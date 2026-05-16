from __future__ import annotations

import logging
import math
import random
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

from .models import BehaviorMode, Sensor, SensorReadingOut

logger = logging.getLogger("sim-control.engine")

UNITS: dict[str, str] = {
    "temperature": "celsius",
    "occupancy": "count",
    "energy": "watt",
}

HISTORY_LEN = 60

# Mean-reverting random walk parameters for the NORMAL mode.
# A small per-step delta plus reversion toward the configured midpoint keeps
# adjacent readings close to each other so a fresh subscriber sees a smooth
# trajectory rather than independent samples drawn from a wide gaussian.
_NORMAL_STEP_FRACTION = 0.02      # fraction of (max-min) per 5s tick
_NORMAL_REVERSION = 0.05          # pull toward midpoint per tick
_NORMAL_NOISE_FRACTION = 0.005    # tiny additive noise

# Anomaly trigger: standard deviation across the last N readings exceeding
# a fraction of the configured range marks the sensor as anomalous.
_ANOMALY_WINDOW = 6
_ANOMALY_STD_FRACTION = 0.18


class SensorEngine:
    def __init__(self) -> None:
        self._pattern_indices: dict[str, int] = {}
        self._last_values: dict[str, float] = {}
        self._last_readings: dict[str, dict[str, Any]] = {}
        self._history: dict[str, deque[tuple[int, float]]] = {}
        self._anomaly_flags: dict[str, bool] = {}

    def generate_reading(self, sensor: Sensor) -> SensorReadingOut | None:
        if not sensor.enabled:
            return None

        cfg = sensor.config
        mode = sensor.behavior_mode
        now = datetime.now(UTC)
        now_ms = int(now.timestamp() * 1000)

        if mode == BehaviorMode.NORMAL:
            value = self._normal_for(sensor.id, cfg)
        elif mode == BehaviorMode.RANDOM:
            value = self._random(cfg)
        elif mode == BehaviorMode.PATTERN:
            value = self._pattern(sensor.id, cfg)
        elif mode == BehaviorMode.ANOMALY:
            value = self._anomaly(sensor.id, cfg)
        else:
            value = self._normal(cfg)

        # Clamp to configured range so anomaly spikes still respect the
        # physical bound for non-anomaly modes.
        if mode != BehaviorMode.ANOMALY:
            value = min(max(value, cfg.min_value), cfg.max_value)

        if str(sensor.sensor_type) == "occupancy":
            value = max(0, int(round(value)))
        else:
            value = round(value, 2)
        self._last_values[sensor.id] = value
        buf = self._history.setdefault(sensor.id, deque(maxlen=HISTORY_LEN))
        buf.append((now_ms, value))

        # High-frequency fluctuation detection: rolling std-dev over the
        # last _ANOMALY_WINDOW samples beyond a fraction of the configured
        # range marks the sensor anomalous regardless of behaviour mode.
        std_anom = self._detect_oscillation(sensor.id, cfg)
        self._anomaly_flags[sensor.id] = std_anom or mode == BehaviorMode.ANOMALY

        reading = SensorReadingOut(
            sensor_id=sensor.id,
            building_id=sensor.building_id,
            floor=sensor.floor,
            room_id=sensor.room_id,
            sensor_type=str(sensor.sensor_type),
            value=value,
            unit=UNITS.get(str(sensor.sensor_type), "count"),
            timestamp_ms=now_ms,
            timestamp=now.isoformat(),
            quality=1.0,
            behavior_mode=str(mode),
            metadata={
                "sensor_name": sensor.name,
                "anomaly": self._anomaly_flags[sensor.id],
                **({"count": int(value)} if str(sensor.sensor_type) == "occupancy" else {}),
            },
        )
        self._last_readings[sensor.id] = reading.model_dump()
        return reading

    def get_last_value(self, sensor_id: str) -> float:
        return self._last_values.get(sensor_id, 0.0)

    def get_last_reading(self, sensor_id: str) -> dict | None:
        return self._last_readings.get(sensor_id)

    def get_history(self, sensor_id: str) -> list[tuple[int, float]]:
        return list(self._history.get(sensor_id, deque()))

    def values_snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            sid: {"value": v, "timestamp_ms": self._last_readings.get(sid, {}).get("timestamp_ms")}
            for sid, v in self._last_values.items()
        }

    def _normal(self, cfg: Any) -> float:
        return (cfg.min_value + cfg.max_value) / 2

    def _normal_for(self, sensor_id: str, cfg: Any) -> float:
        rng = cfg.max_value - cfg.min_value
        mid = (cfg.min_value + cfg.max_value) / 2
        prev = self._last_values.get(sensor_id, mid)
        step = random.uniform(-_NORMAL_STEP_FRACTION, _NORMAL_STEP_FRACTION) * rng
        reverted = prev + step + (mid - prev) * _NORMAL_REVERSION
        noise = random.gauss(0, rng * _NORMAL_NOISE_FRACTION)
        return reverted + noise

    def _detect_oscillation(self, sensor_id: str, cfg: Any) -> bool:
        buf = self._history.get(sensor_id)
        if buf is None or len(buf) < _ANOMALY_WINDOW:
            return False
        recent = [v for _, v in list(buf)[-_ANOMALY_WINDOW:]]
        mean = sum(recent) / len(recent)
        var = sum((v - mean) ** 2 for v in recent) / len(recent)
        std = var ** 0.5
        rng = cfg.max_value - cfg.min_value
        return rng > 0 and std > rng * _ANOMALY_STD_FRACTION

    def get_anomaly(self, sensor_id: str) -> bool:
        return bool(self._anomaly_flags.get(sensor_id, False))

    def _random(self, cfg: Any) -> float:
        return random.uniform(cfg.min_value, cfg.max_value)

    def _pattern(self, sensor_id: str, cfg: Any) -> float:
        if not cfg.pattern:
            return self._normal(cfg)
        idx = self._pattern_indices.get(sensor_id, 0)
        value = cfg.pattern[idx % len(cfg.pattern)]
        self._pattern_indices[sensor_id] = (idx + 1) % len(cfg.pattern)
        jitter = (cfg.max_value - cfg.min_value) * 0.02
        return value + random.uniform(-jitter, jitter)

    def _anomaly(self, sensor_id: str, cfg: Any) -> float:
        if random.random() < cfg.anomaly_prob:
            spike = (cfg.max_value - cfg.min_value) * random.choice([2, -1.5, 3])
            return cfg.max_value + spike
        return self._normal(cfg)
