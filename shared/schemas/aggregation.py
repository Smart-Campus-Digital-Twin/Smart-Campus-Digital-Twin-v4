"""
Windowed aggregation result — output of the Flink WindowAggJob.

Written to InfluxDB bucket `campus_1m` by Flink and read by Spark for
hourly roll-up jobs and by the API for history endpoints.

Example wire format (Kafka topic sensors.aggregated, also written to InfluxDB):
{
    "building_id":   "EF",
    "room_id":       "EF101",
    "sensor_type":   "temperature",
    "window_start":  1745000000000,
    "window_end":    1745000060000,
    "min":           23.1,
    "max":           25.2,
    "avg":           24.3,
    "stddev":        0.42,
    "count":         12,
    "quality_avg":   0.98
}
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .sensor import SensorType


class AggregatedReading(BaseModel):
    """
    Statistics over one 1-minute tumbling window for a single (room, sensor_type) key.

    Only readings with quality >= 0.5 are included in the statistics.
    `count` reflects the number of included samples, not total messages received.
    `quality_avg` is the mean quality of included samples — drops below 1.0
    during sensor degradation events, useful for dashboard health indicators.
    """

    building_id:  str        = Field(..., description="e.g. 'EF'")
    floor:        int        = Field(..., ge=0, le=20)
    room_id:      str        = Field(..., description="e.g. 'EF101'")
    sensor_type:  SensorType
    window_start: int        = Field(..., description="Window open, Unix epoch ms")
    window_end:   int        = Field(..., description="Window close, Unix epoch ms")
    min:          float
    max:          float
    avg:          float
    stddev:       float      = Field(..., ge=0.0)
    count:        int        = Field(..., ge=1, description="Samples included (quality >= 0.5)")
    quality_avg:  float      = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def min_le_avg_le_max(self) -> AggregatedReading:
        if not (self.min <= self.avg <= self.max):
            raise ValueError(
                f"Aggregation invariant violated: min={self.min} <= "
                f"avg={self.avg} <= max={self.max} must hold"
            )
        return self

    @model_validator(mode="after")
    def window_start_before_end(self) -> AggregatedReading:
        if self.window_start >= self.window_end:
            raise ValueError("window_start must be strictly before window_end")
        return self

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str | bytes) -> AggregatedReading:
        return cls.model_validate_json(raw)

    def to_line_protocol(self, measurement: str = "sensor_1m") -> str:
        """
        InfluxDB line protocol for the campus_1m bucket.

        Tags  (indexed, low-cardinality): building_id, floor, room_id, sensor_type
        Fields (unindexed, high-cardinality): all statistics + count + quality_avg
        """
        tags = (
            f"building_id={self.building_id},"
            f"floor={self.floor},"
            f"room_id={self.room_id},"
            f"sensor_type={self.sensor_type}"
        )
        fields = (
            f"min={self.min},"
            f"max={self.max},"
            f"avg={self.avg},"
            f"stddev={self.stddev},"
            f"count={self.count}i,"   # integer field — explicit 'i' suffix
            f"quality_avg={self.quality_avg}"
        )
        ts_ns = self.window_start * 1_000_000
        return f"{measurement},{tags} {fields} {ts_ns}"
