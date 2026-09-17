"""Alembic migration: campay_payments table for MoMo settlement details."""

from alembic import op
import sqlalchemy as sa


revision = "f2a3b4c5d6e7"
down_revision = "5c577bfdb6af"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campay_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("endpoint", sa.String(20), nullable=False, server_default="collect"),
        sa.Column("reference", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("mapped_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("amount", sa.String(40), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="XAF"),
        sa.Column("operator", sa.String(40), nullable=True),
        sa.Column("operator_reference", sa.String(80), nullable=True),
        sa.Column("external_reference", sa.String(80), nullable=True),
        sa.Column("phone_number", sa.String(32), nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campay_payments_reference", "campay_payments", ["reference"], unique=True)
    op.create_index("ix_campay_payments_transaction_id", "campay_payments", ["transaction_id"])
    op.create_index("ix_campay_payments_user_id", "campay_payments", ["user_id"])
    op.create_index("ix_campay_payments_external_reference", "campay_payments", ["external_reference"])
    op.create_index("ix_campay_payments_phone_number", "campay_payments", ["phone_number"])


def downgrade() -> None:
    op.drop_index("ix_campay_payments_phone_number", table_name="campay_payments")
    op.drop_index("ix_campay_payments_external_reference", table_name="campay_payments")
    op.drop_index("ix_campay_payments_user_id", table_name="campay_payments")
    op.drop_index("ix_campay_payments_transaction_id", table_name="campay_payments")
    op.drop_index("ix_campay_payments_reference", table_name="campay_payments")
    op.drop_table("campay_payments")
