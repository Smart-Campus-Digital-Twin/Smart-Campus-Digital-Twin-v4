"""
Hostel zone occupancy model.

Key patterns:
  - Inverted pattern from academic buildings:
    * Full at night (90% after 22:00) - residents in rooms
    * Low during lecture hours (20%) - students in class
  - Weekends: different pattern - out during day, back by evening
  - Holidays: residents mostly stay (70-80%)
  - During breaks/IT: higher occupancy (students not in class)
"""

from simulator.campus.schedule import hostel_ratio as _hostel_ratio

from .base_zone import BaseZone, ZoneContext


class HostelZone(BaseZone):
    """
    Hostel zones with inverted occupancy pattern (full at night, low during day).
    """

    def _target_ratio(self, ctx: ZoneContext) -> float:
        hour = ctx.hour

        is_vacation = ctx.academic_day.is_essentially_empty

        # Holidays: residents mostly stay
        if ctx.is_holiday:
            return _hostel_ratio(hour, ctx.is_weekend, is_vacation) * 0.70

        return _hostel_ratio(hour, ctx.is_weekend, is_vacation)
