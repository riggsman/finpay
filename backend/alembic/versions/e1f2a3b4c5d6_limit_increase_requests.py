"""Alembic migration: limit_increase_requests table."""

from alembic import op
import sqlalchemy as sa


revision = "e1f2a3b4c5d6"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "limit_increase_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("requested_per_txn_limit", sa.BigInteger(), nullable=False),
        sa.Column("requested_daily_limit", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("approved_per_txn_limit", sa.BigInteger(), nullable=True),
        sa.Column("approved_daily_limit", sa.BigInteger(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("spending_cap", sa.BigInteger(), nullable=True),
        sa.Column("amount_spent", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_admin_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_limit_increase_requests_user_id", "limit_increase_requests", ["user_id"])
    op.create_index("ix_limit_increase_requests_status", "limit_increase_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_limit_increase_requests_status", table_name="limit_increase_requests")
    op.drop_index("ix_limit_increase_requests_user_id", table_name="limit_increase_requests")
    op.drop_table("limit_increase_requests")
