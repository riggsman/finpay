import datetime as dt
import enum

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class LimitIncreaseStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXHAUSTED = "EXHAUSTED"


class LimitIncreaseRequest(Base):
    """User request to raise transaction limits; admin-validated separately from KYC."""

    __tablename__ = "limit_increase_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    requested_per_txn_limit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_daily_limit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default=LimitIncreaseStatus.PENDING.value, index=True, nullable=False
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    approved_per_txn_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_daily_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Optional total debit allowance under the raised grant (minor units).
    spending_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount_spent: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    starts_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    reviewed_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
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
