"""
Library zone occupancy model.

Key patterns:
  - Opens 08:00, closes 21:00
  - During lecture sessions: quiet (12%) - students in class
  - 10:10-10:30 break: moderate study (25%)
  - 12:15-13:15 lunch break: busy (55%)
  - 15:10-15:30 break: moderate (25%)
  - 17:15-21:00 post-class peak: 70% (students come to study after lectures)
  - Exam periods: much busier, especially evenings (85%)
  - Scaled by academic calendar congestion
"""

from simulator.campus.schedule import library_ratio as _library_ratio

from .base_zone import BaseZone, ZoneContext


class LibraryZone(BaseZone):
    """
    Library zones with study-pattern based occupancy.
    """

    def _target_ratio(self, ctx: ZoneContext) -> float:
        hour = ctx.hour

        # Closed overnight
        if hour < 8.0 or hour >= 21.0:
            return 0.0

        # Holidays: minimal access
        if ctx.is_holiday:
            return 0.20

        # Weekends: library still popular for study
        base = _library_ratio(hour, ctx.is_exam_period)
        if ctx.is_weekend:
            base *= 0.55

        # During low-attendance periods (reading break, online), library still used
        # but scale properly with how many students are actually on campus
        if ctx.academic_day.is_low_attendance:
            return base * 0.80 * ctx.congestion_fraction

        return base * ctx.congestion_fraction
