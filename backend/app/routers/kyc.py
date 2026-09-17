from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.kyc import (
    KycCaptureRequest,
    KycCaptureResponse,
    KycProfilePublic,
    KycUpdateRequest,
)
from app.services import kyc_media, kyc_service

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


@router.post("/capture", response_model=KycCaptureResponse)
def capture_kyc_media(
    payload: KycCaptureRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store a camera capture and attach it to the user's KYC draft."""
    field = kyc_media.field_for_kind(payload.kind)
    ref = kyc_media.save_capture(current_user.id, payload.kind, payload.image_base64)
    kyc_service.update_draft(db, current_user, {field: ref})
    db.commit()
    return KycCaptureResponse(kind=payload.kind, ref=ref, field=field)


@router.get("/media/{ref}")
def get_kyc_media(
    ref: str,
    current_user: User = Depends(get_current_user),
):
    if not kyc_media.owned_by(ref, current_user.id) and not current_user.is_admin:
        raise NotFoundError("Capture not found.", code="KYC_CAPTURE_NOT_FOUND")
    path = kyc_media.resolve_path(ref)
    media = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else f"image/{path.suffix.lstrip('.')}"
    return FileResponse(path, media_type=media, filename=Path(ref).name)


@router.post("/submit", response_model=KycProfilePublic)
def submit_kyc(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kyc = kyc_service.submit(db, current_user)
    return KycProfilePublic.model_validate(kyc)
