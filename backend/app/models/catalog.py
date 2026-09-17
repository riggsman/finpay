import datetime as dt

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class ServiceProvider(Base):
    """Catalog entry for a billable / top-up provider.

    New providers are added from the Back Office without code changes.
    ``flow`` controls how the front store integrates them:
      - validate_pay: meter/account validation then pay (e.g. electricity)
      - direct_topup: amount + target + PIN (e.g. airtime / data / water)
    ``integration_mode`` selects the runtime adapter (MOCK today, HTTP later).
    """

    __tablename__ = "service_providers"
    __table_args__ = (
        UniqueConstraint("category", "provider_id", name="uq_provider_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    provider_id: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # validate_pay | direct_topup
    flow: Mapped[str] = mapped_column(String(20), default="direct_topup", nullable=False)
    # MOCK | HTTP
    integration_mode: Mapped[str] = mapped_column(String(20), default="MOCK", nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Free-form JSON: api_key_ref, headers, field maps, timeout, etc.
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    target_label: Mapped[str] = mapped_column(
        String(80), default="Account / phone number", nullable=False
    )
    icon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
        nullable=False,
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(10), default="str", nullable=False)
    label: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
        nullable=False,
    )
