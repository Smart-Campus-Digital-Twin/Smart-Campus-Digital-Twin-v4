"""
Kafka transport envelope — produced by the bridge, consumed by Flink.

The bridge wraps every validated SensorReading in this envelope before
writing it to Kafka. This gives all consumers three things for free:
  1. `message_id`  — UUID v4 for exactly-once deduplication without a
                      schema registry or external state store.
  2. `produced_at` — Wall-clock time the bridge forwarded the message,
                      separate from the sensor's own `ts`. Useful for
                      measuring end-to-end pipeline lag.
  3. `mqtt_topic`  — Source MQTT topic, preserved for debugging and
                      replay audits.

Example wire format (stored in Kafka bytes):
{
    "message_id":  "7b9c2d1e-4f3a-4b8c-9d0e-1f2a3b4c5d6e",
    "produced_at": "2025-05-03T10:30:00.123Z",
    "mqtt_topic":  "campus/EF/f1/EF101/temperature",
    "reading": { ...SensorReading... }
}
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from .sensor import SensorReading


class KafkaMessage(BaseModel):
    """
    Envelope written to Kafka topics sensors.temperature / .occupancy / .energy.

    Flink jobs unwrap `.reading` for processing and use `.message_id` to
    mark checkpoints in exactly-once mode.
    """

    message_id:  str           = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID v4 — deduplication key for Flink exactly-once sinks",
    )
    produced_at: datetime      = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC wall-clock when bridge forwarded this message to Kafka",
    )
    mqtt_topic:  str           = Field(
        ...,
        description="Source MQTT topic, e.g. campus/EF/f1/EF101/temperature",
    )
    reading:     SensorReading

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str | bytes) -> KafkaMessage:
        return cls.model_validate_json(raw)
