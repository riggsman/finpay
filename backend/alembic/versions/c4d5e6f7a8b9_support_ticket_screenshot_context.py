"""support ticket screenshot and issue context

Revision ID: c4d5e6f7a8b9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-17 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("support_tickets", sa.Column("page_url", sa.String(length=500), nullable=True))
    op.add_column("support_tickets", sa.Column("user_agent", sa.String(length=500), nullable=True))
    op.add_column("support_tickets", sa.Column("context_json", sa.Text(), nullable=True))
    op.add_column(
        "support_tickets", sa.Column("screenshot_path", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("support_tickets", "screenshot_path")
    op.drop_column("support_tickets", "context_json")
    op.drop_column("support_tickets", "user_agent")
    op.drop_column("support_tickets", "page_url")
