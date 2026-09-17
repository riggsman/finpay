import datetime as dt

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class PhoneNameLookup(Base):
    __tablename__ = "phone_name_lookups"
    __table_args__ = (
        UniqueConstraint("phone", "provider", name="uq_phone_name_lookup"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Normalized MSISDN, e.g. 237682835503.
    phone: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="campay", nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(40), nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How many times a cached row has been served without a refresh.
    lookup_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_checked_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
        nullable=False,
    )