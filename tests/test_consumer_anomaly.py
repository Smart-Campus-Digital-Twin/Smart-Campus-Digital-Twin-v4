"""
Unit tests for the ML consumer anomaly detection module.

Tests cover:
  - Temperature hard thresholds (too low / too high)
  - Temperature Z-score spike detection
  - Occupancy negative / over-capacity rules
  - Energy negative / spike rules
  - Normal readings produce no anomalies
  - Rolling window statistics
"""

from __future__ import annotations

import pytest

from processing.consumer.anomaly import AnomalyDetector, RollingStats

# ─────────────────────────────────────────────────────────────────────────────
# RollingStats unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRollingStats:
    def test_empty_window_returns_none(self):
        stats = RollingStats()
        assert stats.mean is None
        assert stats.stdev is None
        assert stats.zscore(10.0) is None

    def test_single_value_returns_none(self):
        stats = RollingStats()
        stats.push(20.0)
        assert stats.mean is None  # need >= 2 values

    def test_mean_calculated_correctly(self):
        stats = RollingStats()
        for v in [10.0, 20.0, 30.0]:
            stats.push(v)
        assert stats.mean == pytest.approx(20.0)

    def test_zscore_zero_for_mean_value(self):
        stats = RollingStats()
        for v in [10.0, 10.0, 10.0, 20.0, 30.0]:
            stats.push(v)
        # Mean around 16, stdev != 0
        # A value exactly at mean → zscore close to 0
        mean = stats.mean
        zscore = stats.zscore(mean)
        assert zscore == pytest.approx(0.0, abs=1e-9)

    def test_window_maxlen_respected(self):
        stats = RollingStats(maxlen=3)
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            stats.push(v)
        # Only last 3 values remain: [3, 4, 5]
        assert stats.mean == pytest.approx(4.0)


# ─────────────────────────────────────────────────────────────────────────────
# AnomalyDetector — Temperature
# ─────────────────────────────────────────────────────────────────────────────

class TestTemperatureAnomalies:
    def setup_method(self):
        self.detector = AnomalyDetector()

    def _temp_payload(self, value: float, room_id: str = "room-01") -> dict:
        return {"room_id": room_id, "sensor_id": "s1", "value": value}

    def test_normal_temp_no_anomaly(self):
        payload = self._temp_payload(22.0)
        anomalies = self.detector.check("sensors.temperature", payload)
        assert anomalies == []

    def test_temp_too_low_threshold(self):
        payload = self._temp_payload(4.9)  # below TEMP_MIN=5.0
        anomalies = self.detector.check("sensors.temperature", payload)
        assert len(anomalies) == 1
        assert anomalies[0]["rule"] == "temperature_out_of_range"
        assert anomalies[0]["severity"] == "critical"

    def test_temp_too_high_threshold(self):
        payload = self._temp_payload(45.1)  # above TEMP_MAX=45.0
        anomalies = self.detector.check("sensors.temperature", payload)
        assert len(anomalies) == 1
        assert anomalies[0]["rule"] == "temperature_out_of_range"

    def test_temp_boundary_values_no_anomaly(self):
        for val in [5.0, 45.0, 22.5]:
            anomalies = self.detector.check("sensors.temperature", self._temp_payload(val))
            assert anomalies == [], f"Expected no anomaly at {val}°C"

    def test_zscore_spike_detected_after_window_fills(self):
        # Feed slightly varied readings to give nonzero stdev
        import itertools
        stable_vals = itertools.cycle([21.5, 22.0, 22.5, 22.0, 21.8])
        for _, v in zip(range(30), stable_vals, strict=False):
            self.detector.check("sensors.temperature", self._temp_payload(v))
        # Then send a spike well within hard limits but > 3σ from stable mean ~22°C
        # Mean≈22, stdev≈0.35 → z-score of 40°C ≈ (40-22)/0.35 ≈ 51 >> 3
        payload = self._temp_payload(40.0)
        anomalies = self.detector.check("sensors.temperature", payload)
        assert len(anomalies) >= 1
        assert any(a["rule"] == "temperature_zscore_spike" for a in anomalies)


    def test_missing_value_field_no_crash(self):
        payload = {"room_id": "room-01"}
        anomalies = self.detector.check("sensors.temperature", payload)
        assert anomalies == []

    def test_per_room_stats_isolated(self):
        # Room A: stable at 22°C
        for _ in range(30):
            self.detector.check("sensors.temperature", self._temp_payload(22.0, "room-A"))
        # Room B: no history — spike should not be detected via zscore (no window)
        payload = self._temp_payload(40.0, "room-B")
        anomalies = self.detector.check("sensors.temperature", payload)
        # No zscore anomaly for room-B (no window), only possible hard-limit
        assert all(a["rule"] != "temperature_zscore_spike" for a in anomalies)


# ─────────────────────────────────────────────────────────────────────────────
# AnomalyDetector — Occupancy
# ─────────────────────────────────────────────────────────────────────────────

class TestOccupancyAnomalies:
    def setup_method(self):
        self.detector = AnomalyDetector()

    def _occ_payload(self, count: int, room_id: str = "room-01") -> dict:
        return {"room_id": room_id, "sensor_id": "s2", "count": count}

    def test_normal_occupancy_no_anomaly(self):
        anomalies = self.detector.check("sensors.occupancy", self._occ_payload(50))
        assert anomalies == []

    def test_negative_occupancy(self):
        anomalies = self.detector.check("sensors.occupancy", self._occ_payload(-1))
        assert len(anomalies) == 1
        assert anomalies[0]["rule"] == "occupancy_negative"

    def test_zero_occupancy_ok(self):
        anomalies = self.detector.check("sensors.occupancy", self._occ_payload(0))
        assert anomalies == []

    def test_over_capacity(self):
        anomalies = self.detector.check("sensors.occupancy", self._occ_payload(501))  # > 500
        assert len(anomalies) == 1
        assert anomalies[0]["rule"] == "occupancy_exceeds_capacity"
        assert anomalies[0]["severity"] == "critical"

    def test_at_capacity_boundary_no_anomaly(self):
        anomalies = self.detector.check("sensors.occupancy", self._occ_payload(500))
        assert anomalies == []

    def test_missing_count_no_crash(self):
        anomalies = self.detector.check("sensors.occupancy", {"room_id": "x"})
        assert anomalies == []


# ─────────────────────────────────────────────────────────────────────────────
# AnomalyDetector — Energy
# ─────────────────────────────────────────────────────────────────────────────

class TestEnergyAnomalies:
    def setup_method(self):
        self.detector = AnomalyDetector()

    def _energy_payload(self, kwh: float, room_id: str = "room-01") -> dict:
        return {"room_id": room_id, "sensor_id": "s3", "kwh": kwh}

    def test_normal_energy_no_anomaly(self):
        anomalies = self.detector.check("sensors.energy", self._energy_payload(10.0))
        assert anomalies == []

    def test_negative_energy(self):
        anomalies = self.detector.check("sensors.energy", self._energy_payload(-0.1))
        assert len(anomalies) == 1
        assert anomalies[0]["rule"] == "energy_negative"

    def test_zero_energy_ok(self):
        anomalies = self.detector.check("sensors.energy", self._energy_payload(0.0))
        assert anomalies == []

    def test_spike_detected_after_window(self):
        # Stable readings at 10 kWh
        for _ in range(20):
            self.detector.check("sensors.energy", self._energy_payload(10.0))
        # Spike at 35 kWh = 3.5x mean → exceeds ENERGY_SPIKE_FACTOR=3.0
        anomalies = self.detector.check("sensors.energy", self._energy_payload(35.0))
        assert len(anomalies) == 1
        assert anomalies[0]["rule"] == "energy_spike"

    def test_no_spike_without_window(self):
        # First reading — no rolling mean yet → no spike anomaly
        anomalies = self.detector.check("sensors.energy", self._energy_payload(1000.0))
        assert all(a["rule"] != "energy_spike" for a in anomalies)

    def test_missing_kwh_no_crash(self):
        anomalies = self.detector.check("sensors.energy", {"room_id": "x"})
        assert anomalies == []


# ─────────────────────────────────────────────────────────────────────────────
# AnomalyDetector — anomaly event structure
# ─────────────────────────────────────────────────────────────────────────────

class TestAnomalyEventStructure:
    def setup_method(self):
        self.detector = AnomalyDetector()

    def test_anomaly_event_has_required_fields(self):
        payload = {"room_id": "room-99", "sensor_id": "s-test", "value": -999.0}
        anomalies = self.detector.check("sensors.temperature", payload)
        assert len(anomalies) > 0
        event = anomalies[0]
        assert "rule" in event
        assert "topic" in event
        assert "room_id" in event
        assert "severity" in event
        assert "detected_at" in event
        assert event["room_id"] == "room-99"

    def test_anomaly_detected_at_is_iso_string(self):
        from datetime import datetime
        payload = {"room_id": "x", "value": 99.0}
        anomalies = self.detector.check("sensors.temperature", payload)
        assert len(anomalies) > 0
        # Should parse without error
        dt = datetime.fromisoformat(anomalies[0]["detected_at"])
        assert dt is not None
