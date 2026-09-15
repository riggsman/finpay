import datetime as dt
import threading

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, ValidationError
from app.core.logging import get_logger
from app.db.database import SessionLocal
from app.models.kyc import KycProfile, KycStatus
from app.models.user import User
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_user

logger = get_logger("finpay.kyc")

# Fields that must be present before a KYC profile can be submitted.
REQUIRED_FIELDS = (
    "first_name", "last_name", "date_of_birth", "address_line", "city",
    "country", "id_type", "id_number", "id_document_ref", "selfie_ref",
)

EDITABLE_FIELDS = (
    "first_name", "last_name", "date_of_birth", "address_line", "city",
    "country", "id_type", "id_number", "id_document_ref", "selfie_ref",
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def get_or_create(db: Session, user: User) -> KycProfile:
    kyc = db.query(KycProfile).filter(KycProfile.user_id == user.id).one_or_none()
    if not kyc:
        kyc = KycProfile(user_id=user.id, status=KycStatus.NOT_STARTED.value)
        db.add(kyc)
        db.flush()
    return kyc


def update_draft(db: Session, user: User, data: dict) -> KycProfile:
    kyc = get_or_create(db, user)
    if kyc.status in (KycStatus.UNDER_REVIEW.value, KycStatus.APPROVED.value):
        raise ConflictError("KYC cannot be edited in its current state.",
                            code="KYC_LOCKED")
    for field in EDITABLE_FIELDS:
        if field in data and data[field] is not None:
            setattr(kyc, field, data[field])
    if kyc.status in (KycStatus.NOT_STARTED.value, KycStatus.REJECTED.value):
        kyc.status = KycStatus.IN_PROGRESS.value
        kyc.rejection_reason = None
    db.flush()
    return kyc


def submit(db: Session, user: User) -> KycProfile:
    kyc = get_or_create(db, user)
    if kyc.status in (KycStatus.UNDER_REVIEW.value, KycStatus.APPROVED.value):
        raise ConflictError("KYC has already been submitted.", code="KYC_ALREADY_SUBMITTED")

    missing = [f for f in REQUIRED_FIELDS if not getattr(kyc, f)]
    if missing:
        raise ValidationError(
            f"Missing required fields: {', '.join(missing)}", code="KYC_INCOMPLETE"
        )

    kyc.status = KycStatus.UNDER_REVIEW.value
    kyc.submitted_at = _now()
    kyc.rejection_reason = None
    db.commit()
    db.refresh(kyc)

    emit_to_user(user.id, "KYC_STATUS_UPDATED", {"status": kyc.status})
    _schedule_review(kyc.id, user.id)
    return kyc


def _schedule_review(kyc_id: int, user_id: int) -> None:
    timer = threading.Timer(
        settings.KYC_REVIEW_DELAY_SECONDS, _run_review, args=(kyc_id, user_id)
    )
    timer.daemon = True
    timer.start()


def _run_review(kyc_id: int, user_id: int) -> None:
    """Simulated compliance review (background thread)."""
    db = SessionLocal()
    try:
        kyc = db.get(KycProfile, kyc_id)
        if not kyc or kyc.status != KycStatus.UNDER_REVIEW.value:
            return

        # Simulated decision: ID numbers ending in 0000 are rejected.
        approved = not (kyc.id_number or "").endswith("0000")
        kyc.reviewed_at = _now()

        if approved:
            kyc.status = KycStatus.APPROVED.value
            # Grant higher transaction limits on approval.
            user = db.get(User, user_id)
            if user:
                user.per_txn_limit = settings.KYC_APPROVED_PER_TXN_LIMIT
                user.daily_limit = settings.KYC_APPROVED_DAILY_LIMIT
            notif = create_notification(
                db, user_id=user_id, type="KYC_APPROVED", title="Identity Verified",
                message="Your identity has been verified. Your limits have been raised.",
                priority="HIGH",
            )
        else:
            kyc.status = KycStatus.REJECTED.value
            kyc.rejection_reason = "The submitted ID could not be verified."
            notif = create_notification(
                db, user_id=user_id, type="KYC_REJECTED", title="Verification Failed",
                message="We could not verify your identity. Please review and resubmit.",
                priority="HIGH",
            )

        db.commit()
        db.refresh(kyc)

        emit_to_user(user_id, "KYC_STATUS_UPDATED", {
            "status": kyc.status, "rejection_reason": kyc.rejection_reason,
        })
        deliver_notification(notif)
    except Exception:  # pragma: no cover - defensive
        logger.exception("KYC review failed for kyc=%s", kyc_id)
        db.rollback()
    finally:
        db.close()
