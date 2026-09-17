"""kyc id document back capture

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-16 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kyc_profiles",
        sa.Column("id_document_back_ref", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("kyc_profiles", "id_document_back_ref")
