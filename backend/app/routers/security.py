from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.auth import MessageResponse, UserPublic
from app.schemas.security import (
    ActivityPublic,
    ChangePasswordRequest,
    LimitsResponse,
    LimitsUpdateRequest,
    ProfileUpdateRequest,
    SessionPublic,
    SetPinRequest,
)
from app.services import audit_service, security_service

router = APIRouter(prefix="/me", tags=["profile-security"])


@router.patch("/profile", response_model=UserPublic)
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = security_service.update_profile(
        db, current_user, payload.first_name, payload.last_name, payload.email
    )
    db.commit()
    return UserPublic.model_validate(user)


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
def get_limits(current_user: User = Depends(get_current_user)):
    return LimitsResponse(
        per_txn_limit=current_user.per_txn_limit, daily_limit=current_user.daily_limit
    )


@router.patch("/security/limits", response_model=LimitsResponse)
def update_limits(
    payload: LimitsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = security_service.update_limits(
        db, current_user, payload.per_txn_limit, payload.daily_limit
    )
    db.commit()
    return LimitsResponse(per_txn_limit=user.per_txn_limit, daily_limit=user.daily_limit)


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
