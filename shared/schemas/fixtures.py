"""
Test fixtures — deterministic, minimal examples of every schema type.

Import in unit tests and integration tests.  Each function returns a
fresh model instance (no shared mutable state) so tests are independent.

Usage:
    from shared.schemas.fixtures import temp_reading, kafka_message, aggregation, anomaly

    def test_bridge_validates():
        r = temp_reading()
        assert r.sensor_type == SensorType.TEMPERATURE
"""

from __future__ import annotations

from .aggregation import AggregatedReading
from .anomaly import AnomalyEvent
from .kafka import KafkaMessage
from .sensor import SensorReading, SensorType, Unit


def temp_reading(
    *,
    building_id: str = "EF",
    room_id: str = "EF101",
    value: float = 24.3,
    ts: int = 1_745_000_000_000,
    quality: float = 1.0,
) -> SensorReading:
    return SensorReading(
        sensor_id   = f"{room_id}-temp-0",
        building_id = building_id,
        floor       = 1,
        room_id     = room_id,
        sensor_type = SensorType.TEMPERATURE,
        value       = value,
        unit        = Unit.CELSIUS,
        ts          = ts,
        quality     = quality,
    )


def occ_reading(
    *,
    building_id: str = "EF",
    room_id: str = "EF101",
    value: float = 42.0,
    ts: int = 1_745_000_000_000,
) -> SensorReading:
    return SensorReading(
        sensor_id   = f"{room_id}-occ-0",
        building_id = building_id,
        floor       = 1,
        room_id     = room_id,
        sensor_type = SensorType.OCCUPANCY,
        value       = value,
        unit        = Unit.COUNT,
        ts          = ts,
    )


def energy_reading(
    *,
    building_id: str = "EF",
    room_id: str = "EF101",
    value: float = 1200.0,
    ts: int = 1_745_000_000_000,
) -> SensorReading:
    return SensorReading(
        sensor_id   = f"{room_id}-energy-0",
        building_id = building_id,
        floor       = 1,
        room_id     = room_id,
        sensor_type = SensorType.ENERGY,
        value       = value,
        unit        = Unit.WATT,
        ts          = ts,
    )


def kafka_message(reading: SensorReading | None = None) -> KafkaMessage:
    r = reading or temp_reading()
    return KafkaMessage(
        mqtt_topic = f"campus/{r.building_id}/f{r.floor}/{r.room_id}/{r.sensor_type}",
        reading    = r,
    )


def aggregation(
    *,
    building_id: str = "EF",
    room_id: str = "EF101",
    window_start: int = 1_745_000_000_000,
) -> AggregatedReading:
    return AggregatedReading(
        building_id  = building_id,
        floor        = 1,
        room_id      = room_id,
        sensor_type  = SensorType.TEMPERATURE,
        window_start = window_start,
        window_end   = window_start + 60_000,
        min          = 23.1,
        max          = 25.2,
        avg          = 24.3,
        stddev       = 0.42,
        count        = 12,
        quality_avg  = 0.98,
    )


def anomaly_event(reading: SensorReading | None = None) -> AnomalyEvent:
    r = reading or temp_reading(value=39.5)
    return AnomalyEvent.threshold_breach(r, threshold=38.0, high=True)
