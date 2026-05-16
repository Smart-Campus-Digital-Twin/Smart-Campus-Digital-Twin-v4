"""
Office/Admin zone occupancy model.

Key patterns:
  - Admin staff hours: 08:30-17:00 weekdays
  - 80% occupancy during work hours
  - Lunch dip to 25% (12:15-13:15)
  - Weekends: empty (except skeleton staff ~5%)
  - Holidays: empty
  - Exam periods: higher (staff processing exams)
  - Scaled minimally by academic calendar
"""

from simulator.campus.schedule import office_ratio as _office_ratio

from .base_zone import BaseZone, ZoneContext


class OfficeZone(BaseZone):
    """
    Office and admin zones with staff-hours based occupancy.
    """

    def _target_ratio(self, ctx: ZoneContext) -> float:
        hour = ctx.hour

        # Closed overnight and weekends
        if hour < 6.0 or hour >= 22.0:
            return 0.0

        # Holidays: skeleton staff only
        if ctx.is_holiday:
            return 0.05

        # Weekends: minimal staff
        if ctx.is_weekend:
            return 0.05

        # Vacation / marking: skeleton crew only
        if ctx.academic_day.is_essentially_empty:
            return 0.05

        base = _office_ratio(hour)

        # Exam periods: more staff for exam processing
        if ctx.is_exam_period and 8.5 <= hour < 17.0:
            base = 0.90

        # Scale by congestion; keep a small minimum for essential staff
        return max(0.10, base * max(0.40, ctx.congestion_fraction))
