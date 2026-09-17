import datetime as dt
import enum

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class KycStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class KycProfile(Base):
    __tablename__ = "kyc_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=KycStatus.NOT_STARTED.value, nullable=False
    )

    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date_of_birth: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)

    id_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    id_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    id_document_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    id_document_back_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selfie_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
        nullable=False,
    )
