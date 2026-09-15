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
