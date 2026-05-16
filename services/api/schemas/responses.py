"""
API response schemas — what the API sends to clients.

Separate from shared/schemas/ (which is the internal pipeline contract).
These schemas are optimised for readability in JSON responses:
  - timestamps as ISO-8601 strings (not epoch integers)
  - snake_case field names
  - optional fields documented with clear descriptions
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LiveReading(BaseModel):
    """Latest reading for a single sensor."""
    sensor_id:   str
    room_id:     str
    building_id: str
    floor:       int
    sensor_type: str
    value:       float
    unit:        str
    ts:          datetime
    quality:     float


class AggregatedPeriod(BaseModel):
    """One aggregated window (1-min, 1-hour, etc.)."""
    ts:          datetime   = Field(..., description="Window start time")
    room_id:     str
    building_id: str
    sensor_type: str
    min:         float
    max:         float
    avg:         float
    stddev:      float
    count:       int
    quality_avg: float


class BuildingResponse(BaseModel):
    id:       str
    name:     str
    lat:      float | None = None
    lon:      float | None = None
    floors:   int
    capacity: int


class RoomResponse(BaseModel):
    id:          str
    building_id: str
    floor:       int
    room_type:   str
    capacity:    int


class EnergyDailyResponse(BaseModel):
    date:         str   = Field(..., description="YYYY-MM-DD")
    building_id:  str
    total_kwh:    float
    peak_w:       float
    avg_w:        float
    sample_hours: int   = Field(..., description="< 24 means incomplete day")


class AnomalyResponse(BaseModel):
    anomaly_id:  str
    detected_at: datetime
    building_id: str
    room_id:     str
    sensor_type: str
    anomaly_type: str
    severity:    str
    value:       float
    threshold:   float
    message:     str


class PagedResponse(BaseModel):
    """Generic paginated wrapper."""
    total:  int
    offset: int
    limit:  int
    items:  list[Any]


class HealthResponse(BaseModel):
    status:   str          # "ok" | "degraded"
    influxdb: str          # "up" | "down"
    postgres: str          # "up" | "down"
    version:  str
