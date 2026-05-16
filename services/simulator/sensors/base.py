import os
import random
import sys
import time
from abc import ABC, abstractmethod
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.models import SENSOR_UNITS, SensorReading

# Per-tick failure and recovery probabilities.
# At a 5-second interval:
#   _FAIL_PROB ≈ 0.01 % → a sensor fails roughly once every ~14 hours on average.
#   _RECOVER_PROB ≈ 2 % → average offline duration ~50 ticks ≈ 4 minutes.
_FAIL_PROB    = 0.0001
_RECOVER_PROB = 0.02


class BaseSensor(ABC):
    """Abstract base for all simulated sensors."""

    def __init__(
        self,
        sensor_id: str,
        room_id: str,
        building_id: str,
        floor: int,
        sensor_type: str,
        room_type: str = "classroom",
    ) -> None:
        self.sensor_id = sensor_id
        self.room_id = room_id
        self.building_id = building_id
        self.floor = floor
        self.sensor_type = sensor_type
        self.room_type = room_type
        self.unit = SENSOR_UNITS[sensor_type]
        self._state: dict[str, Any] = {}
        self._offline: bool = False

    @abstractmethod
    def _sample(self, context: dict[str, Any]) -> float:
        """Return the raw sensor value given environmental context."""

    def read(self, context: dict[str, Any]) -> SensorReading | None:
        """
        Generate a SensorReading for the current tick, or None when the
        sensor is offline (simulating intermittent IoT dropout).
        """
        # Failure state machine
        if self._offline:
            if random.random() < _RECOVER_PROB:
                self._offline = False
            else:
                return None          # no data published while offline
        elif random.random() < _FAIL_PROB:
            self._offline = True
            return None

        value = self._sample(context)
        return SensorReading(
            sensor_id=self.sensor_id,
            building_id=self.building_id,
            floor=self.floor,
            room_id=self.room_id,
            sensor_type=self.sensor_type,
            value=round(value, 4),
            unit=self.unit,
            timestamp_ms=int(time.time() * 1000),
            quality=self._quality(),
            metadata=self._metadata(),
        )

    def _quality(self) -> float:
        """Override to simulate sensor degradation / data-quality flags."""
        return 1.0

    def _metadata(self) -> dict[str, Any]:
        return {}

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))
