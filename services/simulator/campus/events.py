"""
Campus event calendar.

Generates a deterministic (seeded on the date) list of events for any given day.
The same date always returns the same events, so the live simulator and the
historical dataset generator stay perfectly consistent.

Event types and default venues
────────────────────────────────
  padura        → lagaan only                                 (18:00–22:00)
  food_festival → lagaan + sentra-court                       (10:00–20:00, all-day)
  symposium     → multipurpose-hall only                      (08:00–17:00, all-day)
  workshop      → na-hall                                      (09:00–13:00 or 13:00–17:00)
  orientation   → multipurpose-hall                           (08:00–12:00)
  career_fair   → multipurpose-hall + na-hall                 (09:00–16:00)
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

import yaml

from .holidays import is_holiday

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_events_config() -> dict:
    path = os.path.join(_DATA_DIR, "events.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


_EVT_CFG: dict = _load_events_config()



# ── Event dataclass ───────────────────────────────────────────────────────────
@dataclass
class CampusEvent:
    """A single campus event on a given day."""
    name:       str
    event_type: str          # padura | food_festival | symposium | workshop |
                             # orientation | career_fair
    start_hour: float        # e.g. 18.0 = 18:00
    end_hour:   float        # e.g. 22.0 = 22:00
    # building_id → target occupancy factor (0-1) while this event is active
    venue_fill: dict[str, float] = field(default_factory=dict)

    def is_active_at(self, hour: float) -> bool:
        return self.start_hour <= hour < self.end_hour


# ── Calendar ──────────────────────────────────────────────────────────────────
class EventCalendar:
    """
    Deterministic campus event calendar.

    Uses holidays module for SL public holidays. Events are not scheduled
    on holidays. Padura schedule is pre-built for consistency.

    Usage:
        cal = EventCalendar()
        events = cal.events_for_date(date.today())
        active_venues = cal.active_venue_fill(today, hour)
    """

    def __init__(self) -> None:
        self._cache: dict[date, list[CampusEvent]] = {}
        # Pre-build the full padura schedule so dates don't collide
        self._padura_by_date: dict[date, list[CampusEvent]] = {}
        self._build_padura_schedule(range(2022, 2028))

    # ── Public API ────────────────────────────────────────────────────────────

    def events_for_date(self, d: date) -> list[CampusEvent]:
        if d not in self._cache:
            self._cache[d] = self._generate(d)
        return self._cache[d]

    def active_venue_fill(self, d: date, hour: float) -> dict[str, float]:
        """
        Returns a dict mapping building_id → occupancy factor for all events
        currently happening at `hour` on date `d`.  Multiple events can
        affect different venues simultaneously.
        """
        fill: dict[str, float] = {}
        for evt in self.events_for_date(d):
            if evt.is_active_at(hour):
                for bld, factor in evt.venue_fill.items():
                    fill[bld] = max(fill.get(bld, 0.0), factor)
        return fill

    def active_event_types(self, d: date, hour: float) -> set:
        """Return the set of event_type strings active at `hour` on `d`."""
        return {
            evt.event_type
            for evt in self.events_for_date(d)
            if evt.is_active_at(hour)
        }

    # ── Padura pre-schedule ─────────────────────────────────────────────────────

    def _build_padura_schedule(self, years) -> None:
        """Assign each dept a deterministic padura date for each semester."""
        pcfg = _EVT_CFG["padura"]
        departments = pcfg["departments"]
        sem1_lo, sem1_hi = pcfg["sem1_doy_range"]
        sem2_lo, sem2_hi = pcfg["sem2_doy_range"]
        fill_lo, fill_hi = pcfg["fill_range"]

        for year in years:
            for dept_info in departments:
                dept_name = dept_info["name"]
                for semester in (1, 2):
                    rng = random.Random(
                        hash(f"{dept_name}|{year}|{semester}") & 0xFFFF_FFFF
                    )
                    doy_lo, doy_hi = (
                        (sem1_lo, sem1_hi) if semester == 1 else (sem2_lo, sem2_hi)
                    )
                    # Pick a candidate day, avoid weekends + holidays
                    attempts = 0
                    while attempts < 30:
                        doy = rng.randint(doy_lo, doy_hi)
                        try:
                            d = date(year, 1, 1) + timedelta(days=doy - 1)
                        except ValueError:
                            attempts += 1
                            continue
                        if d.weekday() < 5 and not is_holiday(d):
                            break
                        attempts += 1
                    else:
                        continue   # couldn't find a free day

                    fill = rng.uniform(fill_lo, fill_hi)
                    venue = dept_info.get("padura_venue", pcfg["venue"])
                    evt  = CampusEvent(
                        name       = f"{dept_name} Dept Padura",
                        event_type = "padura",
                        start_hour = float(pcfg["start_hour"]),
                        end_hour   = float(pcfg["end_hour"]),
                        venue_fill = {venue: fill},
                    )
                    self._padura_by_date.setdefault(d, []).append(evt)

    # ── Daily event generation ────────────────────────────────────────────────

    def _generate(self, d: date) -> list[CampusEvent]:
        events: list[CampusEvent] = []
        holiday = is_holiday(d)
        is_weekend = d.weekday() >= 5   # Sat=5, Sun=6
        doy        = d.timetuple().tm_yday
        year       = d.year

        # Padura (pre-scheduled)
        if d in self._padura_by_date:
            events.extend(self._padura_by_date[d])

        # No academic events on public holidays
        if holiday:
            return events

        rng = random.Random(d.toordinal() * 31337 + 7)

        # ── Food festival ──────────────────────────────────────────────────────────
        ff = _EVT_CFG["food_festival"]
        for offset_month in ff["months"]:
            festival_rng = random.Random(year * 1000 + offset_month)
            festival_day = festival_rng.randint(*ff["day_range"])
            try:
                festival_date = date(year, offset_month, festival_day)
            except ValueError:
                continue
            if festival_date == d and festival_rng.random() < ff["probability"]:
                events.append(CampusEvent(
                    name       = festival_rng.choice(ff["names"]),
                    event_type = "food_festival",
                    start_hour = float(ff["start_hour"]),
                    end_hour   = float(ff["end_hour"]),
                    venue_fill = {v: festival_rng.uniform(*r) for v, r in ff["venue_fill"].items()},
                ))

        # ── Symposium ─────────────────────────────────────────────────────────────────
        sym_cfg = _EVT_CFG["symposium"]
        for faculty in sym_cfg["faculties"]:
            sym_month = faculty["sem1_month"] if doy < 180 else faculty["sem2_month"]
            sym_rng = random.Random(hash(f"sym{faculty['name']}{year}{sym_month}") & 0xFFFF)
            sym_day = sym_rng.randint(*sym_cfg["day_range"])
            try:
                sym_date = date(year, sym_month, sym_day)
            except ValueError:
                continue
            if sym_date == d and sym_date.weekday() < 5:
                fill = sym_rng.uniform(*sym_cfg["fill_range"])
                events.append(CampusEvent(
                    name       = f"{faculty['name']} Annual Symposium",
                    event_type = "symposium",
                    start_hour = float(sym_cfg["start_hour"]),
                    end_hour   = float(sym_cfg["end_hour"]),
                    venue_fill = {sym_cfg["venue"]: fill},
                ))

        # ── Orientation ───────────────────────────────────────────────────────────────
        ori_cfg = _EVT_CFG["orientation"]
        for ori_month in ori_cfg["months"]:
            ori_rng = random.Random(year * 500 + ori_month)
            ori_day = ori_rng.randint(*ori_cfg["day_range"])
            try:
                ori_date = date(year, ori_month, ori_day)
            except ValueError:
                continue
            if ori_date == d and ori_date.weekday() < 5:
                events.append(CampusEvent(
                    name       = ori_cfg["name"],
                    event_type = "orientation",
                    start_hour = float(ori_cfg["start_hour"]),
                    end_hour   = float(ori_cfg["end_hour"]),
                    venue_fill = {ori_cfg["venue"]: ori_rng.uniform(*ori_cfg["fill_range"])},
                ))

        # ── Career fair ──────────────────────────────────────────────────────────────
        cf_cfg = _EVT_CFG["career_fair"]
        for cf_month in cf_cfg["months"]:
            cf_rng = random.Random(year * 700 + cf_month)
            cf_day = cf_rng.randint(*cf_cfg["day_range"])
            try:
                cf_date = date(year, cf_month, cf_day)
            except ValueError:
                continue
            if cf_date == d and cf_date.weekday() < 5:
                dept_venue = cf_rng.choice(cf_cfg["dept_venues"])
                events.append(CampusEvent(
                    name       = cf_cfg["name"],
                    event_type = "career_fair",
                    start_hour = float(cf_cfg["start_hour"]),
                    end_hour   = float(cf_cfg["end_hour"]),
                    venue_fill = {
                        cf_cfg["main_venue"]: cf_rng.uniform(*cf_cfg["main_fill_range"]),
                        dept_venue:           cf_rng.uniform(*cf_cfg["dept_fill_range"]),
                    },
                ))

        # ── Workshop ───────────────────────────────────────────────────────────────────
        ws_cfg = _EVT_CFG["workshop"]
        if not is_weekend and rng.random() < ws_cfg["probability"]:
            am = rng.random() < 0.5
            s_h, e_h = ws_cfg["am_hours"] if am else ws_cfg["pm_hours"]
            events.append(CampusEvent(
                name       = rng.choice(ws_cfg["names"]),
                event_type = "workshop",
                start_hour = float(s_h),
                end_hour   = float(e_h),
                venue_fill = {rng.choice(ws_cfg["venues"]): rng.uniform(*ws_cfg["fill_range"])},
            ))

        # ── Movie night (business faculty, monthly) ────────────────────────────────
        mn_cfg = _EVT_CFG.get("movie_night")
        if mn_cfg:
            mn_rng = random.Random(year * 150 + d.month)
            mn_day = mn_rng.randint(*mn_cfg["day_range"])
            try:
                mn_date = date(year, d.month, mn_day)
            except ValueError:
                mn_date = None
            if mn_date == d and not holiday and mn_rng.random() < mn_cfg["probability"]:
                events.append(CampusEvent(
                    name       = mn_rng.choice(mn_cfg["names"]),
                    event_type = "movie_night",
                    start_hour = float(mn_cfg["start_hour"]),
                    end_hour   = float(mn_cfg["end_hour"]),
                    venue_fill = {mn_cfg["venue"]: mn_rng.uniform(*mn_cfg["fill_range"])},
                ))

        return events
