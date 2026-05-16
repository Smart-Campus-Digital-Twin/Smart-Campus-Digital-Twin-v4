"""
Anomaly detection rules for the ML consumer.

Uses statistical thresholds per sensor type:
  - Temperature: Z-score > 3 or absolute range violation
  - Occupancy: negative or beyond room capacity
  - Energy: sudden spike (> 3x rolling mean) or negative

Rules are intentionally simple and interpretable — no black-box models
required for baseline anomaly detection. MLflow-trained models can be
plugged in later via the ModelRegistry class below.
"""

from __future__ import annotations

import logging
import os
import statistics
from collections import deque
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("ml-consumer.anomaly")

# ── Configurable thresholds ────────────────────────────────────────────────
TEMP_MIN = float(os.getenv("ANOMALY_TEMP_MIN", "5.0"))    # °C
TEMP_MAX = float(os.getenv("ANOMALY_TEMP_MAX", "45.0"))   # °C
TEMP_ZSCORE_THRESHOLD = float(os.getenv("ANOMALY_TEMP_ZSCORE", "3.0"))

ENERGY_SPIKE_FACTOR = float(os.getenv("ANOMALY_ENERGY_SPIKE", "3.0"))  # × rolling mean
ENERGY_MIN = float(os.getenv("ANOMALY_ENERGY_MIN", "0.0"))             # kWh

OCCUPANCY_MAX = int(os.getenv("ANOMALY_OCCUPANCY_MAX", "500"))  # persons
ROLLING_WINDOW = int(os.getenv("ANOMALY_ROLLING_WINDOW", "60"))  # messages


class RollingStats:
    """Lightweight rolling window for mean/stdev calculations."""

    def __init__(self, maxlen: int = ROLLING_WINDOW) -> None:
        self._window: deque[float] = deque(maxlen=maxlen)

    def push(self, value: float) -> None:
        self._window.append(value)

    @property
    def mean(self) -> float | None:
        if len(self._window) < 2:
            return None
        return statistics.mean(self._window)

    @property
    def stdev(self) -> float | None:
        if len(self._window) < 2:
            return None
        try:
            return statistics.stdev(self._window)
        except statistics.StatisticsError:
            return None

    def zscore(self, value: float) -> float | None:
        mean = self.mean
        stdev = self.stdev
        if mean is None or stdev is None or stdev == 0:
            return None
        return abs((value - mean) / stdev)


def _anomaly_event(
    rule: str,
    topic: str,
    payload: dict,
    value: Any,
    severity: str = "warning",
) -> dict:
    return {
        "rule": rule,
        "topic": topic,
        "room_id": payload.get("room_id", "unknown"),
        "sensor_id": payload.get("sensor_id", "unknown"),
        "value": value,
        "severity": severity,
        "detected_at": datetime.now(UTC).isoformat(),
        "raw_payload": payload,
    }


class AnomalyDetector:
    """
    Stateful anomaly detector.

    Maintains per-room rolling statistics for Z-score anomaly detection
    and applies hard threshold rules as a first-pass filter.
    """

    def __init__(self) -> None:
        # room_id → RollingStats per measurement type
        self._temp_stats: dict[str, RollingStats] = {}
        self._energy_stats: dict[str, RollingStats] = {}

    def _get_temp_stats(self, room_id: str) -> RollingStats:
        if room_id not in self._temp_stats:
            self._temp_stats[room_id] = RollingStats()
        return self._temp_stats[room_id]

    def _get_energy_stats(self, room_id: str) -> RollingStats:
        if room_id not in self._energy_stats:
            self._energy_stats[room_id] = RollingStats()
        return self._energy_stats[room_id]

    def check(self, topic: str, payload: dict) -> list[dict]:
        """Return list of anomaly events (empty = no anomalies)."""
        anomalies: list[dict] = []
        topic_name = topic.split(".")[-1]  # temperature / occupancy / energy

        if topic_name == "temperature":
            anomalies.extend(self._check_temperature(topic, payload))
        elif topic_name == "occupancy":
            anomalies.extend(self._check_occupancy(topic, payload))
        elif topic_name == "energy":
            anomalies.extend(self._check_energy(topic, payload))

        return anomalies

    def _check_temperature(self, topic: str, payload: dict) -> list[dict]:
        anomalies = []
        value = payload.get("value") or payload.get("temperature")
        if value is None:
            return anomalies
        value = float(value)
        room_id = payload.get("room_id", "unknown")
        stats = self._get_temp_stats(room_id)

        # Hard threshold
        if value < TEMP_MIN or value > TEMP_MAX:
            anomalies.append(_anomaly_event(
                rule="temperature_out_of_range",
                topic=topic,
                payload=payload,
                value=value,
                severity="critical",
            ))
        else:
            # Z-score check (only if window is populated)
            zscore = stats.zscore(value)
            if zscore is not None and zscore > TEMP_ZSCORE_THRESHOLD:
                anomalies.append(_anomaly_event(
                    rule="temperature_zscore_spike",
                    topic=topic,
                    payload=payload,
                    value={"temperature": value, "zscore": round(zscore, 2)},
                    severity="warning",
                ))

        stats.push(value)
        return anomalies

    def _check_occupancy(self, topic: str, payload: dict) -> list[dict]:
        anomalies = []
        value = payload.get("value") or payload.get("occupancy") or payload.get("count")
        if value is None:
            return anomalies
        value = int(value)

        if value < 0:
            anomalies.append(_anomaly_event(
                rule="occupancy_negative",
                topic=topic,
                payload=payload,
                value=value,
                severity="warning",
            ))
        elif value > OCCUPANCY_MAX:
            anomalies.append(_anomaly_event(
                rule="occupancy_exceeds_capacity",
                topic=topic,
                payload=payload,
                value=value,
                severity="critical",
            ))
        return anomalies

    def _check_energy(self, topic: str, payload: dict) -> list[dict]:
        anomalies = []
        value = payload.get("value") or payload.get("energy") or payload.get("kwh")
        if value is None:
            return anomalies
        value = float(value)
        room_id = payload.get("room_id", "unknown")
        stats = self._get_energy_stats(room_id)

        if value < ENERGY_MIN:
            anomalies.append(_anomaly_event(
                rule="energy_negative",
                topic=topic,
                payload=payload,
                value=value,
                severity="warning",
            ))
        else:
            mean = stats.mean
            if mean is not None and mean > 0 and value > mean * ENERGY_SPIKE_FACTOR:
                anomalies.append(_anomaly_event(
                    rule="energy_spike",
                    topic=topic,
                    payload=payload,
                    value={"energy": value, "mean": round(mean, 2), "factor": round(value / mean, 1)},
                    severity="warning",
                ))

        stats.push(value)
        return anomalies
