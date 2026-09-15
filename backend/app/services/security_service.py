import datetime as dt

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, ConflictError, ValidationError
from app.core.security import hash_password, verify_password
from app.models.token import RefreshToken
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User
from app.services import audit_service
from app.services.notification_service import create_notification, deliver_notification

# Transaction types that draw down the wallet and count toward limits.
DEBIT_TYPES = ("SEND_MONEY", "WITHDRAW", "ELECTRICITY")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def update_profile(db: Session, user: User, first_name: str | None,
                   last_name: str | None, email: str | None) -> User:
    if email is not None and email != user.email:
        clash = db.query(User).filter(User.email == email, User.id != user.id).one_or_none()
        if clash:
            raise ConflictError("Email already in use.", code="EMAIL_EXISTS")
        user.email = email
        user.email_verified = False
    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name
    audit_service.record(db, "PROFILE_UPDATED", user_id=user.id, entity_type="user",
                         entity_id=user.id)
    db.flush()
    return user


def change_password(db: Session, user: User, current_password: str,
                    new_password: str) -> None:
    if not user.password_hash or not verify_password(current_password, user.password_hash):
        raise AuthError("Current password is incorrect.", code="INVALID_PASSWORD")
    user.password_hash = hash_password(new_password)
    # Revoke existing sessions on credential change (security policy).
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False)
    ).update({RefreshToken.revoked: True})
    audit_service.record(db, "PASSWORD_CHANGED", user_id=user.id, entity_type="user",
                         entity_id=user.id)
    notif = create_notification(
        db, user_id=user.id, type="PASSWORD_CHANGED", title="Password Changed",
        message="Your account password was changed.", priority="HIGH",
    )
    db.flush()
    deliver_notification(notif)


def set_pin(db: Session, user: User, current_pin: str | None, new_pin: str) -> None:
    if not new_pin.isdigit() or len(new_pin) < 4:
        raise ValidationError("PIN must be at least 4 digits.", code="INVALID_PIN_FORMAT")
    if user.transaction_pin_hash:
        if not current_pin or not verify_password(current_pin, user.transaction_pin_hash):
            raise AuthError("Current PIN is incorrect.", code="INVALID_PIN")
    user.transaction_pin_hash = hash_password(new_pin)
    audit_service.record(db, "PIN_CHANGED", user_id=user.id, entity_type="user",
                         entity_id=user.id)
    notif = create_notification(
        db, user_id=user.id, type="PIN_CHANGED", title="Transaction PIN Changed",
        message="Your transaction PIN was updated.", priority="HIGH",
    )
    db.flush()
    deliver_notification(notif)


def update_limits(db: Session, user: User, per_txn_limit: int | None,
                  daily_limit: int | None) -> User:
    new_per = per_txn_limit if per_txn_limit is not None else user.per_txn_limit
    new_daily = daily_limit if daily_limit is not None else user.daily_limit
    if new_per <= 0 or new_daily <= 0:
        raise ValidationError("Limits must be positive.", code="INVALID_LIMIT")
    if new_per > new_daily:
        raise ValidationError("Per-transaction limit cannot exceed the daily limit.",
                              code="INVALID_LIMIT_RANGE")
    user.per_txn_limit = new_per
    user.daily_limit = new_daily
    audit_service.record(db, "LIMITS_UPDATED", user_id=user.id, entity_type="user",
                         entity_id=user.id,
                         meta={"per_txn_limit": new_per, "daily_limit": new_daily})
    db.flush()
    return user


def _spent_today(db: Session, user_id: int) -> int:
    start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    total = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_id == user_id,
            Transaction.type.in_(DEBIT_TYPES),
            Transaction.status.in_(
                [TransactionStatus.PROCESSING.value, TransactionStatus.SUCCESS.value]
            ),
            Transaction.created_at >= start,
        )
        .scalar()
    )
    return int(total or 0)


def check_limits(db: Session, user: User, amount: int) -> None:
    """Enforce per-transaction and daily spending limits before a debit."""
    if amount > user.per_txn_limit:
        raise ValidationError(
            f"Amount exceeds your per-transaction limit of {user.per_txn_limit / 100:,.2f}.",
            code="PER_TXN_LIMIT_EXCEEDED",
        )
    if _spent_today(db, user.id) + amount > user.daily_limit:
        raise ValidationError(
            "This payment would exceed your daily limit.",
            code="DAILY_LIMIT_EXCEEDED",
        )


def list_sessions(db: Session, user: User) -> list[RefreshToken]:
    return (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > _now(),
        )
        .order_by(RefreshToken.created_at.desc())
        .all()
    )


def revoke_other_sessions(db: Session, user: User) -> int:
    count = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
        .update({RefreshToken.revoked: True})
    )
    db.flush()
    return count
