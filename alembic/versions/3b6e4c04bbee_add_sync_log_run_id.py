"""add sync_log run_id

Revision ID: 3b6e4c04bbee
Revises: 7701d0eef212
Create Date: 2026-06-20 10:36:47.234256

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b6e4c04bbee'
down_revision: Union[str, Sequence[str], None] = '7701d0eef212'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add run_id column to sync_logs table."""
    with op.batch_alter_table('sync_logs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('run_id', sa.String(length=128), nullable=False, server_default=''),
        )
        batch_op.create_index(batch_op.f('ix_sync_logs_run_id'), ['run_id'], unique=False)


def downgrade() -> None:
    """Remove run_id column from sync_logs table."""
    with op.batch_alter_table('sync_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sync_logs_run_id'))
        batch_op.drop_column('run_id')
