"""phone name lookup cache

Revision ID: 5c577bfdb6af
Revises: e1f2a3b4c5d6
Create Date: 2026-09-16 17:59:15.101069

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5c577bfdb6af'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('phone_name_lookups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=32), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('operator', sa.String(length=40), nullable=True),
    sa.Column('raw_response', sa.Text(), nullable=True),
    sa.Column('lookup_count', sa.Integer(), nullable=False),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('phone', 'provider', name='uq_phone_name_lookup')
    )
    op.create_index(op.f('ix_phone_name_lookups_phone'), 'phone_name_lookups', ['phone'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_phone_name_lookups_phone'), table_name='phone_name_lookups')
    op.drop_table('phone_name_lookups')