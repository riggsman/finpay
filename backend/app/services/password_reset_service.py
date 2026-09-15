import datetime as dt
import random
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.security import hash_password
from app.models.password_reset import PasswordResetToken
from app.models.token import RefreshToken
from app.models.user import User


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _find_user(db: Session, identifier: str) -> User | None:
    return (
        db.query(User)
        .filter(or_(User.phone == identifier, User.email == identifier))
        .one_or_none()
    )


def request_reset(db: Session, identifier: str) -> PasswordResetToken | None:
    """Create a reset code for the user. Returns None if no user (caller should
    still respond generically to avoid account enumeration)."""
    user = _find_user(db, identifier)
    if not user:
        return None

    entry = PasswordResetToken(
        user_id=user.id,
        code=f"{random.randint(0, 999999):06d}",
        code_expires_at=_now() + dt.timedelta(seconds=settings.RESET_CODE_TTL_SECONDS),
    )
    db.add(entry)
    db.flush()
    return entry


def verify_code(db: Session, identifier: str, code: str) -> tuple[str, int]:
    """Validate the code and issue a short-lived reset token."""
    user = _find_user(db, identifier)
    if not user:
        raise ValidationError("Invalid reset request.", code="RESET_INVALID")

    entry = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.code_consumed.is_(False),
        )
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )
    if not entry:
        raise ValidationError("No pending reset found. Request a new code.",
                              code="RESET_NOT_FOUND")
    if entry.code_expires_at < _now():
        raise ValidationError("Reset code expired. Request a new code.",
                              code="RESET_CODE_EXPIRED")
    if entry.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise ValidationError("Too many attempts. Request a new code.",
                              code="RESET_MAX_ATTEMPTS")
    if entry.code != code:
        entry.attempts += 1
        db.flush()
        raise ValidationError("Incorrect reset code.", code="RESET_CODE_INCORRECT")

    entry.code_consumed = True
    entry.reset_token = "rst_" + uuid.uuid4().hex
    entry.token_expires_at = _now() + dt.timedelta(seconds=settings.RESET_TOKEN_TTL_SECONDS)
    db.flush()
    return entry.reset_token, settings.RESET_TOKEN_TTL_SECONDS


def complete_reset(db: Session, reset_token: str, new_password: str) -> User:
    entry = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.reset_token == reset_token)
        .one_or_none()
    )
    if not entry or entry.token_consumed:
        raise ValidationError("Invalid or used reset token.", code="RESET_TOKEN_INVALID")
    if not entry.token_expires_at or entry.token_expires_at < _now():
        raise ValidationError("Reset token expired. Start over.", code="RESET_TOKEN_EXPIRED")

    user = db.get(User, entry.user_id)
    if not user:
        raise ValidationError("Invalid reset token.", code="RESET_TOKEN_INVALID")

    user.password_hash = hash_password(new_password)
    entry.token_consumed = True

    # Security policy: revoke existing refresh tokens after a password change.
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False)
    ).update({RefreshToken.revoked: True})

    db.flush()
    return user
