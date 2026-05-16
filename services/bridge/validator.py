"""
MQTT payload validator — the gateway between raw bytes and the canonical schema.

All validation happens here. The bridge main loop calls validate() and receives
either a SensorReading (valid) or raises ValidationError (invalid → DLQ).

Normalisation handled here:
  - simulator unit symbols (°C, W) → canonical strings (celsius, watt)
  - timestamp_ms → ts  (simulator uses timestamp_ms; canonical schema uses ts)
  - reading_id injected if absent
"""

from __future__ import annotations

import json
import logging

from shared.schemas import KafkaMessage, SensorReading

logger = logging.getLogger(__name__)


class MQTTPayloadValidator:
    """Stateless validator; safe to call concurrently."""

    # Simulator publishes °C and W; canonical schema uses full words.
    _UNIT_MAP: dict[str, str] = {
        "°C":    "celsius",
        "count": "count",
        "W":     "watt",
    }

    def parse(self, mqtt_topic: str, raw_bytes: bytes) -> KafkaMessage:
        """
        Parse and validate an MQTT payload.

        Returns a KafkaMessage ready to be serialised and sent to Kafka.
        Raises ValueError  for malformed JSON.
        Raises ValidationError for schema violations — caller routes to DLQ.
        """
        try:
            payload: dict = json.loads(raw_bytes)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Non-JSON payload on {mqtt_topic}: {exc}") from exc

        # Normalise fields that differ between simulator output and canonical schema.
        payload = self._normalise(payload)

        reading = SensorReading(**payload)  # raises ValidationError on bad data

        return KafkaMessage(
            mqtt_topic = mqtt_topic,
            reading    = reading,
        )

    def _normalise(self, payload: dict) -> dict:
        """Map simulator field names and unit symbols to canonical equivalents."""
        out = dict(payload)

        # timestamp_ms → ts
        if "timestamp_ms" in out and "ts" not in out:
            out["ts"] = out.pop("timestamp_ms")

        # Unit symbols → canonical strings
        if "unit" in out:
            out["unit"] = self._UNIT_MAP.get(out["unit"], out["unit"])

        return out
