import datetime as dt

from pydantic import BaseModel, EmailStr, Field


class ProfileUpdateRequest(BaseModel):
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class SetPinRequest(BaseModel):
    current_pin: str | None = None
    new_pin: str = Field(min_length=4, max_length=12)


class LimitsResponse(BaseModel):
    per_txn_limit: int
    daily_limit: int


class LimitsUpdateRequest(BaseModel):
    per_txn_limit: int | None = Field(default=None, gt=0)
    daily_limit: int | None = Field(default=None, gt=0)


class SessionPublic(BaseModel):
    id: int
    created_at: dt.datetime
    expires_at: dt.datetime

    class Config:
        from_attributes = True
