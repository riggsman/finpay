from pydantic import BaseModel, Field


class WalletResponse(BaseModel):
    id: int
    balance: int
    currency: str

    class Config:
        from_attributes = True


class AddMoneyRequest(BaseModel):
    amount: int = Field(gt=0, description="Amount in minor units (e.g. XAF)")
    funding_method: str = Field(default="card")
    idempotency_key: str | None = None


class SendMoneyRequest(BaseModel):
    recipient: str = Field(description="Recipient phone or email")
    amount: int = Field(gt=0, description="Amount in minor units")
    pin: str = Field(min_length=4, max_length=12)
    idempotency_key: str | None = None


class WithdrawRequest(BaseModel):
    amount: int = Field(gt=0, description="Amount in minor units")
    destination: str = Field(description="Destination account / number")
    pin: str = Field(min_length=4, max_length=12)
    idempotency_key: str | None = None
