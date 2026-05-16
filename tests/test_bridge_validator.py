"""Unit tests for bridge/validator.py — MQTTPayloadValidator."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from bridge.validator import MQTTPayloadValidator

_TS_MS = 1_746_090_000_000   # 2025-05-01 10:00:00 UTC in epoch-ms


@pytest.fixture()
def validator() -> MQTTPayloadValidator:
    return MQTTPayloadValidator()


def _encode(payload: dict) -> bytes:
    return json.dumps(payload).encode()


def _valid_payload(**overrides) -> dict:
    """Schema field is `ts` (int epoch-ms), not `timestamp` (ISO string)."""
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
# Valid payloads
# ---------------------------------------------------------------------------

def test_valid_temperature_parse(validator):
    raw = _encode(_valid_payload())
    msg = validator.parse("campus/ENG/ENG-101/temperature", raw)
    assert msg.reading.sensor_type.value == "temperature"
    assert msg.reading.value == 22.5


def test_valid_occupancy_parse(validator):
    raw = _encode(_valid_payload(sensor_type="occupancy", value=15, unit="count"))
    msg = validator.parse("campus/ENG/ENG-101/occupancy", raw)
    assert msg.reading.value == 15


def test_valid_energy_parse(validator):
    raw = _encode(_valid_payload(sensor_type="energy", value=800.0, unit="watt"))
    msg = validator.parse("campus/ENG/ENG-101/energy", raw)
    assert msg.reading.value == 800.0


def test_message_id_is_populated(validator):
    raw = _encode(_valid_payload())
    msg = validator.parse("campus/ENG/ENG-101/temperature", raw)
    assert msg.message_id is not None
    assert len(str(msg.message_id)) > 10


def test_mqtt_topic_preserved(validator):
    topic = "campus/ENG/ENG-101/temperature"
    raw   = _encode(_valid_payload())
    msg   = validator.parse(topic, raw)
    assert msg.mqtt_topic == topic


# ---------------------------------------------------------------------------
# Invalid payloads — must raise
# ---------------------------------------------------------------------------

def test_malformed_json_raises_value_error(validator):
    with pytest.raises(ValueError, match="[Jj][Ss][Oo][Nn]|[Pp]arse|[Dd]ecode"):
        validator.parse("campus/ENG/ENG-101/temperature", b"not-json")


def test_invalid_schema_raises_validation_error(validator):
    payload = _valid_payload()
    del payload["room_id"]
    with pytest.raises(ValidationError):
        validator.parse("campus/ENG/ENG-101/temperature", _encode(payload))


def test_temperature_out_of_range_raises(validator):
    with pytest.raises(ValidationError):
        validator.parse(
            "campus/ENG/ENG-101/temperature",
            _encode(_valid_payload(value=300.0)),
        )


def test_negative_occupancy_raises(validator):
    with pytest.raises(ValidationError):
        validator.parse(
            "campus/ENG/ENG-101/occupancy",
            _encode(_valid_payload(sensor_type="occupancy", value=-1, unit="count")),
        )


def test_empty_payload_raises(validator):
    with pytest.raises((ValueError, ValidationError)):
        validator.parse("campus/ENG/ENG-101/temperature", b"")


def test_wrong_unit_for_sensor_type_raises(validator):
    with pytest.raises(ValidationError):
        validator.parse(
            "campus/ENG/ENG-101/temperature",
            _encode(_valid_payload(unit="watt")),
        )
