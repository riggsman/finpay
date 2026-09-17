from pydantic import BaseModel, Field, field_validator, model_validator

_MOMO_METHODS = {"mobile_money", "momo", "mtn", "orange"}


class WalletResponse(BaseModel):
    id: int
    balance: int
    currency: str

    class Config:
        from_attributes = True


class AmountField:
    """Shared ``amount`` validation reused by all wallet requests."""

    amount: int = Field(gt=0, description="Amount in minor units (e.g. XAF)")


class CardDepositDetails(BaseModel):
    """Required inputs for card-funded deposits."""

    card_number: str = Field(
        min_length=12, max_length=19, description="PAN digits (stored masked on the transaction)."
    )
    card_holder: str = Field(min_length=3, max_length=80, description="Name as printed on card.")
    expiry_month: int = Field(ge=1, le=12)
    expiry_year: int = Field(
        ge=2025,
        le=2100,
        description="4-digit expiry year. Year must be in the future relative to month.",
    )
    cvv: str = Field(min_length=3, max_length=4, description="3-4 digit security code (never stored).")

    @field_validator("card_number")
    @classmethod
    def _card_digits(cls, value: str) -> str:
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if len(digits) < 12 or len(digits) > 19:
            raise ValueError("card_number must be 12–19 digits.")
        return digits

    @field_validator("card_holder")
    @classmethod
    def _holder_trim(cls, value: str) -> str:
        text = (value or "").strip()
        if len(text) < 3:
            raise ValueError("card_holder is required.")
        return text

    @field_validator("cvv")
    @classmethod
    def _cvv_digits(cls, value: str) -> str:
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if len(digits) not in (3, 4):
            raise ValueError("cvv must be 3 or 4 digits.")
        return digits


class BankDepositDetails(BaseModel):
    """Required inputs for bank-transfer funded deposits."""

    bank_code: str = Field(min_length=3, max_length=12, description="BIC / bank identifier.")
    account_number: str = Field(min_length=6, max_length=34, description="IBAN / account number.")
    account_holder: str = Field(min_length=3, max_length=80, description="Account holder name.")

    @field_validator("bank_code", "account_number", "account_holder")
    @classmethod
    def _trim_required(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("This field is required.")
        return text


class AddMoneyRequest(BaseModel):
    amount: int = Field(gt=0, description="Amount in minor units (e.g. XAF)")
    funding_method: str = Field(
        default="card",
        description="card, bank, or mobile_money (Campay).",
    )
    phone: str | None = Field(
        default=None,
        description="MSISDN for mobile_money collection (Campay)",
        max_length=40,
    )
    card_details: CardDepositDetails | None = None
    bank_details: BankDepositDetails | None = None
    idempotency_key: str | None = None

    @model_validator(mode="after")
    def _require_details_per_method(self) -> "AddMoneyRequest":
        method = (self.funding_method or "").strip().lower()
        if not method:
            self.funding_method = "card"
            method = "card"
        if method in _MOMO_METHODS and not (self.phone or "").strip():
            raise ValueError("phone is required for mobile money deposits.")
        # Card/bank detail objects are enforced in wallet_service so feature-flag
        # checks and stable AppError codes run in one place.
        return self


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
