from pydantic import BaseModel, Field


class MeterValidateRequest(BaseModel):
    provider_id: str
    meter_number: str = Field(min_length=1, max_length=40)


class AccountValidateRequest(BaseModel):
    category: str
    provider_id: str
    phone: str = Field(min_length=1, max_length=80)


class ProviderPublic(BaseModel):
    id: str
    name: str


class CustomerPublic(BaseModel):
    name: str
    meter_number: str


class MeterValidateResponse(BaseModel):
    validation_token: str
    customer: CustomerPublic
    provider: ProviderPublic
    expires_in: int
    category: str | None = None


class ElectricityConfirmRequest(BaseModel):
    validation_token: str
    amount: int = Field(gt=0, description="Amount in minor units")
    pin: str = Field(min_length=4, max_length=12)
    idempotency_key: str | None = None
    message: str | None = Field(default=None, max_length=255)


class TopupConfirmRequest(BaseModel):
    category: str = Field(description="airtime or data")
    provider_id: str
    target: str = Field(min_length=3, max_length=40, description="Phone number to top up")
    amount: int = Field(gt=0, description="Amount in minor units")
    pin: str = Field(min_length=4, max_length=12)
    idempotency_key: str | None = None
    message: str | None = Field(default=None, max_length=255)


class UnifiedPayRequest(BaseModel):
    category: str
    provider_id: str
    phone: str | None = Field(default=None, max_length=80)
    amount: int | None = Field(default=None, gt=0, description="Amount in minor units")
    message: str | None = Field(default=None, max_length=255)
    pin: str = Field(min_length=4, max_length=12)
    validation_token: str | None = None
    idempotency_key: str | None = None
