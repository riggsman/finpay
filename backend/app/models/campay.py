import datetime as dt

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class CampayPayment(Base):
    """Persisted Campay collect/withdraw details linked to a FinPay transaction."""

    __tablename__ = "campay_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), index=True, nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    # collect | withdraw
    endpoint: Mapped[str] = mapped_column(String(20), default="collect", nullable=False)
    # Campay UUID reference
    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    mapped_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    # Campay amount as returned (often major units, e.g. "25.00")
    amount: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # FinPay minor units when known from our txn
    amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="XAF", nullable=False)
    operator: Mapped[str | None] = mapped_column(String(40), nullable=True)
    operator_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set once when final SUCCESS/FAILED is first applied (idempotent emails).
    finalized_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    notified_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
        nullable=False,
    )
