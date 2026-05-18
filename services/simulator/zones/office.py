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

        # Strict office hours — locked outside 07:30-18:00
        if hour < 7.5 or hour >= 18.0:
            return 0.0

        # Holidays: skeleton staff only, daytime window
        if ctx.is_holiday:
            return 0.05 if 9.0 <= hour < 15.0 else 0.0

        # Weekends: minimal staff, daytime window
        if ctx.is_weekend:
            return 0.05 if 9.0 <= hour < 14.0 else 0.0

        # Vacation / marking: skeleton crew only
        if ctx.academic_day.is_essentially_empty:
            return 0.05

        base = _office_ratio(hour)

        # Exam periods: more staff for exam processing
        if ctx.is_exam_period and 8.5 <= hour < 17.0:
            base = 0.90

        # Scale by congestion; keep a small minimum for essential staff
        return max(0.10, base * max(0.40, ctx.congestion_fraction))
