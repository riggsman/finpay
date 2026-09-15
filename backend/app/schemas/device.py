import datetime as dt

from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    device_type: str = Field(default="web", max_length=20)
    push_token: str | None = Field(default=None, max_length=512)


class DevicePublic(BaseModel):
    id: int
    device_id: str
    device_type: str
    has_push_token: bool
    is_active: bool
    last_seen_at: dt.datetime

    @classmethod
    def from_model(cls, d) -> "DevicePublic":
        return cls(
            id=d.id,
            device_id=d.device_id,
            device_type=d.device_type,
            has_push_token=bool(d.push_token),
            is_active=d.is_active,
            last_seen_at=d.last_seen_at,
        )
