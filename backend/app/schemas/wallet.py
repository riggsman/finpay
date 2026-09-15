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
