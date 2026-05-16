"""
Anomaly injector for simulator testing.

Injects minimal anomalies into sensor readings to test the anomaly detection pipeline.
Can be enabled/disabled via environment variable ANOMALY_INJECTION_ENABLED=true.
"""

import os
import random

from shared.models import SensorReading

# Enable/disable via environment variable
_ENABLED = os.getenv("ANOMALY_INJECTION_ENABLED", "false").lower() == "true"
# Probability of injecting an anomaly per reading (5% by default)
_INJECTION_PROB = float(os.getenv("ANOMALY_INJECTION_PROB", "0.05"))


class AnomalyInjector:
    """Injects anomalies into sensor readings for testing."""

    def __init__(self):
        self._enabled = _ENABLED
        self._injection_prob = _INJECTION_PROB

    def inject(self, reading: SensorReading) -> SensorReading:
        """
        Inject an anomaly into a sensor reading if enabled and probability check passes.

        Returns the modified reading or the original if no injection occurs.
        """
        if not self._enabled:
            return reading

        if random.random() > self._injection_prob:
            return reading

        # Inject anomaly based on sensor type
        if reading.sensor_type == "temperature":
            return self._inject_temperature_anomaly(reading)
        elif reading.sensor_type == "energy":
            return self._inject_energy_anomaly(reading)
        elif reading.sensor_type == "occupancy":
            return self._inject_occupancy_anomaly(reading)
        else:
            return reading

    def _inject_temperature_anomaly(self, reading: SensorReading) -> SensorReading:
        """Inject temperature anomaly (>38°C or <14°C)."""
        # Randomly choose high or low anomaly
        if random.random() < 0.5:
            # High anomaly: 39-42°C
            new_value = random.uniform(39.0, 42.0)
        else:
            # Low anomaly: 10-13°C
            new_value = random.uniform(10.0, 13.0)

        return SensorReading(
            sensor_id=reading.sensor_id,
            building_id=reading.building_id,
            floor=reading.floor,
            room_id=reading.room_id,
            sensor_type=reading.sensor_type,
            value=round(new_value, 2),
            unit=reading.unit,
            timestamp_ms=reading.timestamp_ms,
            quality=reading.quality,
            metadata={**reading.metadata, "anomaly_injected": True},
        )

    def _inject_energy_anomaly(self, reading: SensorReading) -> SensorReading:
        """Inject energy spike (3-5x normal value)."""
        # Multiply by 3-5x to trigger spike detection
        multiplier = random.uniform(3.0, 5.0)
        new_value = reading.value * multiplier

        return SensorReading(
            sensor_id=reading.sensor_id,
            building_id=reading.building_id,
            floor=reading.floor,
            room_id=reading.room_id,
            sensor_type=reading.sensor_type,
            value=round(new_value, 2),
            unit=reading.unit,
            timestamp_ms=reading.timestamp_ms,
            quality=reading.quality,
            metadata={**reading.metadata, "anomaly_injected": True},
        )

    def _inject_occupancy_anomaly(self, reading: SensorReading) -> SensorReading:
        """Inject occupancy capacity breach (>105% capacity)."""
        actual_capacity = int(reading.metadata.get("capacity", 30))
        multiplier = random.uniform(1.1, 1.2)
        new_value = int(actual_capacity * multiplier)

        return SensorReading(
            sensor_id=reading.sensor_id,
            building_id=reading.building_id,
            floor=reading.floor,
            room_id=reading.room_id,
            sensor_type=reading.sensor_type,
            value=float(new_value),
            unit=reading.unit,
            timestamp_ms=reading.timestamp_ms,
            quality=reading.quality,
            metadata={**reading.metadata, "anomaly_injected": True},
        )


# Global instance
_injector: AnomalyInjector | None = None


def get_injector() -> AnomalyInjector:
    """Get or create the global anomaly injector instance."""
    global _injector
    if _injector is None:
        _injector = AnomalyInjector()
    return _injector


def inject_if_enabled(reading: SensorReading) -> SensorReading:
    """Convenience function to inject anomalies if enabled."""
    return get_injector().inject(reading)
