import datetime as dt

from pydantic import BaseModel, Field


class BeneficiaryCreateRequest(BaseModel):
    identifier: str = Field(description="Beneficiary phone or email")


class BeneficiaryPublic(BaseModel):
    id: int
    display_name: str
    phone: str

    class Config:
        from_attributes = True


class MoneyRequestCreate(BaseModel):
    payer: str = Field(description="Payer phone or email")
    amount: int = Field(gt=0, description="Amount in minor units")
    note: str | None = None


class MoneyRequestPublic(BaseModel):
    id: int
    reference: str
    requester_id: int
    payer_id: int
    amount: int
    currency: str
    note: str | None = None
    status: str
    transaction_id: int | None = None
    created_at: dt.datetime
    resolved_at: dt.datetime | None = None

    class Config:
        from_attributes = True


class PayRequestBody(BaseModel):
    pin: str = Field(min_length=4, max_length=12)
