from __future__ import annotations

import logging
import math
import random
import time
from typing import Any

from .models import BehaviorMode, Sensor, SensorReadingOut

logger = logging.getLogger("sim-control.engine")

UNITS: dict[str, str] = {
    "temperature": "celsius",
    "occupancy": "count",
    "energy": "watt",
}


class SensorEngine:
    def __init__(self) -> None:
        self._pattern_indices: dict[str, int] = {}
        self._last_values: dict[str, float] = {}

    def generate_reading(self, sensor: Sensor) -> SensorReadingOut | None:
        if not sensor.enabled:
            return None

        cfg = sensor.config
        mode = sensor.behavior_mode
        now_ms = int(time.time() * 1000)

        if mode == BehaviorMode.NORMAL:
            value = self._normal(cfg)
        elif mode == BehaviorMode.RANDOM:
            value = self._random(cfg)
        elif mode == BehaviorMode.PATTERN:
            value = self._pattern(sensor.id, cfg)
        elif mode == BehaviorMode.ANOMALY:
            value = self._anomaly(sensor.id, cfg)
        else:
            value = self._normal(cfg)

        self._last_values[sensor.id] = value

        return SensorReadingOut(
            sensor_id=sensor.id,
            building_id=sensor.building_id,
            floor=sensor.floor,
            room_id=sensor.room_id,
            sensor_type=str(sensor.sensor_type),
            value=round(value, 2),
            unit=UNITS.get(str(sensor.sensor_type), "count"),
            timestamp_ms=now_ms,
            quality=1.0,
            behavior_mode=str(mode),
            metadata={"sensor_name": sensor.name},
        )

    def get_last_value(self, sensor_id: str) -> float:
        return self._last_values.get(sensor_id, 0.0)

    def _normal(self, cfg: Any) -> float:
        mid = (cfg.min_value + cfg.max_value) / 2
        spread = (cfg.max_value - cfg.min_value) * 0.1
        return mid + random.gauss(0, spread)

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
