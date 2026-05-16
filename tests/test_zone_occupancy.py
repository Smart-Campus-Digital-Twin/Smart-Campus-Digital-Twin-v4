"""Unit tests for simulator zone occupancy models."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _academic_day(activity: str = "AW", congestion: float = 1.0, tua: bool = False):
    """Return a minimal AcademicDay-like mock."""
    d = MagicMock()
    d.activity            = MagicMock()
    d.activity.value      = activity
    d.congestion_fraction = congestion
    d.tua_active          = tua
    d.is_exam_period      = activity in ("EXAM", "SUPP")
    d.is_low_attendance   = activity in ("RB", "AW_OL", "IS", "MSB")
    d.is_essentially_empty = activity in ("VAC", "MARK")
    d.lecture_scale       = 0.5 if tua else min(1.0, congestion)
    return d


def _ctx(hour: float = 10.0, day_of_week: int = 0, is_holiday: bool = False,
         activity: str = "AW", congestion: float = 1.0, tua: bool = False,
         active_venue_fill: dict | None = None, active_event_types: list | None = None):
    from simulator.zones.base_zone import ZoneContext
    return ZoneContext(
        hour=hour,
        day_of_week=day_of_week,
        is_holiday=is_holiday,
        academic_day=_academic_day(activity, congestion, tua),
        active_venue_fill=active_venue_fill or {},
        active_event_types=frozenset(active_event_types or []),
        building_id="TEST",
        room_id="TEST-001",
    )


def _room(room_type: str, capacity: int = 60, room_id: str = "TEST-001",
          building_id: str = "ENG", floor: int = 1):
    r = MagicMock()
    r.room_type    = room_type
    r.capacity     = capacity
    r.room_id      = room_id
    r.building_id  = building_id
    r.floor        = floor
    return r


# ---------------------------------------------------------------------------
# Classroom tests
# ---------------------------------------------------------------------------

def test_classroom_peak_lecture_time():
    from simulator.zones.classroom import ClassroomZone
    zone = ClassroomZone(_room("classroom"))
    ratio = zone._target_ratio(_ctx(hour=10.0))
    assert ratio > 0.5, f"Expected busy classroom at 10:00, got {ratio}"


def test_classroom_midnight_empty():
    from simulator.zones.classroom import ClassroomZone
    zone = ClassroomZone(_room("classroom"))
    ratio = zone._target_ratio(_ctx(hour=0.0))
    assert ratio < 0.1, f"Expected empty classroom at 00:00, got {ratio}"


def test_classroom_holiday_low():
    from simulator.zones.classroom import ClassroomZone
    zone = ClassroomZone(_room("classroom"))
    ratio = zone._target_ratio(_ctx(hour=10.0, is_holiday=True))
    assert ratio < 0.1


def test_classroom_weekend_low():
    from simulator.zones.classroom import ClassroomZone
    zone = ClassroomZone(_room("classroom"))
    ratio = zone._target_ratio(_ctx(hour=10.0, day_of_week=5))
    assert ratio < 0.2


def test_classroom_exam_period_different_from_lecture():
    from simulator.zones.classroom import ClassroomZone
    zone = ClassroomZone(_room("classroom"))
    lecture_ratio = zone._target_ratio(_ctx(hour=10.0, activity="AW"))
    exam_ratio    = zone._target_ratio(_ctx(hour=10.0, activity="EXAM"))
    assert lecture_ratio != exam_ratio


# ---------------------------------------------------------------------------
# Canteen tests
# ---------------------------------------------------------------------------

def test_canteen_lunch_rush_high():
    from simulator.zones.canteen import CanteenZone
    zone = CanteenZone(_room("canteen"))
    ratio = zone._target_ratio(_ctx(hour=12.5))
    assert ratio > 0.5, f"Expected busy canteen at 12:30, got {ratio}"


def test_canteen_3am_empty():
    from simulator.zones.canteen import CanteenZone
    zone = CanteenZone(_room("canteen"))
    ratio = zone._target_ratio(_ctx(hour=3.0))
    assert ratio < 0.05


# ---------------------------------------------------------------------------
# Library tests
# ---------------------------------------------------------------------------

def test_library_open_hours_nonzero():
    from simulator.zones.library import LibraryZone
    zone = LibraryZone(_room("library"))
    ratio = zone._target_ratio(_ctx(hour=14.0))
    assert ratio > 0.0


def test_library_closed_hours_near_zero():
    from simulator.zones.library import LibraryZone
    zone = LibraryZone(_room("library"))
    ratio = zone._target_ratio(_ctx(hour=2.0))
    assert ratio < 0.05


# ---------------------------------------------------------------------------
# Server room tests
# ---------------------------------------------------------------------------

def test_server_room_has_no_occupancy_sensors():
    from simulator.sensors.occupancy import OccupancySensor
    from simulator.zones.server_room import ServerRoomZone
    zone = ServerRoomZone(_room("server_room"))
    occ_sensors = [s for s in zone.sensors if isinstance(s, OccupancySensor)]
    assert len(occ_sensors) == 0


# ---------------------------------------------------------------------------
# Output bounds — all zone _target_ratio must return [0, 1]
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("zone_module,zone_class,room_type", [
    ("simulator.zones.classroom",  "ClassroomZone",  "classroom"),
    ("simulator.zones.canteen",    "CanteenZone",    "canteen"),
    ("simulator.zones.library",    "LibraryZone",    "library"),
    ("simulator.zones.office",     "OfficeZone",     "office"),
    ("simulator.zones.auditorium", "AuditoriumZone", "auditorium"),
    ("simulator.zones.hostel",     "HostelZone",     "hostel"),
    ("simulator.zones.outdoor",    "OutdoorZone",    "outdoor"),
])
def test_target_ratio_bounded(zone_module, zone_class, room_type):
    import importlib
    mod  = importlib.import_module(zone_module)
    cls  = getattr(mod, zone_class)
    zone = cls(_room(room_type))
    for hour in [0, 6, 8, 10, 12, 14, 17, 20, 23]:
        ratio = zone._target_ratio(_ctx(hour=float(hour)))
        assert 0.0 <= ratio <= 1.0, (
            f"{zone_class} at hour={hour} returned out-of-bounds ratio {ratio}"
        )
