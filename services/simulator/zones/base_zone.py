"""
Base zone class and shared context dataclass.

Zones encapsulate zone-specific sensor logic and occupancy patterns.
Each zone type inherits from BaseZone and overrides:
  - _target_ratio(): the occupancy ratio given time-of-day and academic context
  - Optionally: create_sensors() to customize sensor configuration
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from simulator.sensors.occupancy import OccupancySensor

if TYPE_CHECKING:
    from simulator.campus.academic_calendar import AcademicDay
    from simulator.campus.topology import Room
    from simulator.sensors.base import BaseSensor


@dataclass(frozen=True)
class ZoneContext:
    """
    Context passed to all zone sensors on each tick.
    Contains time, academic calendar state, and active events.
    """
    hour: float                      # 0.0–24.0 fractional hour
    day_of_week: int                 # 0=Monday ... 6=Sunday
    is_holiday: bool                 # Sri Lanka public holiday
    academic_day: AcademicDay        # From AcademicCalendar (congestion, activity type)
    active_venue_fill:  dict[str, float]  # From EventCalendar (events override)
    active_event_types: frozenset[str]   # Event types active this tick
    building_id: str                     # Current building
    room_id: str                         # Current room

    @property
    def is_weekend(self) -> bool:
        return self.day_of_week >= 5

    @property
    def is_exam_period(self) -> bool:
        return self.academic_day.is_exam_period

    @property
    def congestion_fraction(self) -> float:
        """Campus-wide congestion multiplier (0.0–1.0+)."""
        return self.academic_day.congestion_fraction

    @property
    def lecture_scale(self) -> float:
        """Multiplier for lecture-slot occupancy (accounts for TUA, breaks, etc.)."""
        return self.academic_day.lecture_scale


class BaseZone(ABC):
    """
    Abstract base for all zone types.

    Each zone:
      1. Holds zone-specific parameters (capacity, building_id, etc.)
      2. Implements _target_ratio() for its occupancy pattern
      3. Creates and manages its sensors (temperature, occupancy, energy)
    """

    def __init__(
        self,
        room: Room,
    ) -> None:
        self.room = room
        self.room_id = room.room_id
        self.building_id = room.building_id
        self.floor = room.floor
        self.room_type = room.room_type
        self.capacity = room.capacity
        self._sensors: list[BaseSensor] = []
        self._create_sensors()

    @abstractmethod
    def _target_ratio(self, ctx: ZoneContext) -> float:
        """
        Return the target occupancy ratio (0.0–1.0) for this zone given context.
        This is the core zone-specific logic that varies by room type.
        """
        ...

    def _create_sensors(self) -> None:
        """
        Instantiate sensors for this zone. Override to customize.
        Default: temperature, occupancy, energy for most zones.
        """
        # Import here to avoid circular imports
        from simulator.sensors.energy import EnergySensor
        from simulator.sensors.temperature import TemperatureSensor

        for sensor_type in self.room.sensors:
            kwargs = dict(
                sensor_id=f"{self.room_id}-{sensor_type}",
                room_id=self.room_id,
                building_id=self.building_id,
                floor=self.floor,
                sensor_type=sensor_type,
                room_type=self.room_type,
            )

            if sensor_type == "occupancy":
                kwargs["capacity"] = self.capacity
                # Bind zone's _target_ratio method to the occupancy sensor
                sensor = ZoneOccupancySensor(
                    zone=self,
                    **kwargs
                )
            elif sensor_type == "temperature":
                sensor = TemperatureSensor(**kwargs)
            elif sensor_type == "energy":
                sensor = EnergySensor(**kwargs)
            else:
                continue

            self._sensors.append(sensor)

    @property
    def sensors(self) -> list[BaseSensor]:
        """Return all sensors in this zone."""
        return self._sensors

    def get_occupancy_sensor(self) -> Any | None:
        """Return the occupancy sensor if present."""
        for s in self._sensors:
            if s.sensor_type == "occupancy":
                return s
        return None


# ─── Event crowd redistribution ───────────────────────────────────────────────
#
# When a large event is active at one venue, non-venue buildings see a drain
# (people leave classrooms for the career fair, etc.) or a boost (canteen gets
# more traffic from event visitors).  Factors compound when multiple events run.
_EVENT_CROWD_DRAIN: dict[str, dict[str, float]] = {
    "career_fair":  {"classroom": 0.80, "lab": 0.85, "library": 0.90, "canteen": 1.10},
    "symposium":    {"classroom": 0.90, "lab": 0.90, "canteen": 1.05},
    "food_festival":{"classroom": 0.95, "library": 0.88, "office": 0.95},
    "orientation":  {"classroom": 0.90, "library": 1.10},
}


# ─── Zone-specific Occupancy Sensor ───────────────────────────────────────────

class ZoneOccupancySensor(OccupancySensor):
    """
    Occupancy sensor that delegates target ratio calculation to its parent Zone.
    This allows each zone type to define its own occupancy logic.
    """

    def __init__(self, zone: BaseZone, **kwargs) -> None:
        super().__init__(**kwargs)
        self._zone = zone
        self._eve_active: bool = False
        self._eve_ratio: float = 0.0

    def _compute_target_ratio(self, ctx: ZoneContext) -> float:
        """Delegate to zone's logic."""
        return self._zone._target_ratio(ctx)

    def _sample(self, context: dict[str, Any]) -> int:
        # Convert dict context to ZoneContext
        from simulator.campus.academic_calendar import calendar

        hour               = context.get("hour", 12.0)
        dow                = context.get("day_of_week", 0)
        is_holiday         = context.get("is_holiday", False)
        active_venue_fill  = context.get("active_venue_fill", {})
        active_event_types = frozenset(context.get("active_event_types", set()))

        academic_day = context.get("academic_day")
        if academic_day is None:
            from datetime import date
            academic_day = calendar.get_day(date.today())

        zone_ctx = ZoneContext(
            hour=hour,
            day_of_week=dow,
            is_holiday=is_holiday,
            academic_day=academic_day,
            active_venue_fill=active_venue_fill,
            active_event_types=active_event_types,
            building_id=self.building_id,
            room_id=self.room_id,
        )

        # Event venue override takes full precedence (this building is hosting)
        if self.building_id in active_venue_fill:
            ratio = active_venue_fill[self.building_id]
        else:
            ratio = self._compute_target_ratio(zone_ctx)

            # Crowd redistribution: events at other venues draw people away
            # (or boost traffic) in non-hosting buildings.
            if active_event_types:
                drain = 1.0
                for evt_type in active_event_types:
                    drain *= _EVENT_CROWD_DRAIN.get(evt_type, {}).get(self.room_type, 1.0)
                ratio *= drain

        # Optional evening tutorial / club event (classrooms & labs only)
        if not zone_ctx.is_weekend and self.room_type in ("classroom", "lab") and (17.25 <= hour < 21.0):
            ratio = self._apply_evening_event(hour, ratio)

        return self._apply_flow(ratio)

    def _apply_evening_event(self, hour: float, base: float) -> float:
        """Rare optional evening tutorial/club."""
        if not self._eve_active:
            if random.random() < 0.0015:
                self._eve_active = True
                self._eve_ratio = random.uniform(0.20, 0.50)
        else:
            if hour >= 21.0 or random.random() < 0.0008:
                self._eve_active = False
        return self._eve_ratio if self._eve_active else base

