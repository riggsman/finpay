import datetime as dt

from pydantic import BaseModel, Field


class TicketCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=160)
    category: str = Field(default="general", max_length=40)
    message: str = Field(min_length=1)


class MessageCreateRequest(BaseModel):
    body: str = Field(min_length=1)


class SupportMessagePublic(BaseModel):
    id: int
    sender: str
    body: str
    created_at: dt.datetime

    class Config:
        from_attributes = True


class TicketPublic(BaseModel):
    id: int
    reference: str
    subject: str
    category: str
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime

    class Config:
        from_attributes = True


class TicketDetailPublic(TicketPublic):
    messages: list[SupportMessagePublic] = []


class DisputeCreateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=60)
    description: str | None = None


class DisputePublic(BaseModel):
    id: int
    reference: str
    transaction_id: int
    reason: str
    description: str | None = None
    status: str
    resolution: str | None = None
    created_at: dt.datetime
    resolved_at: dt.datetime | None = None

    class Config:
        from_attributes = True
