"""
University of Moratuwa — shared lecture schedule constants and helpers.

Single source of truth for lecture timing AND all zone occupancy patterns,
used across:
  - simulator/zones/classroom.py
  - simulator/zones/auditorium.py
  - simulator/zones/canteen.py
  - simulator/zones/library.py
  - simulator/zones/office.py
  - simulator/zones/hostel.py
  - simulator/sensors/occupancy.py

Slot timing notes
─────────────────
Slots 1 and 3 end ~5 min before their official clock time (10:10 / 15:10)
because in practice the lecturer wraps up slightly early and students begin
moving.  The POST_WINDOW drain overlaps with the next slot's PRE_WINDOW
ramp; lecture_ratio() returns the max() across all slots so the crossover
is smooth — classrooms dip only briefly while students transition.
The canteen tea spikes (10:10–10:30 and 15:10–15:30) align with these
drain windows, which is why both can be non-zero simultaneously.
"""


# Campus-wide lecture slots (start, end) in fractional 24-h hours
LECTURE_SLOTS: list[tuple[float, float]] = [
    (8  + 15/60, 10 + 10/60),  # 08:15–10:10  (slot 1 — ends early)
    (10 + 15/60, 12 + 15/60),  # 10:15–12:15  (slot 2)
    (13 + 15/60, 15 + 10/60),  # 13:15–15:10  (slot 3 — ends early)
    (15 + 15/60, 17 + 15/60),  # 15:15–17:15  (slot 4)
]

# Written / design exam session slots
EXAM_SLOTS: list[tuple[float, float]] = [
    (8.0,  11.0),   # morning exam session
    (13.0, 16.0),   # afternoon exam session
]

PRE_WINDOW:  float = 10 / 60   # ramp-up window before a slot  (hours)
POST_WINDOW: float =  5 / 60   # drain window after a slot (hours)

# Buildings where Saturday/Sunday classes run (IT and Architecture)
WEEKEND_ACTIVE_BUILDINGS: frozenset[str] = frozenset({"faculty-it", "dept-design"})

# Canteen busy periods: (start, end, peak_ratio)
CANTEEN_PERIODS: list[tuple[float, float, float]] = [
    (7.5,         8  + 15/60,   0.95),  # 07:30–08:15 breakfast rush
    (10 + 10/60,  10 + 30/60,   0.65),  # 10:10–10:30 session-change tea spike
    (12 + 15/60,  13 + 15/60,   0.98),  # 12:15–13:15 lunch peak
    (15 + 10/60,  15 + 30/60,   0.55),  # 15:10–15:30 afternoon tea spike
    (17 + 15/60,  19 + 30/60,   0.30),  # 17:15–19:30 post-lecture dinner
]


def lecture_ratio(hour: float) -> float:
    """
    Target occupancy ratio for a classroom (0.0–0.88).

    Burst-fill model: t² ramp (slow start, rapid arrival just before the
    slot) and (1-t)² drain (rapid emptying right after the slot ends).
    Uses max() over all slots for smooth slot-boundary crossovers.
    """
    best = 0.0
    for start, end in LECTURE_SLOTS:
        pre  = start - PRE_WINDOW
        post = end   + POST_WINDOW
        if pre <= hour < start:
            t    = (hour - pre) / PRE_WINDOW          # 0→1, convex rise
            best = max(best, 0.88 * t * t)
        elif start <= hour <= end:
            return 0.88
        elif end < hour < post:
            t    = (hour - end) / POST_WINDOW          # 0→1, fast initial drain
            best = max(best, 0.88 * (1.0 - t) ** 2)
    return best


def exam_ratio(hour: float) -> float:
    """Target occupancy ratio during an exam session (0.0–0.95)."""
    for start, end in EXAM_SLOTS:
        pre  = start - 30 / 60    # 30 min early-arrival window
        post = end   + 20 / 60    # 20 min exit drain
        if pre <= hour < start:
            return 0.95 * (hour - pre) / (30 / 60)
        if start <= hour <= end:
            return 0.95
        if end < hour < post:
            return 0.95 * (1.0 - (hour - end) / (20 / 60))
    return 0.0


def is_during_lectures(hour: float) -> bool:
    """Return True if `hour` falls within any lecture slot."""
    return any(start <= hour <= end for start, end in LECTURE_SLOTS)


def canteen_ratio(hour: float) -> float:
    """Canteen occupancy ratio — peaks at meal/tea breaks, near-zero during lectures."""
    for start, end, peak in CANTEEN_PERIODS:
        if start <= hour < end:
            span = end - start
            ramp = span / 3.0
            if hour < start + ramp:
                return peak * (hour - start) / ramp
            if hour > end - ramp:
                return peak * (end - hour) / ramp
            return peak
    if 8 + 15/60 <= hour <= 17 + 15/60:
        return 0.02   # just staff during active lecture hours
    if 6.5 <= hour < 20.0:
        return 0.03   # background traffic early morning / evening
    return 0.0


def library_ratio(hour: float, is_exam_period: bool = False) -> float:
    """Library occupancy pattern."""
    if hour < 8.0 or hour >= 21.0:
        return 0.0
    if is_exam_period:
        return 0.85
    if 17 + 15/60 <= hour < 21.0:
        return 0.70
    if 12 + 15/60 <= hour < 13 + 15/60:
        return 0.55
    if 10 + 10/60 <= hour < 10 + 30/60:
        return 0.25
    if 15 + 10/60 <= hour < 15 + 30/60:
        return 0.25
    return 0.12


def office_ratio(hour: float) -> float:
    """Admin/academic staff occupancy during work hours."""
    if hour < 8.5 or hour >= 17.0:
        return 0.0
    if 12 + 15/60 <= hour < 13 + 15/60:
        return 0.25   # most staff at lunch
    return 0.80


def hostel_ratio(hour: float, is_weekend: bool, is_vacation: bool = False) -> float:
    """Hostel occupancy — inverted from academic schedule (full at night, low during day)."""
    if hour >= 22.0 or hour < 6.0:
        return 0.90
    if hour < 7.0:
        return 0.85
    if is_vacation:
        if 10.0 <= hour < 20.0:
            return 0.55
        return 0.80
    if is_weekend:
        if 10.0 <= hour < 20.0:
            return 0.45
        if 20.0 <= hour < 22.0:
            return 0.75
        return 0.80
    if 8.0 <= hour < 17.5:
        return 0.20
    if 17.5 <= hour < 22.0:
        t = (hour - 17.5) / (22.0 - 17.5)
        return 0.20 + t * 0.70
    return 0.80
