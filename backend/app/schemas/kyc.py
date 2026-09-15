import datetime as dt

from pydantic import BaseModel, Field


class KycProfilePublic(BaseModel):
    status: str
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: dt.date | None = None
    address_line: str | None = None
    city: str | None = None
    country: str | None = None
    id_type: str | None = None
    id_number: str | None = None
    id_document_ref: str | None = None
    selfie_ref: str | None = None
    rejection_reason: str | None = None
    submitted_at: dt.datetime | None = None
    reviewed_at: dt.datetime | None = None

    class Config:
        from_attributes = True


class KycUpdateRequest(BaseModel):
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    date_of_birth: dt.date | None = None
    address_line: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    id_type: str | None = Field(default=None, max_length=40)
    id_number: str | None = Field(default=None, max_length=64)
    id_document_ref: str | None = Field(default=None, max_length=255)
    selfie_ref: str | None = Field(default=None, max_length=255)
