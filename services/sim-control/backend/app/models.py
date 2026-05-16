from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SensorType(StrEnum):
    TEMPERATURE = "temperature"
    OCCUPANCY = "occupancy"
    ENERGY = "energy"


class BehaviorMode(StrEnum):
    NORMAL = "normal"
    RANDOM = "random"
    PATTERN = "pattern"
    ANOMALY = "anomaly"


class SensorConfig(BaseModel):
    min_value: float = 0.0
    max_value: float = 100.0
    interval_ms: int = 5000
    pattern: list[float] = Field(default_factory=list)
    anomaly_prob: float = 0.05


class Sensor(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    building_id: str
    floor: int = 0
    room_id: str
    sensor_type: SensorType
    enabled: bool = True
    behavior_mode: BehaviorMode = BehaviorMode.NORMAL
    config: SensorConfig = Field(default_factory=SensorConfig)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class RuleCondition(BaseModel):
    sensor_id: str
    operator: str = "gt"
    threshold: float = 0.0


class RuleAction(BaseModel):
    type: str = "set_value"
    target_sensor_id: str = ""
    value: float = 0.0
    enable: bool | None = None


class Rule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    enabled: bool = True
    condition: RuleCondition
    action: RuleAction
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class LogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    sensor_id: str = ""
    sensor_name: str = ""
    action: str
    details: str = ""
    value: float | None = None


class SensorReadingOut(BaseModel):
    sensor_id: str
    building_id: str
    floor: int
    room_id: str
    sensor_type: str
    value: float
    unit: str
    timestamp_ms: int
    timestamp: str
    quality: float = 1.0
    behavior_mode: str = "normal"
    metadata: dict[str, Any] = Field(default_factory=dict)
