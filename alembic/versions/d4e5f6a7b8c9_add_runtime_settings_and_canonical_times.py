"""add runtime settings and canonical event times

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-07-11 19:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d4e5f6a7b8c9"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    event_columns = {column["name"] for column in inspector.get_columns("events")}
    event_indexes = {index["name"] for index in inspector.get_indexes("events")}
    with op.batch_alter_table("events") as batch_op:
        if "start_at" not in event_columns:
            batch_op.add_column(sa.Column("start_at", sa.DateTime(), nullable=True))
        if "end_at" not in event_columns:
            batch_op.add_column(sa.Column("end_at", sa.DateTime(), nullable=True))
        if "timezone" not in event_columns:
            batch_op.add_column(sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Shanghai"))
        if "raw_time_text" not in event_columns:
            batch_op.add_column(sa.Column("raw_time_text", sa.Text(), nullable=False, server_default=""))
        if "ix_events_start_at" not in event_indexes:
            batch_op.create_index("ix_events_start_at", ["start_at"], unique=False)
        if "ix_events_end_at" not in event_indexes:
            batch_op.create_index("ix_events_end_at", ["end_at"], unique=False)

    if "app_settings" not in inspector.get_table_names():
        op.create_table(
            "app_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("value", sa.Text(), nullable=False, server_default=""),
            sa.Column("value_type", sa.String(length=32), nullable=False, server_default="string"),
            sa.Column("category", sa.String(length=64), nullable=False, server_default="general"),
            sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("requires_restart", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key"),
        )
    app_setting_indexes = set()
    if "app_settings" in inspect(op.get_bind()).get_table_names():
        app_setting_indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("app_settings")}
    if "ix_app_settings_key" not in app_setting_indexes:
        op.create_index("ix_app_settings_key", "app_settings", ["key"], unique=False)

    _backfill_event_datetimes()


def downgrade() -> None:
    op.drop_index("ix_app_settings_key", table_name="app_settings")
    op.drop_table("app_settings")
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_index("ix_events_end_at")
        batch_op.drop_index("ix_events_start_at")
        batch_op.drop_column("raw_time_text")
        batch_op.drop_column("timezone")
        batch_op.drop_column("end_at")
        batch_op.drop_column("start_at")


def _backfill_event_datetimes() -> None:
    from datetime import datetime, timezone

    from sqlalchemy import MetaData, Table, select

    from app.utils.time import parse_datetime_str

    bind = op.get_bind()
    metadata = MetaData()
    events = Table(
        "events",
        metadata,
        sa.Column("id", sa.Integer),
        sa.Column("start_time", sa.String(length=128)),
        sa.Column("end_time", sa.String(length=128)),
        sa.Column("start_at", sa.DateTime()),
        sa.Column("end_at", sa.DateTime()),
        sa.Column("raw_time_text", sa.Text()),
        sa.Column("timezone", sa.String(length=64)),
    )

    rows = bind.execute(select(events.c.id, events.c.start_time, events.c.end_time)).fetchall()
    for row in rows:
        values: dict[str, object] = {"timezone": "Asia/Shanghai"}
        if row.start_time:
            start_dt = parse_datetime_str(row.start_time)
            if start_dt:
                values["start_at"] = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
        if row.end_time:
            end_dt = parse_datetime_str(row.end_time)
            if end_dt:
                values["end_at"] = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
        raw_parts = [part for part in [row.start_time, row.end_time] if part]
        values["raw_time_text"] = "\n".join(raw_parts)
        bind.execute(events.update().where(events.c.id == row.id).values(**values))
