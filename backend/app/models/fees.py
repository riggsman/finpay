import datetime as dt

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class FeeRule(Base):
    __tablename__ = "fee_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    # DEPOSIT, WITHDRAW, SEND_MONEY, ELECTRICITY, AIRTIME, DATA
    operation: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    # FLAT, PERCENTAGE, TIERED
    fee_type: Mapped[str] = mapped_column(String(20), default="FLAT", nullable=False)
    # JSON config: FLAT {"fee":F}; PERCENTAGE {"percent":P,"min_fee":m,"max_fee":M};
    # TIERED {"tiers":[{"min":a,"max":b,"fee":f}, ...]}  (all minor units)
    config: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
        nullable=False,
    )


class ServiceFlag(Base):
    __tablename__ = "service_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    # "service" (front-store tile), "operation" (money movement), or "notification"
    kind: Mapped[str] = mapped_column(String(20), default="service", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # When True, HIGH/CRITICAL notifications for this service are also emailed.
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
        nullable=False,
    )
