"""
Base occupancy sensor.

Zone-specific occupancy logic lives in the zones/ package; each zone type
implements _target_ratio().  All occupancy pattern helpers (canteen_ratio,
library_ratio, etc.) are the canonical versions in campus/schedule.py.

Global rules:
  - After 22:00 → campus curfew: hostel 90 %, everything else 0
  - active_venue_fill dict (from EventCalendar) fully overrides occupancy
"""

import random
from typing import Any

from .base import BaseSensor

# ── Sensor class ──────────────────────────────────────────────────────────────

class OccupancySensor(BaseSensor):
    """
    Base occupancy sensor - stateful bi-directional people counter.

    Target headcount is determined by _target_ratio() which is implemented
    by zone-specific subclasses (ZoneOccupancySensor in zones/base_zone.py).

    This base class provides:
      - Stateful count tracking with probabilistic entry/exit flows via _apply_flow()
      - Capacity management
      - Noise injection for realistic simulation

    Subclasses must implement:
      - _target_ratio(context) -> float: returns 0.0-1.0 occupancy ratio

    Context keys consumed by base implementation:
      - hour, day_of_week, is_holiday, active_venue_fill
      - academic_day (ZoneOccupancySensor uses this from ZoneContext)
    """

    def __init__(
        self,
        *args,
        capacity: int = 30,
        room_type: str = "classroom",
        **kwargs,
    ) -> None:
        super().__init__(*args, room_type=room_type, **kwargs)
        self.capacity = capacity
        self._count: int = 0

    def _target_ratio(self, context: dict[str, Any]) -> float:
        """
        Return target occupancy ratio (0.0-1.0).

        OVERRIDE in subclasses to provide zone-specific logic.
        This base implementation returns 0 (must be overridden).
        """
        return 0.0

    def _apply_flow(self, ratio: float) -> int:
        """
        Move _count toward ratio * capacity using probabilistic entry/exit.

        Burst mode: when the gap exceeds 10 % of capacity (e.g. a lecture hall
        going from empty to full), up to capacity//20 people move per tick so
        the hall fills in ~2-3 minutes rather than 80+ minutes.  Small gaps
        keep the fine-grained one-person-at-a-time behaviour.
        """
        target = int(max(0, min(self.capacity,
                    round(ratio * self.capacity
                          + random.gauss(0, max(1, self.capacity * 0.04))))))

        diff = target - self._count
        if diff == 0:
            return self._count

        abs_diff = abs(diff)
        # Burst: allow larger steps only when gap is significant
        step = max(1, min(abs_diff, self.capacity // 20)) if abs_diff > self.capacity * 0.1 else 1

        prob = min(0.92, abs_diff / max(1, self.capacity * 1.5))
        if random.random() < prob:
            if diff > 0:
                self._count = min(self.capacity, self._count + step)
            else:
                self._count = max(0, self._count - step)

        return self._count

    # ── Sensor tick ───────────────────────────────────────────────────────────

    def _sample(self, context: dict[str, Any]) -> int:
        ratio = self._target_ratio(context)
        return self._apply_flow(ratio)
