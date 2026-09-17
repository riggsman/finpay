from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.auth import MessageResponse, UserPublic
from app.schemas.security import (
    ActivityPublic,
    ChangePasswordRequest,
    LimitsUpdateRequest,
    ProfileUpdateRequest,
    SessionPublic,
    SetPinRequest,
)
from app.schemas.limits import (
    LimitIncreaseCreate,
    LimitIncreasePublic,
    LimitsResponse,
)
from app.services import audit_service, limit_service, security_service

router = APIRouter(prefix="/me", tags=["profile-security"])


@router.patch("/profile", response_model=UserPublic)
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raise AppError(
        "Profile details cannot be edited. Only your profile picture can be changed in the app.",
        code="PROFILE_LOCKED",
        status_code=403,
    )


@router.post("/security/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    security_service.change_password(
        db, current_user, payload.current_password, payload.new_password
    )
    db.commit()
    return MessageResponse(message="Password changed. Other sessions were signed out.")


@router.put("/security/pin", response_model=MessageResponse)
def set_pin(
    payload: SetPinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    security_service.set_pin(db, current_user, payload.current_pin, payload.new_pin)
    db.commit()
    return MessageResponse(message="Transaction PIN updated.")


@router.get("/security/limits", response_model=LimitsResponse)
def get_limits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    snap = limit_service.limits_snapshot(db, current_user)
    return LimitsResponse(**snap)


@router.post("/security/limit-requests", response_model=LimitIncreasePublic)
def create_limit_request(
    payload: LimitIncreaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = limit_service.create_request(
        db,
        current_user,
        requested_per_txn_limit=payload.requested_per_txn_limit,
        requested_daily_limit=payload.requested_daily_limit,
        reason=payload.reason,
    )
    return LimitIncreasePublic.model_validate(row)


@router.get("/security/limit-requests", response_model=list[LimitIncreasePublic])
def list_limit_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = limit_service.list_for_user(db, current_user.id)
    return [LimitIncreasePublic.model_validate(r) for r in rows]


@router.patch("/security/limits", response_model=LimitsResponse)
def update_limits(
    payload: LimitsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raise AppError(
        "Transaction limits are set by the system and cannot be changed by users. "
        "Submit a limit increase request instead.",
        code="LIMITS_LOCKED",
        status_code=403,
    )


@router.get("/security/sessions", response_model=list[SessionPublic])
def list_sessions(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    sessions = security_service.list_sessions(db, current_user)
    return [SessionPublic.model_validate(s) for s in sessions]


@router.post("/security/sessions/revoke-all", response_model=MessageResponse)
def revoke_all_sessions(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    count = security_service.revoke_other_sessions(db, current_user)
    db.commit()
    return MessageResponse(message=f"Revoked {count} session(s).")


@router.get("/security/activity", response_model=list[ActivityPublic])
def security_activity(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    rows = audit_service.list_for_user(db, current_user.id, limit=limit)
    return [ActivityPublic.model_validate(r) for r in rows]
