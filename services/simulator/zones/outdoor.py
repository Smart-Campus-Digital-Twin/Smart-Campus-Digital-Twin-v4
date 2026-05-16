"""
Outdoor zone occupancy model (e.g., Lagaan ground).

Key patterns:
  - Normally 0-1.5% (random small groups passing through)
  - Event-driven: EventCalendar provides active_venue_fill
  - Lunch break: slightly higher foot traffic
  - Exam periods: quieter (students focused)
  - Seasonal modulation via month proxy:
      Mar-Apr  hot season (~33 °C) → midday dip, people avoid sun
      May, Oct-Nov SW/NE monsoon  → all-day reduction
      Dec-Jan  cool season        → slight increase
"""

import random

from .base_zone import BaseZone, ZoneContext


def _outdoor_background_ratio(hour: float) -> float:
    """Background outdoor occupancy — small random groups passing through."""
    if hour < 7.0 or hour >= 21.0:
        return 0.0
    if random.random() < 0.35:
        return random.uniform(0, 0.015)
    return 0.0


def _season_factor(month: int, hour: float) -> float:
    """
    Month-as-weather-proxy modifier for outdoor occupancy.

    Moratuwa climate:
      Mar-Apr: hot (~33 °C peak), people avoid 11:00-15:00 outdoors
      May, Oct-Nov: SW/NE monsoon, ~50 % rain reduction
      Dec-Jan: cooler and drier, more pleasant outdoors
    """
    if month in (3, 4):            # hot season
        if 11.0 <= hour < 15.0:
            return 0.4             # strong midday heat deterrent
        return 0.85
    if month in (5, 10, 11):       # monsoon months
        return 0.6
    if month in (12, 1):           # cool / dry season
        return 1.2
    return 1.0


class OutdoorZone(BaseZone):
    """Outdoor zones with event-driven or background foot traffic."""

    def _target_ratio(self, ctx: ZoneContext) -> float:
        hour = ctx.hour

        # Event override takes full precedence
        if self.building_id in ctx.active_venue_fill:
            return ctx.active_venue_fill[self.building_id]

        # Night time: empty
        if hour < 6.0 or hour >= 22.0:
            return 0.0

        # Holidays: minimal passersby
        if ctx.is_holiday:
            return random.uniform(0, 0.02)

        base = _outdoor_background_ratio(hour)
        if ctx.is_weekend:
            base *= 1.5

        if ctx.is_exam_period:
            base *= 0.30

        if ctx.academic_day.is_low_attendance:
            base *= 2.0

        # Seasonal / weather proxy
        month = ctx.academic_day.date.month
        base *= _season_factor(month, hour)

        return max(0.005, base * max(0.20, ctx.congestion_fraction))
