"""Add persistent Feishu retry state.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-13 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("events")}
    indexes = {index["name"] for index in inspector.get_indexes("events")}
    with op.batch_alter_table("events") as batch_op:
        if "feishu_retry_count" not in columns:
            batch_op.add_column(sa.Column("feishu_retry_count", sa.Integer(), nullable=False, server_default="0"))
        if "feishu_next_retry_at" not in columns:
            batch_op.add_column(sa.Column("feishu_next_retry_at", sa.DateTime(), nullable=True))
        if "feishu_last_error" not in columns:
            batch_op.add_column(sa.Column("feishu_last_error", sa.Text(), nullable=False, server_default=""))
        if "ix_events_feishu_next_retry_at" not in indexes:
            batch_op.create_index("ix_events_feishu_next_retry_at", ["feishu_next_retry_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_index("ix_events_feishu_next_retry_at")
        batch_op.drop_column("feishu_last_error")
        batch_op.drop_column("feishu_next_retry_at")
        batch_op.drop_column("feishu_retry_count")
