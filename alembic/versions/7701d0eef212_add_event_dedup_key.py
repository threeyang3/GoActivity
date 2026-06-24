"""add event dedup_key

Revision ID: 7701d0eef212
Revises: b3b280a6e3b8
Create Date: 2026-06-20 10:26:44.036825

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7701d0eef212'
down_revision: Union[str, Sequence[str], None] = 'b3b280a6e3b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add dedup_key column to events table."""
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('dedup_key', sa.String(length=255), nullable=False, server_default=''),
        )
        batch_op.create_index(batch_op.f('ix_events_dedup_key'), ['dedup_key'], unique=False)


def downgrade() -> None:
    """Remove dedup_key column from events table."""
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_events_dedup_key'))
        batch_op.drop_column('dedup_key')
