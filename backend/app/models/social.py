import datetime as dt

from sqlalchemy import BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class Beneficiary(Base):
    __tablename__ = "beneficiaries"
    __table_args__ = (
        UniqueConstraint("user_id", "beneficiary_user_id", name="uq_beneficiary_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    beneficiary_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )


class MoneyRequest(Base):
    __tablename__ = "money_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    payer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="XAF", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # PENDING | PROCESSING | PAID | DECLINED | CANCELLED | FAILED
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    # WALLET | CAMPAY once the payer has validated
    funding_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Requester-side history row (MONEY_REQUEST_OUT → TRANSFER_RECEIVED on settle)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    # Payer-side history row (MONEY_REQUEST_IN → SEND_MONEY on wallet settle)
    payer_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    # Campay collect txn on the payer when funding_mode=CAMPAY
    collect_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), index=True, nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
