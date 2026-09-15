from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.notifications import fcm
from app.schemas.device import DevicePublic, DeviceRegisterRequest
from app.services import device_service

router = APIRouter(prefix="/me/devices", tags=["devices"])


@router.get("/config")
def push_config(current_user: User = Depends(get_current_user)):
    """Report whether the server is configured to send FCM push."""
    return {"fcm_enabled": settings.fcm_configured}


@router.post("", response_model=DevicePublic)
def register_device(
    payload: DeviceRegisterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = device_service.register_device(
        db, current_user, payload.device_id, payload.device_type, payload.push_token
    )
    db.commit()
    db.refresh(device)
    # Warm the FCM app so the first real push has no init latency.
    fcm.is_enabled()
    return DevicePublic.from_model(device)


@router.get("", response_model=list[DevicePublic])
def list_devices(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [DevicePublic.from_model(d) for d in device_service.list_devices(db, current_user)]


@router.delete("/{device_pk}")
def unregister_device(
    device_pk: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device_service.unregister_device(db, current_user, device_pk)
    db.commit()
    return {"unregistered": True}
