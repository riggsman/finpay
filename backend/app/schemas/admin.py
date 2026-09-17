from datetime import date, datetime

from pydantic import BaseModel, Field


class FeeRulePublic(BaseModel):
    operation: str
    fee_type: str
    config: dict
    active: bool


class FeeRuleUpdate(BaseModel):
    fee_type: str = Field(pattern="^(FLAT|PERCENTAGE|TIERED)$")
    config: dict
    active: bool = True


class ServiceFlagPublic(BaseModel):
    key: str
    label: str
    kind: str
    enabled: bool
    email_enabled: bool = True


class ServiceFlagUpdate(BaseModel):
    enabled: bool | None = None
    email_enabled: bool | None = None


class ProviderPublic(BaseModel):
    id: int
    category: str
    provider_id: str
    name: str
    description: str | None = None
    enabled: bool
    flow: str = "direct_topup"
    integration_mode: str = "MOCK"
    base_url: str | None = None
    config: dict = Field(default_factory=dict)
    fields: list[dict] = Field(default_factory=list)
    target_label: str = "Account / phone number"
    icon: str | None = None
    sort_order: int = 100

    class Config:
        from_attributes = True


class ProviderCreate(BaseModel):
    category: str = Field(min_length=2, max_length=40)
    provider_id: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    enabled: bool = True
    flow: str | None = Field(default=None, pattern="^(validate_pay|direct_topup)$")
    integration_mode: str = Field(default="MOCK", pattern="^(MOCK|HTTP|mock|http)$")
    base_url: str | None = Field(default=None, max_length=255)
    config: dict = Field(default_factory=dict)
    target_label: str | None = Field(default=None, max_length=80)
    icon: str | None = Field(default=None, max_length=40)
    sort_order: int = 100


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None
    flow: str | None = Field(default=None, pattern="^(validate_pay|direct_topup)$")
    integration_mode: str | None = Field(default=None, pattern="^(MOCK|HTTP|mock|http)$")
    base_url: str | None = Field(default=None, max_length=255)
    config: dict | None = None
    target_label: str | None = Field(default=None, max_length=80)
    icon: str | None = Field(default=None, max_length=40)
    sort_order: int | None = None


class ProviderCategoryPublic(BaseModel):
    category: str
    label: str
    enabled_count: int


class SettingPublic(BaseModel):
    key: str
    value: str
    value_type: str
    label: str


class SettingsUpdate(BaseModel):
    values: dict


class EmailTestRequest(BaseModel):
    to: str | None = None
    subject: str = "FinPay test email"
    body: str = "This is a test email from the FinPay Back Office."


class AdminKycPublic(BaseModel):
    id: int
    user_id: int
    status: str
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    address_line: str | None = None
    city: str | None = None
    country: str | None = None
    id_type: str | None = None
    id_number: str | None = None
    id_document_ref: str | None = None
    id_document_back_ref: str | None = None
    selfie_ref: str | None = None
    rejection_reason: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    user_phone: str | None = None
    user_email: str | None = None
    user_status: str | None = None

    class Config:
        from_attributes = True


class AdminKycRejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AdminUserSummary(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str
    status: str
    phone_verified: bool
    email_verified: bool
    account_number: str | None = None
    kyc_status: str | None = None
    created_at: datetime | None = None


class AdminWalletPublic(BaseModel):
    id: int
    balance: int
    currency: str
    account_number: str | None = None


class AdminUserKycPublic(BaseModel):
    id: int
    status: str
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    address_line: str | None = None
    city: str | None = None
    country: str | None = None
    id_type: str | None = None
    id_number: str | None = None
    id_document_ref: str | None = None
    id_document_back_ref: str | None = None
    selfie_ref: str | None = None
    rejection_reason: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None


class AdminUserProfile(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str
    status: str
    phone_verified: bool
    email_verified: bool
    is_admin: bool = False
    per_txn_limit: int
    daily_limit: int
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None
    account_number: str | None = None
    wallet: AdminWalletPublic | None = None
    kyc: AdminUserKycPublic | None = None


class AdminTransactionPublic(BaseModel):
    id: int
    reference: str
    user_id: int
    user_phone: str | None = None
    user_name: str | None = None
    account_number: str | None = None
    type: str
    direction: str
    direction_label: str
    sender: str | None = None
    sender_phone: str | None = None
    receiver: str | None = None
    receiver_phone: str | None = None
    method: str | None = None
    status: str
    amount: int
    fee: int
    currency: str
    description: str | None = None
    provider_reference: str | None = None
    failure_reason: str | None = None
    pending_reconciliation: bool = False
    can_verify_provider: bool = False
    created_at: datetime
    completed_at: datetime | None = None
