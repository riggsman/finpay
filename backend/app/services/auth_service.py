import datetime as dt
import random

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthError, ConflictError, NotFoundError, ValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.otp import OtpCode
from app.models.token import RefreshToken
from app.models.user import User, UserStatus
from app.models.wallet import Wallet


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _generate_otp() -> str:
    return f"{random.randint(0, 999999):06d}"


def initiate_registration(db: Session, phone: str) -> tuple[OtpCode, bool]:
    existing = db.query(User).filter(User.phone == phone).one_or_none()
    account_exists = existing is not None and existing.status == UserStatus.ACTIVE

    # Rate limit: reuse an unexpired OTP window instead of spamming new codes.
    recent = (
        db.query(OtpCode)
        .filter(
            OtpCode.identifier == phone,
            OtpCode.purpose == "registration",
            OtpCode.consumed.is_(False),
            OtpCode.expires_at > _now(),
        )
        .order_by(OtpCode.created_at.desc())
        .first()
    )
    if recent:
        return recent, account_exists

    otp = OtpCode(
        identifier=phone,
        purpose="registration",
        code=_generate_otp(),
        expires_at=_now() + dt.timedelta(seconds=settings.OTP_TTL_SECONDS),
    )
    db.add(otp)
    db.flush()
    return otp, account_exists


def register_user(db: Session, data) -> User:
    existing = db.query(User).filter(User.phone == data.phone).one_or_none()
    if existing and existing.status == UserStatus.ACTIVE:
        raise ConflictError("An account with this phone number already exists.",
                            code="ACCOUNT_EXISTS")

    if data.email:
        email_owner = db.query(User).filter(User.email == data.email).one_or_none()
        if email_owner and email_owner.phone != data.phone:
            raise ConflictError("Email already in use.", code="EMAIL_EXISTS")

    user = existing or User(phone=data.phone)
    user.first_name = data.first_name
    user.last_name = data.last_name
    user.email = data.email
    user.password_hash = hash_password(data.password)
    user.status = UserStatus.PENDING_VERIFICATION
    db.add(user)
    db.flush()
    return user


def verify_otp(db: Session, phone: str, code: str) -> User:
    otp = (
        db.query(OtpCode)
        .filter(
            OtpCode.identifier == phone,
            OtpCode.purpose == "registration",
            OtpCode.consumed.is_(False),
        )
        .order_by(OtpCode.created_at.desc())
        .first()
    )
    if not otp:
        raise ValidationError("No pending verification found. Please register again.",
                              code="OTP_NOT_FOUND")
    if otp.expires_at < _now():
        raise ValidationError("OTP has expired. Please request a new code.",
                              code="OTP_EXPIRED")
    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise ValidationError("Maximum OTP attempts exceeded.", code="OTP_MAX_ATTEMPTS")

    if otp.code != code:
        otp.attempts += 1
        db.flush()
        raise ValidationError("Incorrect OTP code.", code="OTP_INCORRECT")

    otp.consumed = True

    user = db.query(User).filter(User.phone == phone).one_or_none()
    if not user:
        raise NotFoundError("User not found.", code="USER_NOT_FOUND")

    user.status = UserStatus.ACTIVE
    user.phone_verified = True

    # Provision a wallet on activation (idempotent).
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).one_or_none()
    if not wallet:
        db.add(Wallet(user_id=user.id, balance=0, currency="XAF"))

    db.flush()
    return user


def login(db: Session, identifier: str, password: str) -> tuple[User, str, str]:
    user = (
        db.query(User)
        .filter(or_(User.phone == identifier, User.email == identifier))
        .one_or_none()
    )
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise AuthError("Invalid credentials.", code="INVALID_CREDENTIALS")
    if user.status == UserStatus.PENDING_VERIFICATION:
        raise AuthError("Account not verified. Please complete OTP verification.",
                        code="ACCOUNT_NOT_VERIFIED")
    if user.status != UserStatus.ACTIVE:
        raise AuthError("Account is not active.", code="ACCOUNT_INACTIVE")

    access = create_access_token(str(user.id))
    refresh, jti, expires_at = create_refresh_token(str(user.id))
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires_at))
    user.last_login_at = _now()
    db.flush()
    return user, access, refresh
