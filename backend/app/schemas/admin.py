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


class ServiceFlagUpdate(BaseModel):
    enabled: bool


class ProviderPublic(BaseModel):
    id: int
    category: str
    provider_id: str
    name: str
    enabled: bool

    class Config:
        from_attributes = True


class ProviderCreate(BaseModel):
    category: str = Field(pattern="^(electricity|airtime|data|water)$")
    provider_id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)


class ProviderUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None


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
