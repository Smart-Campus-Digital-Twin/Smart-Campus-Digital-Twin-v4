"""
University of Moratuwa — Academic Calendar model (2023 – 2026).

Data sources
────────────
  Engineering 2024 (rev 22/07/2024), Engineering 2025 & 2026 (rev 16/10/2025)
  IT 2024 v9, IT 2025 v8, IT 2026 v4
  Architecture 2023/2024 (rev 22/08/2024)
  Business & Medicine: inferred from UGS semester structure

Activity types and their approximate on-campus fractions
──────────────────────────────────────────────────────────
  AW        Academic Work (lectures, labs)          100 %
  AW_OL     Online Academic Sessions                 45 %
  EXAM      Written / Design Examinations           100 % (concentrated slots)
  SUPP      Supplementary + Assessments             100 %
  RB        Reading Break / Reading Week             50 %
  MSB       Mid-Semester Break                       20 %
  VAC       Vacation / Inter-semester recess          5 %
  IT        Industrial Training (affected cohort)     0 %   (others normal)
  TUA       Trade Union Action (2024: 3 May–15 Jul)  50 %
  PRE_AC    Pre-Academic / Orientation               12 %
  IS        Independent Studies                      40 %
  MARK      Marking Time (staff only)                 5 %

How zones use this
──────────────────
  Every sensor tick, main.py calls `calendar.get_day(today)` and injects an
  `AcademicDay` into the context dict.  Zone sensors read:

      ctx["academic_day"].congestion_fraction  → scale their base occupancy
      ctx["academic_day"].activity             → choose intra-day pattern
      ctx["academic_day"].is_exam_period       → use exam slot pattern
      ctx["academic_day"].tua_active           → reduce all counts by 50 %
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import yaml

from .holidays import is_holiday

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ── Activity types ────────────────────────────────────────────────────────────

class ActivityType(StrEnum):
    AW      = "AW"       # Academic Work — full lecture schedule
    AW_OL   = "AW_OL"   # Online lectures — 45 % on campus
    EXAM    = "EXAM"     # Written / design exams — 100 %, concentrated sessions
    SUPP    = "SUPP"     # Supplementary work — 100 %
    RB      = "RB"       # Reading break — 50 %
    MSB     = "MSB"      # Mid-semester break — 20 %
    VAC     = "VAC"      # Vacation / recess — 5 %
    IT      = "IT"       # Industrial training period (net effect per month)
    TUA     = "TUA"      # Trade Union Action 2024 — 50 %
    PRE_AC  = "PRE_AC"  # Pre-academic / orientation — 12 %
    IS      = "IS"       # Independent studies — 40 %
    MARK    = "MARK"     # Marking period — 5 %


# Fraction of full campus population present for each activity type (weekday)
ACTIVITY_FRACTION: dict[ActivityType, float] = {
    ActivityType.AW:     1.00,
    ActivityType.AW_OL:  0.45,
    ActivityType.EXAM:   0.95,
    ActivityType.SUPP:   0.95,
    ActivityType.RB:     0.50,
    ActivityType.MSB:    0.20,
    ActivityType.VAC:    0.05,
    ActivityType.IT:     0.40,   # other cohorts still present; net campus effect
    ActivityType.TUA:    0.50,
    ActivityType.PRE_AC: 0.12,
    ActivityType.IS:     0.40,
    ActivityType.MARK:   0.05,
}


# ── AcademicDay (output) ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class AcademicDay:
    """Snapshot of campus academic state for a single calendar date."""
    date:                date
    activity:            ActivityType
    congestion_fraction: float   # 0.0–1.0+ relative to campus max (10 320 students)
    tua_active:          bool    # True only 3 May–15 Jul 2024

    @property
    def is_exam_period(self) -> bool:
        return self.activity in (ActivityType.EXAM, ActivityType.SUPP)

    @property
    def is_low_attendance(self) -> bool:
        """Reading week, online, IS — students mostly at home."""
        return self.activity in (
            ActivityType.RB, ActivityType.AW_OL,
            ActivityType.IS, ActivityType.MSB,
        )

    @property
    def is_essentially_empty(self) -> bool:
        return self.activity in (ActivityType.VAC, ActivityType.MARK)

    @property
    def lecture_scale(self) -> float:
        """
        Multiplier applied to normal lecture-slot occupancy.
        Zones multiply their timetable ratio by this to simulate
        under-attendance during breaks, TUA, online periods etc.
        """
        if self.tua_active:
            return 0.50
        return min(1.0, self.congestion_fraction)


# ── Special period encoding ───────────────────────────────────────────────────

@dataclass(frozen=True)
class _Period:
    start:               date
    end:                 date           # inclusive
    activity:            ActivityType
    congestion_fraction: float | None  # None = use monthly baseline


def _load_academic_calendar():
    path = os.path.join(_DATA_DIR, "academic_calendar.yaml")
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Academic calendar data file not found at {path}. "
            "Ensure simulator/campus/data/academic_calendar.yaml exists."
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError(f"academic_calendar.yaml did not parse to a dict: {path}")

    monthly: dict[int, dict[int, float]] = {}
    for year, months in raw.get("monthly_baseline", {}).items():
        monthly[int(year)] = {int(m): float(v) for m, v in months.items()}

    fallback_val = float(raw.get("fallback_monthly_baseline", 0.90))
    fallback: dict[int, float] = {m: fallback_val for m in range(1, 13)}

    periods: list[_Period] = []
    for p in raw.get("special_periods", []):
        periods.append(_Period(
            start=date.fromisoformat(p["start"]),
            end=date.fromisoformat(p["end"]),
            activity=ActivityType(p["activity"]),
            congestion_fraction=p.get("congestion_fraction"),
        ))
    periods.sort(key=lambda x: x.start)

    return monthly, fallback, periods


_MONTHLY_BASELINE, _FALLBACK_MONTHLY, _SPECIAL_PERIODS = _load_academic_calendar()


# ── AcademicCalendar ──────────────────────────────────────────────────────────

class AcademicCalendar:
    """
    Returns an AcademicDay for any date.

    The lookup priority is:
      1. Special periods (most specific, last match wins within same start).
      2. Monthly baseline congestion fraction.
      3. Public holiday → congestion set to 0.05 (skeleton crew only).
      4. Weekend → congestion set to 0.15 (Architecture + library access).
    """

    def __init__(self) -> None:
        self._cache: dict[date, AcademicDay] = {}

    def get_day(self, d: date) -> AcademicDay:
        if d not in self._cache:
            self._cache[d] = self._compute(d)
        return self._cache[d]

    # convenience
    def congestion_fraction(self, d: date) -> float:
        return self.get_day(d).congestion_fraction

    def activity(self, d: date) -> ActivityType:
        return self.get_day(d).activity

    # ── Internal ──────────────────────────────────────────────────────────────

    def _compute(self, d: date) -> AcademicDay:
        # Weekends: Architecture + library access only (~15 %)
        if d.weekday() >= 5:
            return AcademicDay(
                date=d,
                activity=ActivityType.IS,
                congestion_fraction=0.15,
                tua_active=False,
            )

        # Public holidays
        if is_holiday(d):
            return AcademicDay(
                date=d,
                activity=ActivityType.VAC,
                congestion_fraction=0.05,
                tua_active=False,
            )

        # Monthly baseline
        baseline = _MONTHLY_BASELINE.get(d.year, _FALLBACK_MONTHLY).get(d.month, 0.90)
        activity = ActivityType.AW
        tua      = False

        # Apply special periods (LAST matching period wins)
        for p in _SPECIAL_PERIODS:
            if p.start <= d <= p.end:
                activity = p.activity
                if p.congestion_fraction is not None:
                    baseline = p.congestion_fraction
                if activity == ActivityType.TUA:
                    tua = True

        # Cap at 1.05 (over-capacity is possible but physically bounded)
        baseline = min(1.05, max(0.0, baseline))

        return AcademicDay(
            date=d,
            activity=activity,
            congestion_fraction=baseline,
            tua_active=tua,
        )


# Module-level singleton — import and use directly
calendar = AcademicCalendar()
