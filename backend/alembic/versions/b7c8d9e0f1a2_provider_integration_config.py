"""extend service_providers for configurable integrations

Revision ID: b7c8d9e0f1a2
Revises: 0057a1c0b286
Create Date: 2026-09-16 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "0057a1c0b286"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("service_providers", sa.Column("description", sa.String(length=255), nullable=True))
    op.add_column(
        "service_providers",
        sa.Column("flow", sa.String(length=20), nullable=False, server_default="direct_topup"),
    )
    op.add_column(
        "service_providers",
        sa.Column("integration_mode", sa.String(length=20), nullable=False, server_default="MOCK"),
    )
    op.add_column("service_providers", sa.Column("base_url", sa.String(length=255), nullable=True))
    op.add_column(
        "service_providers",
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "service_providers",
        sa.Column(
            "target_label",
            sa.String(length=80),
            nullable=False,
            server_default="Account / phone number",
        ),
    )
    op.add_column("service_providers", sa.Column("icon", sa.String(length=40), nullable=True))
    op.add_column(
        "service_providers",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column(
        "service_providers",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill timestamps and electricity flow defaults.
    op.execute(
        "UPDATE service_providers SET updated_at = created_at WHERE updated_at IS NULL"
    )
    op.execute(
        "UPDATE service_providers SET flow = 'validate_pay', "
        "target_label = 'Meter number' WHERE category = 'electricity'"
    )
    op.execute(
        "UPDATE service_providers SET target_label = 'Phone number' "
        "WHERE category IN ('airtime', 'data')"
    )


def downgrade() -> None:
    op.drop_column("service_providers", "updated_at")
    op.drop_column("service_providers", "sort_order")
    op.drop_column("service_providers", "icon")
    op.drop_column("service_providers", "target_label")
    op.drop_column("service_providers", "config_json")
    op.drop_column("service_providers", "base_url")
    op.drop_column("service_providers", "integration_mode")
    op.drop_column("service_providers", "flow")
    op.drop_column("service_providers", "description")
