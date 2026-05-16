"""
Pydantic v2 request/response schemas — the API's public contract.

threejs_node_id is included in every room-level response so the frontend
can call scene.getObjectByName(threejs_node_id) without a secondary lookup.

status values map to Three.js emissive colours:
  ok=0x00C875  warning=0xF5A623  critical=0xE84040  unknown=0x888888
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------

class BuildingOut(_Base):
    id: uuid.UUID = Field(description="Building UUID", example="550e8400-e29b-41d4-a716-446655440000")
    name: str = Field(description="Human-readable building name", example="Engineering Tower A")
    address: str | None = Field(None, description="Street address")
    lat: float | None = Field(None, description="WGS-84 latitude", example=6.7956)
    lng: float | None = Field(None, description="WGS-84 longitude", example=79.9012)
    floors: int = Field(description="Number of floors", example=5)
    created_at: datetime


class BuildingWithRoomsOut(BuildingOut):
    rooms: list[RoomOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

class RoomOut(_Base):
    id: uuid.UUID = Field(description="Room UUID")
    building_id: uuid.UUID
    name: str = Field(example="Lab 3-04")
    floor: int = Field(example=3)
    area_sqm: float | None = Field(None, description="Floor area in m²", example=45.0)
    room_type: str = Field(example="laboratory")
    threejs_node_id: str | None = Field(
        None,
        description="Stable identifier used with scene.getObjectByName() in Three.js",
        example="room_lab_304",
    )
    created_at: datetime


# ---------------------------------------------------------------------------
# Sensor readings (from InfluxDB)
# ---------------------------------------------------------------------------

class FieldReading(BaseModel):
    value: float = Field(description="Raw sensor value", example=22.5)
    unit: str = Field(description="Engineering unit", example="°C")
    status: str = Field(description="ok | warning | critical | unknown", example="ok")
    emissive: int = Field(description="Three.js hex emissive colour", example=0x00C875)


class SensorReading(BaseModel):
    """Latest multi-field reading for a single room."""
    room_id: str = Field(example="a1b2c3d4-...")
    building_id: str
    threejs_node_id: str | None = Field(
        None, description="Passed through so frontend needs no lookup"
    )
    ts: datetime | None = Field(None, description="Timestamp of most recent measurement")
    data: dict[str, FieldReading] = Field(
        description="Keyed by field name: temperature, humidity, co2, occupancy, power_kw, lux",
        example={
            "temperature": {"value": 22.5, "unit": "°C", "status": "ok", "emissive": 0x00C875},
            "occupancy":   {"value": 75.0, "unit": "%", "status": "warning", "emissive": 0xF5A623},
        },
    )


class SensorHistoryPoint(BaseModel):
    ts: datetime
    room_id: str
    building_id: str
    sensor_type: str
    min: float | None = None
    max: float | None = None
    avg: float | None = None
    stddev: float | None = None
    count: int | None = None


# ---------------------------------------------------------------------------
# Building summary
# ---------------------------------------------------------------------------

class FloorSummary(BaseModel):
    floor: int
    avg_temp: float | None
    avg_humidity: float | None
    room_count: int
    alert_count: int


class BuildingSummary(BaseModel):
    building_id: uuid.UUID
    avg_temp: float | None = Field(None, example=23.1)
    avg_humidity: float | None = Field(None, example=55.2)
    avg_occupancy: float | None = Field(None, example=62.0)
    total_power_kw: float | None = Field(None, example=48.3)
    alert_count: int = Field(0, example=2)
    room_count: int = Field(0)
    floor_summaries: list[FloorSummary] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertOut(_Base):
    id: uuid.UUID
    room_id: uuid.UUID
    building_id: uuid.UUID
    severity: str = Field(description="info | warning | critical", example="warning")
    message: str = Field(example="Temperature exceeded 30 °C in Lab 3-04")
    resolved: bool
    created_at: datetime
    resolved_at: datetime | None = None
    threejs_node_id: str | None = Field(
        None, description="For immediate 3D mesh highlight on alert receipt"
    )


class AlertResolveOut(AlertOut):
    pass


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PageMeta(BaseModel):
    total: int
    offset: int
    limit: int


class PagedAlerts(BaseModel):
    meta: PageMeta
    items: list[AlertOut]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class DBStatus(BaseModel):
    status: str = Field(description="up | down")
    latency_ms: float | None = None


class HealthOut(BaseModel):
    status: str = Field(description="ok | degraded")
    influxdb: DBStatus
    postgres: DBStatus
    version: str
    auth_mode: str = Field(description="keycloak | hs256-dev")
