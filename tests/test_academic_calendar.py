"""Unit tests for simulator/campus/academic_calendar.py."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from simulator.campus.academic_calendar import (
    _SPECIAL_PERIODS,
    AcademicCalendar,
    AcademicDay,
    ActivityType,
)


@pytest.fixture()
def calendar() -> AcademicCalendar:
    return AcademicCalendar()


# ---------------------------------------------------------------------------
# Weekend logic
# ---------------------------------------------------------------------------

def test_saturday_returns_low_congestion(calendar):
    saturday = date(2025, 5, 3)   # Saturday
    assert saturday.weekday() == 5
    day = calendar.get_day(saturday)
    assert day.congestion_fraction <= 0.20


def test_sunday_returns_low_congestion(calendar):
    sunday = date(2025, 5, 4)
    assert sunday.weekday() == 6
    day = calendar.get_day(sunday)
    assert day.congestion_fraction <= 0.20


# ---------------------------------------------------------------------------
# Public holiday logic
# ---------------------------------------------------------------------------

def test_public_holiday_returns_vac_activity(calendar):
    with patch("simulator.campus.academic_calendar.is_holiday", return_value=True):
        day = calendar._compute(date(2025, 4, 14))  # bypass cache
    assert day.activity == ActivityType.VAC
    assert day.congestion_fraction <= 0.10


# ---------------------------------------------------------------------------
# Special period lookup
# ---------------------------------------------------------------------------

def test_special_period_overrides_baseline(calendar):
    """Any date inside a VAC special period must return VAC activity."""
    vac_periods = [p for p in _SPECIAL_PERIODS if p.activity == ActivityType.VAC]
    if not vac_periods:
        pytest.skip("No VAC periods in calendar data")
    p   = vac_periods[0]
    day = calendar.get_day(p.start)
    assert day.activity == ActivityType.VAC


def test_tua_period_sets_flag(calendar):
    """Dates inside a TUA special period must have tua_active=True."""
    tua_periods = [p for p in _SPECIAL_PERIODS if p.activity == ActivityType.TUA]
    if not tua_periods:
        pytest.skip("No TUA periods in calendar data")
    p   = tua_periods[0]
    day = calendar.get_day(p.start)
    assert day.tua_active is True


# ---------------------------------------------------------------------------
# AcademicDay properties
# ---------------------------------------------------------------------------

def test_is_exam_period_true_for_exam(calendar):
    with patch.object(calendar, "_compute") as mock_compute:
        mock_compute.return_value = AcademicDay(
            date=date(2025, 6, 2),
            activity=ActivityType.EXAM,
            congestion_fraction=0.95,
            tua_active=False,
        )
        day = calendar._compute(date(2025, 6, 2))
    assert day.is_exam_period is True


def test_is_exam_period_false_for_aw():
    day = AcademicDay(date(2025, 5, 5), ActivityType.AW, 1.0, False)
    assert day.is_exam_period is False


def test_lecture_scale_halved_during_tua():
    day = AcademicDay(date(2025, 6, 1), ActivityType.TUA, 1.0, tua_active=True)
    assert day.lecture_scale == 0.50


def test_lecture_scale_capped_at_one():
    day = AcademicDay(date(2025, 5, 5), ActivityType.AW, 1.10, tua_active=False)
    assert day.lecture_scale == 1.0


def test_congestion_fraction_bounded(calendar):
    """All returned congestion fractions must lie in [0.0, 1.05]."""
    sample_dates = [date(2025, m, 1) for m in range(1, 13)]
    for d in sample_dates:
        day = calendar.get_day(d)
        assert 0.0 <= day.congestion_fraction <= 1.05, (
            f"Out-of-bounds congestion {day.congestion_fraction} for {d}"
        )


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def test_get_day_returns_same_instance_on_repeated_calls(calendar):
    d = date(2025, 5, 5)
    assert calendar.get_day(d) is calendar.get_day(d)
