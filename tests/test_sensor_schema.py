"""Unit tests for shared/schemas/sensor.py — SensorReading validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.schemas.sensor import SensorReading, SensorType, Unit

_TS_MS = 1_746_090_000_000   # 2025-05-01 10:00:00 UTC in epoch-ms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_payload(**overrides) -> dict:
    """Return a minimal valid SensorReading payload dict.

    The schema uses `ts` (int epoch-ms), not `timestamp` (ISO string).
    """
    base = {
        "sensor_id":   "temp-eng-01",
        "building_id": "ENG",
        "floor":       1,
        "room_id":     "ENG-101",
        "sensor_type": "temperature",
        "value":       22.5,
        "unit":        "celsius",
        "ts":          _TS_MS,
        "quality":     1.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

def test_valid_temperature_reading():
    r = SensorReading(**_valid_payload())
    assert r.sensor_type == SensorType.TEMPERATURE
    assert r.value == 22.5
    assert r.unit == Unit.CELSIUS


def test_valid_occupancy_reading():
    r = SensorReading(**_valid_payload(sensor_type="occupancy", value=42, unit="count"))
    assert r.sensor_type == SensorType.OCCUPANCY
    assert r.value == 42


def test_valid_energy_reading():
    r = SensorReading(**_valid_payload(sensor_type="energy", value=1500.0, unit="watt"))
    assert r.sensor_type == SensorType.ENERGY


def test_kafka_topic_derivation():
    r = SensorReading(**_valid_payload())
    assert r.kafka_topic == "sensors.temperature"


def test_kafka_key_is_building_id_bytes():
    r = SensorReading(**_valid_payload())
    assert isinstance(r.kafka_key, bytes)
    assert r.kafka_key == b"ENG"   # key is building_id, not room_id


def test_to_line_protocol_contains_measurement():
    r = SensorReading(**_valid_payload())
    lp = r.to_line_protocol(measurement="sensors")
    assert lp.startswith("sensors,")
    assert "value=" in lp
    assert "quality=" in lp


def test_line_protocol_timestamp_in_nanoseconds():
    r = SensorReading(**_valid_payload())
    lp = r.to_line_protocol()
    ts_ns_str = str(_TS_MS * 1_000_000)
    assert lp.endswith(ts_ns_str)


def test_json_round_trip():
    r = SensorReading(**_valid_payload())
    raw = r.model_dump_json()
    r2  = SensorReading.model_validate_json(raw)
    assert r == r2


# ---------------------------------------------------------------------------
# Validation rejection tests
# ---------------------------------------------------------------------------

def test_temperature_above_physical_max_rejected():
    with pytest.raises(ValidationError):
        SensorReading(**_valid_payload(value=200.0))   # above 60 °C ceiling


def test_temperature_below_physical_min_rejected():
    with pytest.raises(ValidationError):
        SensorReading(**_valid_payload(value=-50.0))   # below -10 °C floor


def test_negative_occupancy_rejected():
    with pytest.raises(ValidationError):
        SensorReading(**_valid_payload(sensor_type="occupancy", value=-1, unit="count"))


def test_negative_energy_rejected():
    with pytest.raises(ValidationError):
        SensorReading(**_valid_payload(sensor_type="energy", value=-5.0, unit="watt"))


def test_quality_out_of_range_rejected():
    with pytest.raises(ValidationError):
        SensorReading(**_valid_payload(quality=1.5))


def test_invalid_sensor_type_rejected():
    with pytest.raises(ValidationError):
        SensorReading(**_valid_payload(sensor_type="pressure"))


def test_missing_required_field_rejected():
    payload = _valid_payload()
    del payload["room_id"]
    with pytest.raises(ValidationError):
        SensorReading(**payload)


def test_invalid_unit_for_sensor_type_rejected():
    with pytest.raises(ValidationError):
        SensorReading(**_valid_payload(unit="watt"))   # watt invalid for temperature
