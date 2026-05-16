"""
Sri Lanka public holidays — loaded from data/holidays.yaml.

Single source of truth imported by AcademicCalendar, EventCalendar, and all zone sensors.
Add future years to data/holidays.yaml; nothing else needs to change.
"""

from __future__ import annotations

import os
from datetime import date

import yaml

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_holidays() -> dict[int, frozenset[date]]:
    path = os.path.join(_DATA_DIR, "holidays.yaml")
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Holidays data file not found at {path}. "
            "Ensure simulator/campus/data/holidays.yaml exists."
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError(f"holidays.yaml did not parse to a dict: {path}")
    by_year: dict[int, frozenset[date]] = {}
    for year, entries in raw.get("holidays", {}).items():
        by_year[int(year)] = frozenset(date.fromisoformat(e["date"]) for e in entries)
    return by_year


_BY_YEAR: dict[int, frozenset[date]] = _load_holidays()


def is_holiday(d: date) -> bool:
    """Return True if `d` is a Sri Lanka public holiday."""
    return d in _BY_YEAR.get(d.year, frozenset())


def holidays_for_year(year: int) -> frozenset[date]:
    return _BY_YEAR.get(year, frozenset())


def all_holidays() -> frozenset[date]:
    result: set = set()
    for s in _BY_YEAR.values():
        result |= s
    return frozenset(result)
