"""add archive fields

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 新增 user_participate 字段（用户标记"我参与了"）
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("events")}
    if 'user_participate' not in columns:
        op.add_column('events', sa.Column('user_participate', sa.Boolean(), nullable=False, server_default='0'))
    # 新增 archived_at 字段（归档时间）
    if 'archived_at' not in columns:
        op.add_column('events', sa.Column('archived_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('events', 'archived_at')
    op.drop_column('events', 'user_participate')
