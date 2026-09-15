import datetime as dt

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.device import UserDevice
from app.models.user import User


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def register_device(db: Session, user: User, device_id: str, device_type: str,
                    push_token: str | None) -> UserDevice:
    # A push token is unique to a browser/app install. If it was previously
    # registered elsewhere, detach it so pushes don't go to the wrong account.
    if push_token:
        (
            db.query(UserDevice)
            .filter(UserDevice.push_token == push_token)
            .filter((UserDevice.user_id != user.id) | (UserDevice.device_id != device_id))
            .update({UserDevice.push_token: None, UserDevice.is_active: False})
        )

    device = (
        db.query(UserDevice)
        .filter(UserDevice.user_id == user.id, UserDevice.device_id == device_id)
        .one_or_none()
    )
    if device is None:
        device = UserDevice(user_id=user.id, device_id=device_id)
        db.add(device)

    device.device_type = device_type or "web"
    device.push_token = push_token
    device.is_active = True
    device.last_seen_at = _now()
    db.flush()
    return device


def list_devices(db: Session, user: User) -> list[UserDevice]:
    return (
        db.query(UserDevice)
        .filter(UserDevice.user_id == user.id, UserDevice.is_active.is_(True))
        .order_by(UserDevice.last_seen_at.desc())
        .all()
    )


def unregister_device(db: Session, user: User, device_pk: int) -> None:
    device = db.get(UserDevice, device_pk)
    if not device or device.user_id != user.id:
        raise NotFoundError("Device not found.", code="DEVICE_NOT_FOUND")
    device.is_active = False
    device.push_token = None
    db.flush()
