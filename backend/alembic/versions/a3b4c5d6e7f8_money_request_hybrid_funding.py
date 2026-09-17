"""money request hybrid wallet/campay funding

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-17 10:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "money_requests",
        sa.Column("funding_mode", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "money_requests",
        sa.Column("payer_transaction_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "money_requests",
        sa.Column("collect_transaction_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_money_requests_payer_transaction_id",
        "money_requests",
        "transactions",
        ["payer_transaction_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_money_requests_collect_transaction_id",
        "money_requests",
        "transactions",
        ["collect_transaction_id"],
        ["id"],
    )
    op.create_index(
        "ix_money_requests_collect_transaction_id",
        "money_requests",
        ["collect_transaction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_money_requests_collect_transaction_id", table_name="money_requests")
    op.drop_constraint(
        "fk_money_requests_collect_transaction_id", "money_requests", type_="foreign_key"
    )
    op.drop_constraint(
        "fk_money_requests_payer_transaction_id", "money_requests", type_="foreign_key"
    )
    op.drop_column("money_requests", "collect_transaction_id")
    op.drop_column("money_requests", "payer_transaction_id")
    op.drop_column("money_requests", "funding_mode")
