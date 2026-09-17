import datetime as dt

from pydantic import BaseModel, Field


class LimitIncreaseCreate(BaseModel):
    requested_per_txn_limit: int = Field(gt=0)
    requested_daily_limit: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=500)


class LimitIncreaseApprove(BaseModel):
    approved_per_txn_limit: int | None = Field(default=None, gt=0)
    approved_daily_limit: int | None = Field(default=None, gt=0)
    duration_days: int = Field(default=30, ge=1, le=365)
    spending_cap: int | None = Field(default=None, gt=0)


class LimitIncreaseReject(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class LimitIncreasePublic(BaseModel):
    id: int
    user_id: int
    requested_per_txn_limit: int
    requested_daily_limit: int
    reason: str | None = None
    status: str
    rejection_reason: str | None = None
    approved_per_txn_limit: int | None = None
    approved_daily_limit: int | None = None
    duration_days: int | None = None
    spending_cap: int | None = None
    amount_spent: int = 0
    starts_at: dt.datetime | None = None
    expires_at: dt.datetime | None = None
    reviewed_at: dt.datetime | None = None
    created_at: dt.datetime

    class Config:
        from_attributes = True


class ActiveGrantPublic(BaseModel):
    id: int
    per_txn_limit: int | None = None
    daily_limit: int | None = None
    expires_at: dt.datetime | None = None
    spending_cap: int | None = None
    amount_spent: int = 0
    remaining_allowance: int | None = None


class LimitsResponse(BaseModel):
    per_txn_limit: int
    daily_limit: int
    spent_today: int = 0
    remaining_daily: int = 0
    default_per_txn_limit: int | None = None
    default_daily_limit: int | None = None
    active_grant: ActiveGrantPublic | None = None
