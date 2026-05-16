import json
from dataclasses import dataclass, field
from typing import Any

SENSOR_UNITS: dict[str, str] = {
    "temperature": "°C",
    "occupancy":   "count",
    "energy":      "W",
}


@dataclass
class SensorReading:
    sensor_id:    str
    building_id:  str
    floor:        int
    room_id:      str
    sensor_type:  str
    value:        float
    unit:         str
    timestamp_ms: int
    quality:      float = 1.0
    metadata:     dict[str, Any] = field(default_factory=dict)

    @property
    def mqtt_topic(self) -> str:
        return f"campus/{self.building_id}/f{self.floor}/{self.room_id}/{self.sensor_type}"

    def to_json(self) -> str:
        return json.dumps({
            "sensor_id":    self.sensor_id,
            "building_id":  self.building_id,
            "floor":        self.floor,
            "room_id":      self.room_id,
            "sensor_type":  self.sensor_type,
            "value":        self.value,
            "unit":         self.unit,
            "timestamp_ms": self.timestamp_ms,
            "quality":      self.quality,
            "metadata":     self.metadata,
        })
