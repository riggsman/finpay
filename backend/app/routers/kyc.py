from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.kyc import KycProfilePublic, KycUpdateRequest
from app.services import kyc_service

router = APIRouter(prefix="/me/kyc", tags=["kyc"])


@router.get("", response_model=KycProfilePublic)
def get_kyc(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kyc = kyc_service.get_or_create(db, current_user)
    db.commit()
    return KycProfilePublic.model_validate(kyc)


@router.put("", response_model=KycProfilePublic)
def update_kyc(
    payload: KycUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kyc = kyc_service.update_draft(db, current_user, payload.model_dump(exclude_unset=True))
    db.commit()
    return KycProfilePublic.model_validate(kyc)


@router.post("/submit", response_model=KycProfilePublic)
def submit_kyc(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kyc = kyc_service.submit(db, current_user)
    return KycProfilePublic.model_validate(kyc)
