import datetime as dt
import json

from pydantic import BaseModel, field_validator


class NotificationPublic(BaseModel):
    id: int
    event_id: str
    type: str
    title: str
    message: str
    priority: str
    is_read: bool
    created_at: dt.datetime
    read_at: dt.datetime | None = None
    data: dict | None = None

    @field_validator("data", mode="before")
    @classmethod
    def parse_data(cls, value):
        if value is None or isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return None
            return parsed if isinstance(parsed, dict) else None
        return None

    class Config:
        from_attributes = True


class UnreadCountResponse(BaseModel):
    unread: int
