"""
Canteen/Food court zone occupancy model.

Key patterns:
  - Anti-correlated with lecture schedule (empty during classes, full at breaks)
  - 07:30–08:15 breakfast rush → 95% capacity (queues form)
  - 10:10–10:30 session-change spike → 65% (quick tea)
  - 12:15–13:15 lunch peak → 98% (maximum, overflows to nearby areas)
  - 15:10–15:30 afternoon tea → 55%
  - 17:15–19:30 after-class dinner → 30% tapering
  - Scaled by academic calendar congestion
"""

from simulator.campus.schedule import canteen_ratio as _canteen_ratio

from .base_zone import BaseZone, ZoneContext


class CanteenZone(BaseZone):
    """
    Canteen and food court zones with meal-rush based occupancy.
    """

    def _target_ratio(self, ctx: ZoneContext) -> float:
        hour = ctx.hour

        # Closed overnight
        if hour < 6.5 or hour >= 20.0:
            return 0.0

        # Holidays: minimal staff only
        if ctx.is_holiday:
            return 0.15

        # Weekends: reduced but still meal traffic
        base = _canteen_ratio(hour)
        if ctx.is_weekend:
            base *= 0.40

        # Scale by academic calendar congestion
        # But canteen always has some traffic even during breaks
        if ctx.academic_day.is_essentially_empty:
            return max(0.05, base * 0.30)

        return base * ctx.congestion_fraction
