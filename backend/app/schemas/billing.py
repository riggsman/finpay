from pydantic import BaseModel, Field


class MeterValidateRequest(BaseModel):
    provider_id: str
    meter_number: str = Field(min_length=1, max_length=40)


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


class ElectricityConfirmRequest(BaseModel):
    validation_token: str
    amount: int = Field(gt=0, description="Amount in minor units")
    pin: str = Field(min_length=4, max_length=12)
    idempotency_key: str | None = None


class TopupConfirmRequest(BaseModel):
    category: str = Field(description="airtime or data")
    provider_id: str
    target: str = Field(min_length=3, max_length=40, description="Phone number to top up")
    amount: int = Field(gt=0, description="Amount in minor units")
    pin: str = Field(min_length=4, max_length=12)
    idempotency_key: str | None = None
