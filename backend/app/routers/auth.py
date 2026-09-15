from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
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
from app.services import auth_service, password_reset_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register/initiate", response_model=RegisterInitiateResponse)
def register_initiate(payload: RegisterInitiateRequest, db: Session = Depends(get_db)):
    otp, _account_exists = auth_service.initiate_registration(db, payload.phone)
    db.commit()
    return RegisterInitiateResponse(
        message="Verification code sent.",
        expires_in=settings.OTP_TTL_SECONDS,
        otp_debug=otp.code if settings.EXPOSE_OTP_IN_RESPONSE else None,
    )


@router.post("/register", response_model=MessageResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    auth_service.register_user(db, payload)
    # Ensure an OTP exists for verification.
    auth_service.initiate_registration(db, payload.phone)
    db.commit()
    return MessageResponse(message="Registration received. Verify the OTP to activate.")


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    user = auth_service.verify_otp(db, payload.phone, payload.otp)
    # Auto-login on successful verification for a smooth onboarding flow.
    access, refresh = _issue_tokens(db, user)
    db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        user=UserPublic.model_validate(user),
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
    entry = password_reset_service.request_reset(db, payload.identifier)
    db.commit()
    # Respond generically to avoid account enumeration; expose the code only in dev.
    return PasswordResetRequestResponse(
        message="If an account exists, a reset code has been sent.",
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
    user, access, refresh = auth_service.login(db, payload.identifier, payload.password)
    db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        user=UserPublic.model_validate(user),
    )
