import datetime as dt
import threading

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.database import SessionLocal
from app.models.kyc import KycProfile, KycStatus
from app.models.user import User
from app.services import audit_service
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_user

logger = get_logger("finpay.kyc")

# Fields that must be present before a KYC profile can be submitted.
REQUIRED_FIELDS = (
    "first_name", "last_name", "date_of_birth", "address_line", "city",
    "country", "id_type", "id_number", "id_document_ref", "id_document_back_ref",
    "selfie_ref",
)

EDITABLE_FIELDS = (
    "first_name", "last_name", "date_of_birth", "address_line", "city",
    "country", "id_type", "id_number", "id_document_ref", "id_document_back_ref",
    "selfie_ref",
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
    audit_service.record(db, "KYC_SUBMITTED", user_id=user.id, entity_type="kyc",
                         entity_id=kyc.id)
    db.commit()
    db.refresh(kyc)

    emit_to_user(user.id, "KYC_STATUS_UPDATED", {"status": kyc.status})
    if settings.KYC_AUTO_REVIEW_ENABLED:
        _schedule_review(kyc.id, user.id)
    return kyc


def list_for_admin(
    db: Session,
    status: str | None = None,
    user_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[KycProfile]:
    q = db.query(KycProfile)
    if status:
        q = q.filter(KycProfile.status == status.upper())
    if user_id is not None:
        q = q.filter(KycProfile.user_id == user_id)
    return (
        q.order_by(KycProfile.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def _apply_decision(
    db: Session,
    kyc: KycProfile,
    *,
    approved: bool,
    rejection_reason: str | None,
    admin_id: int | None,
) -> KycProfile:
    status = kyc.status

    if approved:
        if status == KycStatus.REJECTED.value:
            raise ConflictError(
                "A rejected KYC cannot be approved again.",
                code="KYC_CANNOT_APPROVE_REJECTED",
            )
        if status == KycStatus.APPROVED.value:
            raise ConflictError(
                "KYC is already approved.",
                code="KYC_ALREADY_APPROVED",
            )
        if status != KycStatus.UNDER_REVIEW.value:
            raise ConflictError(
                "Only submissions under review can be approved.",
                code="KYC_NOT_REVIEWABLE",
            )
    else:
        if status == KycStatus.REJECTED.value:
            raise ConflictError(
                "KYC is already rejected.",
                code="KYC_ALREADY_REJECTED",
            )
        if status not in (KycStatus.UNDER_REVIEW.value, KycStatus.APPROVED.value):
            raise ConflictError(
                "Only under-review or approved KYC can be rejected.",
                code="KYC_NOT_REJECTABLE",
            )

    kyc.reviewed_at = _now()

    if approved:
        kyc.status = KycStatus.APPROVED.value
        kyc.rejection_reason = None
        notif = create_notification(
            db,
            user_id=kyc.user_id,
            type="KYC_APPROVED",
            title="Successful KYC verification",
            message=(
                "Your KYC verification was successful. Your identity has been verified "
                "and you can continue using FinPay."
            ),
            priority="HIGH",
            data={"status": KycStatus.APPROVED.value, "kyc_id": kyc.id},
        )
    else:
        reason = (rejection_reason or "").strip() or "The submitted ID could not be verified."
        kyc.status = KycStatus.REJECTED.value
        kyc.rejection_reason = reason
        notif = create_notification(
            db,
            user_id=kyc.user_id,
            type="KYC_REJECTED",
            title="KYC verification rejected",
            message=(
                f"Your KYC verification was rejected. Reason: {reason}. "
                "Please update your documents and resubmit."
            ),
            priority="HIGH",
            data={
                "status": KycStatus.REJECTED.value,
                "kyc_id": kyc.id,
                "rejection_reason": reason,
            },
        )

    audit_service.record(
        db,
        "KYC_APPROVED" if approved else "KYC_REJECTED",
        user_id=admin_id or kyc.user_id,
        entity_type="kyc",
        entity_id=kyc.id,
        result="SUCCESS" if approved else "FAILURE",
        meta={
            "subject_user_id": kyc.user_id,
            "manual": admin_id is not None,
            "previous_status": status,
        },
    )
    db.commit()
    db.refresh(kyc)

    emit_to_user(
        kyc.user_id,
        "KYC_STATUS_UPDATED",
        {"status": kyc.status, "rejection_reason": kyc.rejection_reason},
    )
    deliver_notification(notif)
    return kyc


def admin_approve(db: Session, kyc_id: int, admin: User) -> KycProfile:
    kyc = db.get(KycProfile, kyc_id)
    if not kyc:
        raise NotFoundError("KYC profile not found.", code="KYC_NOT_FOUND")
    return _apply_decision(db, kyc, approved=True, rejection_reason=None, admin_id=admin.id)


def admin_reject(
    db: Session, kyc_id: int, admin: User, reason: str | None = None
) -> KycProfile:
    kyc = db.get(KycProfile, kyc_id)
    if not kyc:
        raise NotFoundError("KYC profile not found.", code="KYC_NOT_FOUND")
    return _apply_decision(
        db, kyc, approved=False, rejection_reason=reason, admin_id=admin.id
    )


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
        reason = None if approved else "The submitted ID could not be verified."
        _apply_decision(
            db, kyc, approved=approved, rejection_reason=reason, admin_id=None
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("KYC review failed for kyc=%s", kyc_id)
        db.rollback()
    finally:
        db.close()
