"""
Classroom/Lab zone occupancy model.

Key patterns:
  - Weekday lecture slots: fills to ~88% during 08:15-10:15, 10:15-12:15, 13:15-15:15, 15:15-17:15
  - Transitions at 10:15 and 15:15: brief half-empty state while students switch
  - Exam periods: concentrated session pattern (morning/afternoon exam slots)
  - Scaled by academic calendar congestion (TUA=50%, Reading Break=50%, etc.)
  - Weekend classes for IT and Architecture (dept-design, faculty-it)
"""

from typing import TYPE_CHECKING

from simulator.campus.schedule import (
    WEEKEND_ACTIVE_BUILDINGS,
)
from simulator.campus.schedule import (
    exam_ratio as _exam_ratio,
)
from simulator.campus.schedule import (
    lecture_ratio as _lecture_ratio,
)

from .base_zone import BaseZone, ZoneContext

if TYPE_CHECKING:
    from simulator.campus.topology import Room


class ClassroomZone(BaseZone):
    """
    Classroom and lab zones with lecture/exam-based occupancy patterns.
    """

    def __init__(self, room: "Room") -> None:
        super().__init__(room)
        self.has_weekend_classes = self.building_id in WEEKEND_ACTIVE_BUILDINGS

    def _target_ratio(self, ctx: ZoneContext) -> float:
        hour = ctx.hour

        # Curfew: 22:00-06:00
        if hour >= 22.0 or hour < 6.0:
            return 0.0

        # Holidays: a small residual of postgrad researchers and maintenance staff
        # remain on campus even on public holidays.
        if ctx.is_holiday:
            return 0.03

        # Weekends
        if ctx.is_weekend:
            if self.has_weekend_classes:
                # IT/Arch have Sat classes
                ratio = _lecture_ratio(hour) if hour < 17.0 else 0.0
                # Scale down for weekend
                return ratio * 0.40
            return 0.0

        # Normal academic day
        base = _exam_ratio(hour) if ctx.is_exam_period else _lecture_ratio(hour)

        # Scale by academic calendar (TUA, reading break, etc.)
        return base * ctx.lecture_scale
