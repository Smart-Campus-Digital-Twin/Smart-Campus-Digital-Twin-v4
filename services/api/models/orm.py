"""SQLAlchemy 2.x ORM — buildings, rooms, sensors, alerts."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    floors: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rooms: Mapped[list[Room]] = relationship("Room", back_populates="building", lazy="raise")


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (Index("ix_rooms_building_id", "building_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    building_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    area_sqm: Mapped[float | None] = mapped_column(Float)
    room_type: Mapped[str] = mapped_column(String(64), nullable=False, default="generic")
    threejs_node_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    building: Mapped[Building] = relationship("Building", back_populates="rooms", lazy="raise")
    sensors: Mapped[list[Sensor]] = relationship("Sensor", back_populates="room", lazy="raise")
    alerts: Mapped[list[Alert]] = relationship("Alert", back_populates="room", lazy="raise")


class Sensor(Base):
    __tablename__ = "sensors"
    __table_args__ = (Index("ix_sensors_room_id", "room_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    sensor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    influx_tag_value: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    room: Mapped[Room] = relationship("Room", back_populates="sensors", lazy="raise")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_room_resolved", "room_id", "resolved"),
        Index("ix_alerts_building_resolved", "building_id", "resolved"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    building_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # info|warning|critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    room: Mapped[Room] = relationship("Room", back_populates="alerts", lazy="raise")
