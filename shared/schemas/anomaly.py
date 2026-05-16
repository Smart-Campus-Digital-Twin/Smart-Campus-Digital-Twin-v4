"""
Anomaly event — emitted by the Flink AnomalyJob to two sinks:
  1. Kafka topic  `alerts.anomalies`  — for real-time alert consumers
  2. PostgreSQL   `anomalies` table   — for audit log and dashboard queries

Example wire format:
{
    "anomaly_id":   "c1d2e3f4-0000-0000-0000-000000000001",
    "detected_at":  "2025-05-03T10:31:00.000Z",
    "sensor_id":    "EF101-temp-0",
    "building_id":  "EF",
    "floor":        1,
    "room_id":      "EF101",
    "sensor_type":  "temperature",
    "anomaly_type": "threshold_breach",
    "severity":     "warning",
    "value":        39.5,
    "threshold":    38.0,
    "message":      "temperature 39.5 °C exceeds warning threshold 38.0 °C in EF101"
}
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from .sensor import SensorReading, SensorType

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AnomalyType(StrEnum):
    THRESHOLD_HIGH  = "threshold_high"    # value above upper bound
    THRESHOLD_LOW   = "threshold_low"     # value below lower bound
    SPIKE           = "spike"             # value > N × rolling average
    SENSOR_DROPOUT  = "sensor_dropout"    # gap in readings > 2× publish interval
    CAPACITY_BREACH = "capacity_breach"   # occupancy > room_capacity * 1.05


class Severity(StrEnum):
    INFO     = "info"      # FYI, no action required
    WARNING  = "warning"   # worth investigating
    CRITICAL = "critical"  # immediate action required


# Default severity mapping — overridden by rules loaded from PostgreSQL alert_rules.
DEFAULT_SEVERITY: dict[AnomalyType, Severity] = {
    AnomalyType.THRESHOLD_HIGH:  Severity.WARNING,
    AnomalyType.THRESHOLD_LOW:   Severity.WARNING,
    AnomalyType.SPIKE:           Severity.WARNING,
    AnomalyType.SENSOR_DROPOUT:  Severity.INFO,
    AnomalyType.CAPACITY_BREACH: Severity.CRITICAL,
}


# ---------------------------------------------------------------------------
# Anomaly model
# ---------------------------------------------------------------------------

class AnomalyEvent(BaseModel):
    """
    A single anomaly detected by the Flink AnomalyJob.

    anomaly_id   — UUID v4 for deduplication in PostgreSQL UPSERT.
    detected_at  — UTC wall-clock when Flink fired the rule.
    sensor_id    — Physical sensor that triggered the rule.
    building_id  — For dashboard filtering without a join.
    floor        — For dashboard filtering without a join.
    room_id      — For dashboard filtering without a join.
    sensor_type  — For rule routing.
    anomaly_type — Enum: what rule was violated.
    severity     — info / warning / critical.
    value        — Actual measurement that triggered the rule.
    threshold    — The rule threshold that was crossed.
    message      — Human-readable one-line description for alert UIs.
    """

    anomaly_id:  str         = Field(default_factory=lambda: str(uuid.uuid4()))
    detected_at: datetime    = Field(
        default_factory=lambda: datetime.now(UTC)
    )
    sensor_id:   str
    building_id: str
    floor:       int         = Field(..., ge=0, le=20)
    room_id:     str
    sensor_type: SensorType
    anomaly_type: AnomalyType
    severity:    Severity
    value:       float
    threshold:   float
    message:     str         = Field(..., min_length=1)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str | bytes) -> AnomalyEvent:
        return cls.model_validate_json(raw)

    def to_line_protocol(self, measurement: str = "anomalies") -> str:
        """Convert anomaly to InfluxDB line protocol format."""
        tags = [
            f"sensor_id={self.sensor_id}",
            f"building_id={self.building_id}",
            f"floor={self.floor}",
            f"room_id={self.room_id}",
            f"sensor_type={self.sensor_type}",
            f"anomaly_type={self.anomaly_type}",
            f"severity={self.severity}",
        ]
        fields = [
            f"value={self.value}",
            f"threshold={self.threshold}",
        ]
        timestamp_ns = int(self.detected_at.timestamp() * 1_000_000_000)
        return f"{measurement},{','.join(tags)} {','.join(fields)} {timestamp_ns}"

    # ------------------------------------------------------------------
    # Factory helpers — used by the Flink AnomalyJob rule engine
    # ------------------------------------------------------------------

    @classmethod
    def threshold_breach(
        cls,
        reading: SensorReading,  # type: ignore[name-defined]
        *,
        threshold: float,
        high: bool,
        severity: Severity | None = None,
    ) -> AnomalyEvent:
        atype = AnomalyType.THRESHOLD_HIGH if high else AnomalyType.THRESHOLD_LOW
        direction = "exceeds" if high else "falls below"
        return cls(
            detected_at = datetime.fromtimestamp(reading.ts / 1000, tz=UTC),
            sensor_id   = reading.sensor_id,
            building_id = reading.building_id,
            floor       = reading.floor,
            room_id     = reading.room_id,
            sensor_type = reading.sensor_type,
            anomaly_type = atype,
            severity    = severity or DEFAULT_SEVERITY[atype],
            value       = reading.value,
            threshold   = threshold,
            message     = (
                f"{reading.sensor_type} {reading.value} {direction} "
                f"{atype.replace('_', ' ')} {threshold} in {reading.room_id}"
            ),
        )

    @classmethod
    def capacity_breach(
        cls,
        reading: SensorReading,  # type: ignore[name-defined]
        *,
        room_capacity: int,
    ) -> AnomalyEvent:
        threshold = room_capacity * 1.05
        return cls(
            detected_at  = datetime.fromtimestamp(reading.ts / 1000, tz=UTC),
            sensor_id    = reading.sensor_id,
            building_id  = reading.building_id,
            floor        = reading.floor,
            room_id      = reading.room_id,
            sensor_type  = reading.sensor_type,
            anomaly_type = AnomalyType.CAPACITY_BREACH,
            severity     = Severity.CRITICAL,
            value        = reading.value,
            threshold    = threshold,
            message      = (
                f"Occupancy {int(reading.value)} exceeds 105% capacity "
                f"({room_capacity}) in {reading.room_id}"
            ),
        )

    @classmethod
    def spike(
        cls,
        reading: SensorReading,  # type: ignore[name-defined]
        *,
        rolling_avg: float,
        multiplier: float,
    ) -> AnomalyEvent:
        threshold = rolling_avg * multiplier
        return cls(
            detected_at  = datetime.fromtimestamp(reading.ts / 1000, tz=UTC),
            sensor_id    = reading.sensor_id,
            building_id  = reading.building_id,
            floor        = reading.floor,
            room_id      = reading.room_id,
            sensor_type  = reading.sensor_type,
            anomaly_type = AnomalyType.SPIKE,
            severity     = DEFAULT_SEVERITY[AnomalyType.SPIKE],
            value        = reading.value,
            threshold    = threshold,
            message      = (
                f"{reading.sensor_type} spike: {reading.value:.1f} is "
                f"{reading.value / rolling_avg:.1f}× the 5-min rolling average "
                f"({rolling_avg:.1f}) in {reading.room_id}"
            ),
        )
