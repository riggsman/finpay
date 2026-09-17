from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthError
from app.core.ratelimit import check_rate_limit
from app.core.security import create_access_token, decode_token
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.token import RefreshToken
from app.models.user import User, UserStatus
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    PasswordResetCompleteRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    PasswordResetVerifyRequest,
    PasswordResetVerifyResponse,
    RegisterInitiateRequest,
    RegisterInitiateResponse,
    RegisterRequest,
    TokenResponse,
    UserPublic,
    VerifyOtpRequest,
)
from app.services import audit_service, auth_service, fee_service, password_reset_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register/initiate", response_model=RegisterInitiateResponse)
def register_initiate(payload: RegisterInitiateRequest, db: Session = Depends(get_db)):
    check_rate_limit("otp_initiate", payload.phone,
                     settings.RL_OTP_INITIATE_LIMIT, settings.RL_OTP_INITIATE_WINDOW)
    otp, _account_exists = auth_service.initiate_registration(db, payload.phone)
    db.commit()
    auth_service.deliver_registration_otp(db, payload.phone, otp.code)
    return RegisterInitiateResponse(
        message="Verification code sent to your email.",
        expires_in=settings.OTP_TTL_SECONDS,
        otp_debug=otp.code if settings.EXPOSE_OTP_IN_RESPONSE else None,
    )


@router.post("/register", response_model=MessageResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    auth_service.register_user(db, payload)
    otp, _ = auth_service.initiate_registration(db, payload.phone)
    db.commit()
    auth_service.deliver_registration_otp(db, payload.phone, otp.code)
    return MessageResponse(message="Registration received. Check your email for the OTP.")


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    check_rate_limit("verify_otp", payload.phone,
                     settings.RL_VERIFY_OTP_LIMIT, settings.RL_VERIFY_OTP_WINDOW)
    user = auth_service.verify_otp(db, payload.phone, payload.otp)
    # Auto-login on successful verification for a smooth onboarding flow.
    access, refresh = _issue_tokens(db, user)
    db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        user=UserPublic.model_validate(user),
        config=fee_service.get_client_config(db),
    )


def _issue_tokens(db: Session, user):
    from app.core.security import create_access_token, create_refresh_token
    from app.models.token import RefreshToken

    access = create_access_token(str(user.id))
    refresh, jti, expires_at = create_refresh_token(str(user.id))
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires_at))
    db.flush()
    return access, refresh


@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
def password_reset_request(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    check_rate_limit("password_reset", payload.identifier,
                     settings.RL_PASSWORD_RESET_LIMIT, settings.RL_PASSWORD_RESET_WINDOW)
    entry = password_reset_service.request_reset(db, payload.identifier)
    db.commit()
    if entry:
        user = db.get(User, entry.user_id)
        if user:
            password_reset_service.deliver_reset_code(db, user, entry.code)
    # Respond generically to avoid account enumeration; expose the code only in dev.
    return PasswordResetRequestResponse(
        message="If an account exists, a reset code has been sent to the registered email.",
        expires_in=settings.RESET_CODE_TTL_SECONDS,
        reset_code_debug=(entry.code if (entry and settings.EXPOSE_OTP_IN_RESPONSE) else None),
    )


@router.post("/password-reset/verify", response_model=PasswordResetVerifyResponse)
def password_reset_verify(payload: PasswordResetVerifyRequest, db: Session = Depends(get_db)):
    reset_token, expires_in = password_reset_service.verify_code(
        db, payload.identifier, payload.code
    )
    db.commit()
    return PasswordResetVerifyResponse(reset_token=reset_token, expires_in=expires_in)


@router.post("/password-reset/complete", response_model=MessageResponse)
def password_reset_complete(payload: PasswordResetCompleteRequest, db: Session = Depends(get_db)):
    password_reset_service.complete_reset(db, payload.reset_token, payload.new_password)
    db.commit()
    return MessageResponse(message="Password updated. Please sign in with your new password.")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    check_rate_limit("login", payload.identifier,
                     settings.RL_LOGIN_LIMIT, settings.RL_LOGIN_WINDOW)
    try:
        user, access, refresh = auth_service.login(db, payload.identifier, payload.password)
    except AuthError as exc:
        audit_service.record(db, "LOGIN", result="FAILURE",
                             meta={"identifier": payload.identifier, "code": exc.code})
        db.commit()
        raise
    audit_service.record(db, "LOGIN", user_id=user.id, result="SUCCESS")
    db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        user=UserPublic.model_validate(user),
        config=fee_service.get_client_config(db),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        claims = decode_token(payload.refresh_token)
    except Exception:
        raise AuthError("Invalid or expired refresh token.", code="INVALID_REFRESH_TOKEN")
    if claims.get("type") != "refresh":
        raise AuthError("Invalid token type.", code="INVALID_TOKEN_TYPE")

    jti = claims.get("jti")
    row = db.query(RefreshToken).filter(RefreshToken.jti == jti).one_or_none()
    if not row or row.revoked:
        raise AuthError("Refresh token has been revoked.", code="REFRESH_TOKEN_REVOKED")

    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError, TypeError):
        raise AuthError("Invalid token subject.", code="INVALID_REFRESH_TOKEN")

    user = db.get(User, user_id)
    if not user or user.status != UserStatus.ACTIVE:
        raise AuthError("Account is not active.", code="ACCOUNT_INACTIVE")

    access = create_access_token(str(user.id))
    audit_service.record(db, "TOKEN_REFRESH", user_id=user.id)
    db.commit()
    return AccessTokenResponse(
        access_token=access, expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS
    )


@router.post("/logout", response_model=MessageResponse)
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    revoked = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == current_user.id, RefreshToken.revoked.is_(False))
        .update({RefreshToken.revoked: True})
    )
    audit_service.record(db, "LOGOUT", user_id=current_user.id, meta={"revoked": revoked})
    db.commit()
    return MessageResponse(message="Signed out.")
