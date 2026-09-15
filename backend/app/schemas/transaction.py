import datetime as dt

from pydantic import BaseModel


class TransactionPublic(BaseModel):
    id: int
    reference: str
    type: str
    status: str
    amount: int
    fee: int
    currency: str
    description: str | None = None
    provider_reference: str | None = None
    failure_reason: str | None = None
    created_at: dt.datetime
    completed_at: dt.datetime | None = None

    class Config:
        from_attributes = True


class TransactionEventPublic(BaseModel):
    id: int
    event_type: str
    previous_status: str | None = None
    new_status: str | None = None
    created_at: dt.datetime

    class Config:
        from_attributes = True
