"""add event indexes

Revision ID: a1b2c3d4e5f6
Revises: 3b6e4c04bbee
Create Date: 2026-06-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '3b6e4c04bbee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 为高频查询字段添加索引
    op.create_index('ix_events_status', 'events', ['status'])
    op.create_index('ix_events_start_time', 'events', ['start_time'])
    op.create_index('ix_events_feishu_record_id', 'events', ['feishu_record_id'])


def downgrade() -> None:
    op.drop_index('ix_events_feishu_record_id', table_name='events')
    op.drop_index('ix_events_start_time', table_name='events')
    op.drop_index('ix_events_status', table_name='events')
