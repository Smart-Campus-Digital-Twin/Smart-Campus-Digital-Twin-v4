"""
Auditorium/Large lecture hall zone occupancy model (e.g., Multipurpose Hall, NA1/NA2).

Key patterns:
  - Fills only for large lectures (~15% of lecture slots) or special events
  - Otherwise empty (classes use regular classrooms)
  - EventCalendar provides fills for: symposiums, orientation, career fairs, concerts
  - Exam periods: used for large batch exams
  - Scaled by academic calendar congestion
"""

import random

from simulator.campus.schedule import is_during_lectures as _is_during_lectures

from .base_zone import BaseZone, ZoneContext


class AuditoriumZone(BaseZone):
    """
    Auditorium and large lecture hall zones with event/lecture-based occupancy.
    """

    def _target_ratio(self, ctx: ZoneContext) -> float:
        hour = ctx.hour

        # Check for event override first (symposiums, concerts, etc.)
        if self.building_id in ctx.active_venue_fill:
            return ctx.active_venue_fill[self.building_id]

        # Closed overnight — auditoriums lock at 21:00, unlock 07:00
        if hour < 7.0 or hour >= 21.0:
            return 0.0

        # Holidays: empty unless event
        if ctx.is_holiday:
            return 0.0

        # Weekends: empty unless event (covered by active_venue_fill check above)
        if ctx.is_weekend:
            return 0.0

        # Vacation / marking period: no lectures = empty hall
        if ctx.academic_day.is_essentially_empty:
            return 0.0

        # Exam periods: used for large batch exams
        if ctx.is_exam_period:
            # Higher occupancy during exam slots
            if _is_during_lectures(hour):
                return 0.85 * ctx.lecture_scale
            return 0.0

        # Normal academic day: fills for large lectures ~15% of slots
        if _is_during_lectures(hour) and random.random() < 0.15:
            return random.uniform(0.55, 0.90) * ctx.lecture_scale

        return 0.0
