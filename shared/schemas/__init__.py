"""
shared.schemas — canonical data contracts for the Smart Campus pipeline.

Import from here in all services; never import the sub-modules directly.
This lets the internal layout change without breaking import paths.
"""

from .aggregation import AggregatedReading
from .anomaly import AnomalyEvent, AnomalyType, Severity
from .kafka import KafkaMessage
from .sensor import (
    CANONICAL_UNIT,
    PHYSICAL_BOUNDS,
    SensorReading,
    SensorType,
    Unit,
)

__all__ = [
    # sensor
    "SensorReading",
    "SensorType",
    "Unit",
    "CANONICAL_UNIT",
    "PHYSICAL_BOUNDS",
    # kafka
    "KafkaMessage",
    # aggregation
    "AggregatedReading",
    # anomaly
    "AnomalyEvent",
    "AnomalyType",
    "Severity",
]
