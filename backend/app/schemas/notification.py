import datetime as dt

from pydantic import BaseModel


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

    class Config:
        from_attributes = True


class UnreadCountResponse(BaseModel):
    unread: int
