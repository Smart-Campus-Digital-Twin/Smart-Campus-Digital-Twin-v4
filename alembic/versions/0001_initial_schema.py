"""Initial schema — buildings, rooms, sensors, alerts.

Revision ID: 0001
Revises:
Create Date: 2026-05-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "buildings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("address", sa.String(255)),
        sa.Column("lat", sa.Float()),
        sa.Column("lng", sa.Float()),
        sa.Column("floors", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("building_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("area_sqm", sa.Float()),
        sa.Column("room_type", sa.String(64), nullable=False, server_default="generic"),
        sa.Column("threejs_node_id", sa.String(64), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_rooms_building_id", "rooms", ["building_id"])

    op.create_table(
        "sensors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("room_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sensor_type", sa.String(64), nullable=False),
        sa.Column("influx_tag_value", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_sensors_room_id", "sensors", ["room_id"])

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("room_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("building_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_alerts_room_resolved", "alerts", ["room_id", "resolved"])
    op.create_index("ix_alerts_building_resolved", "alerts", ["building_id", "resolved"])


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("sensors")
    op.drop_table("rooms")
    op.drop_table("buildings")
