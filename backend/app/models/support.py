import datetime as dt

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="general", nullable=False)
    # OPEN, IN_PROGRESS, RESOLVED, CLOSED
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)
    # Client context captured at submit time for admin triage.
    page_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
        nullable=False,
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("support_tickets.id"), index=True, nullable=False
    )
    # 'user' or 'agent'
    sender: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )


class TransactionDispute(Base):
    __tablename__ = "transaction_disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), index=True, nullable=False
    )
    reason: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # OPEN, UNDER_REVIEW, RESOLVED, REJECTED
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
