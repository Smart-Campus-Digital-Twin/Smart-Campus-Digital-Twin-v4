"""Unit tests for the AnomalyDetector rule logic in processing/flink/jobs/anomaly.py."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from shared.schemas.sensor import SensorType

# ---------------------------------------------------------------------------
# Helpers — build minimal SensorReading objects without Flink state
# ---------------------------------------------------------------------------

def _reading(sensor_type: str, value: float, room_id: str = "ENG-101") -> MagicMock:
    """Return a mock that behaves like a SensorReading for rule-checking."""
    r = MagicMock()
    r.sensor_type = SensorType(sensor_type)
    r.value       = value
    r.room_id     = room_id
    r.sensor_id   = f"{sensor_type}-01"
    r.building_id = "ENG"
    r.floor       = 1
    r.unit        = MagicMock()
    r.timestamp   = datetime(2025, 5, 1, 10, 0, 0, tzinfo=UTC)
    r.quality     = 1.0
    return r


_DEFAULT_RULES = {
    ("temperature", "threshold_high"): {"threshold": 38.0, "severity": "warning"},
    ("temperature", "threshold_low"):  {"threshold": 14.0, "severity": "warning"},
    ("energy",      "spike"):          {"threshold": 3.0,  "severity": "warning"},
    ("occupancy",   "capacity_breach"):{"threshold": 1.05, "severity": "critical"},
}

_DEFAULT_CAPACITIES = {"ENG-101": 40}


# ---------------------------------------------------------------------------
# Import AnomalyDetector after patching Flink's runtime environment
# ---------------------------------------------------------------------------

@pytest.fixture()
def detector():
    """Return an AnomalyDetector instance with Flink state mocked out."""
    import sys
    from unittest.mock import MagicMock
    for mod in [
        "psycopg2",
        "psycopg2.extras",
        "psycopg2.extensions",
        "pyflink",
        "pyflink.common",
        "pyflink.datastream",
        "pyflink.datastream.connectors",
        "pyflink.datastream.connectors.kafka",
        "pyflink.datastream.functions",
        "pyflink.datastream.state",
    ]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    sys.modules["pyflink.datastream.functions"].KeyedProcessFunction = object

    # Import the module so it exists as an attribute on processing.flink.jobs
    import processing.flink.jobs.anomaly  # noqa: F401

    # Patch the Flink state so we do not need a JVM
    with patch("processing.flink.jobs.anomaly.StateTtlConfig"), \
         patch("processing.flink.jobs.anomaly.ValueStateDescriptor"):
        from processing.flink.jobs.anomaly import AnomalyDetector
        d = AnomalyDetector(_DEFAULT_RULES, _DEFAULT_CAPACITIES)
        # Inject a simple dict-backed mock for the ValueState
        mock_state = MagicMock()
        mock_state.value.return_value = None
        d._energy_avg_state = mock_state
        return d


# ---------------------------------------------------------------------------
# Temperature rule tests
# ---------------------------------------------------------------------------

def test_temperature_high_threshold_breach(detector):
    anomalies = detector._check(_reading("temperature", 39.0))
    assert len(anomalies) == 1
    assert "threshold" in anomalies[0].anomaly_type.value.lower()


def test_temperature_low_threshold_breach(detector):
    anomalies = detector._check(_reading("temperature", 12.0))
    assert len(anomalies) == 1
    assert "threshold" in anomalies[0].anomaly_type.value.lower()


def test_temperature_within_range_no_anomaly(detector):
    assert detector._check(_reading("temperature", 22.0)) == []


def test_temperature_exactly_at_threshold_no_anomaly(detector):
    assert detector._check(_reading("temperature", 38.0)) == []


# ---------------------------------------------------------------------------
# Energy spike rule tests
# ---------------------------------------------------------------------------

def test_energy_spike_detected(detector):
    r = _reading("energy", 10.0)
    detector._energy_avg_state.value.return_value = 2.0   # rolling avg = 2 W
    anomalies = detector._check(r)                        # 10 > 2 × 3 = 6 → spike
    assert len(anomalies) == 1
    assert "spike" in anomalies[0].anomaly_type.value.lower()


def test_energy_no_spike_below_threshold(detector):
    r = _reading("energy", 5.0)
    detector._energy_avg_state.value.return_value = 3.0   # 5 < 3 × 3 = 9 → no spike
    assert detector._check(r) == []


def test_energy_ema_updates_on_each_reading(detector):
    detector._energy_avg_state.value.return_value = 4.0
    detector._check(_reading("energy", 4.0))
    detector._energy_avg_state.update.assert_called_once()
    new_val = detector._energy_avg_state.update.call_args[0][0]
    assert abs(new_val - (0.9 * 4.0 + 0.1 * 4.0)) < 1e-9


# ---------------------------------------------------------------------------
# Capacity breach rule tests
# ---------------------------------------------------------------------------

def test_occupancy_capacity_breach_detected(detector):
    r = _reading("occupancy", 43.0)   # 43 > 40 × 1.05 = 42
    anomalies = detector._check(r)
    assert len(anomalies) == 1
    assert "capacity" in anomalies[0].anomaly_type.value.lower()


def test_occupancy_within_capacity_no_anomaly(detector):
    r = _reading("occupancy", 40.0)   # 40 <= 42
    assert detector._check(r) == []


def test_occupancy_unknown_room_skipped(detector):
    r = _reading("occupancy", 999.0, room_id="UNKNOWN-999")
    assert detector._check(r) == []
