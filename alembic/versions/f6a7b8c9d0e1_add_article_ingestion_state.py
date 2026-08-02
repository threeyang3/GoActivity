"""Add article ingestion decision state.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-15 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("articles")}
    indexes = {index["name"] for index in inspector.get_indexes("articles")}
    with op.batch_alter_table("articles") as batch_op:
        if "ingestion_status" not in columns:
            batch_op.add_column(
                sa.Column("ingestion_status", sa.String(length=32), nullable=False, server_default="ingested")
            )
        if "ingestion_reason" not in columns:
            batch_op.add_column(
                sa.Column("ingestion_reason", sa.String(length=255), nullable=False, server_default="")
            )
        if "ix_articles_ingestion_status" not in indexes:
            batch_op.create_index("ix_articles_ingestion_status", ["ingestion_status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("articles") as batch_op:
        batch_op.drop_index("ix_articles_ingestion_status")
        batch_op.drop_column("ingestion_reason")
        batch_op.drop_column("ingestion_status")
