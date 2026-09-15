from pydantic import BaseModel, EmailStr, Field


class RegisterInitiateRequest(BaseModel):
    signup_method: str = Field(default="phone")
    phone: str = Field(min_length=6, max_length=32)


class RegisterInitiateResponse(BaseModel):
    message: str
    expires_in: int
    otp_debug: str | None = None


class RegisterRequest(BaseModel):
    signup_method: str = Field(default="phone")
    phone: str = Field(min_length=6, max_length=32)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    password: str = Field(min_length=8, max_length=128)


class VerifyOtpRequest(BaseModel):
    phone: str
    otp: str = Field(min_length=4, max_length=12)


class LoginRequest(BaseModel):
    identifier: str
    password: str


class UserPublic(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str
    status: str
    phone_verified: bool
    email_verified: bool

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class MessageResponse(BaseModel):
    message: str
