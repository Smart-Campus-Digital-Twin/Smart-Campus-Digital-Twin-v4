"""
ML Dataset Generator — University of Moratuwa Smart Campus Digital Twin
=========================================================================
Generates three ML training datasets for 2024-2025 whose schema matches
what the live pipeline assembles at inference time:

    1. Sensor values       -> InfluxDB campus_1m/1h fields (avg, min, max,
                                                     stddev, sum_avg, count, quality_avg)
    2. Room metadata       -> PostgreSQL rooms table (room_id, building_id,
                                                     floor, room_type, capacity)
    3. Calendar context    -> AcademicCalendar YAML (activity_type,
                                                     congestion_fraction, is_exam_period, ...)
    4. Holiday / event ctx -> holidays.yaml + events.yaml (same files used live)
    5. Temporal features   -> derived from window_start (year, month, hour, ...)

This means the inference code does the same assembly:
  pull InfluxDB window → join PostgreSQL rooms → add calendar/event ctx →
    feed to model. No separate cleaning step.

Datasets produced (ml/datasets/):
    canteen_congestion_2024_2025.csv   - 30-min windows, one row per canteen room
    library_congestion_2024_2025.csv   - 30-min windows, one row per library room
    energy_forecast_2024_2025.csv      - hourly windows, one row per building

Columns NOT included (simulation-only, unavailable in live pipeline):
    canteen_base_ratio, library_base_ratio, is_canteen_open, is_library_open

Usage (from project root):
    python ml/generate_datasets.py
"""

from __future__ import annotations

import csv
import math
import os
import random
import sys
import yaml
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional

# ── Project root on sys.path ──────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Simulator imports — single source of truth ───────────────────────────────
from simulator.campus.academic_calendar import calendar as _acal
from simulator.campus.events import EventCalendar
from simulator.campus.holidays import is_holiday
from simulator.campus.schedule import (
    canteen_ratio as _crat,
    library_ratio as _lrat,
    lecture_ratio as _lecrat,
    exam_ratio as _examrat,
    office_ratio as _offrat,
    hostel_ratio as _hosrat,
    is_during_lectures,
)
from simulator.campus.topology import CampusTopology
from simulator.zones.base_zone import _EVENT_CROWD_DRAIN
from simulator.config import config as _sim_config

# ── Singletons ────────────────────────────────────────────────────────────────
_evt_cal = EventCalendar()
_topo    = CampusTopology()

# ── Holiday name lookup ───────────────────────────────────────────────────────
with open(os.path.join(_ROOT, "simulator", "campus", "data", "holidays.yaml"),
          encoding="utf-8") as _f:
    _hol_raw = yaml.safe_load(_f)

_HOL_NAMES: Dict[date, str] = {}
for _yr, _entries in _hol_raw.get("holidays", {}).items():
    for _e in _entries:
        _HOL_NAMES[date.fromisoformat(_e["date"])] = _e["name"]

# ── Campus topology constants ─────────────────────────────────────────────────
_CANTEEN_CAPS: Dict[str, int] = {
    "goda-canteen": 100, "sentra-court": 100,
    "l-canteen": 40, "wala-canteen": 200,
}
_CANTEEN_TOTAL = 440   # sum of above
_LIBRARY_TOTAL = 1000  # 400 + 350 + 250

_SAMPLES_PER_MIN = max(1, int(60 / _sim_config.publish_interval_s))
_WINDOW_MINUTES = 30

# ── Energy model constants (mirrors energy.py exactly) ───────────────────────
_BASE_W: Dict[str, float] = {
    "classroom": 80.0, "lab": 120.0, "office": 60.0, "canteen": 100.0,
    "auditorium": 200.0, "hostel": 50.0, "library": 80.0,
    "server_room": 350.0, "outdoor": 0.0, "default": 80.0,
}
_STBY_W: Dict[str, float] = {
    "classroom": 20.0, "lab": 35.0, "office": 15.0, "canteen": 80.0,
    "auditorium": 30.0, "hostel": 25.0, "library": 40.0,
    "server_room": 350.0, "outdoor": 0.0, "default": 20.0,
}
_OCC_GAIN    = 200.0
_EQUIP_GAIN  = 150.0
_EQUIP_RAMP  = 15 / 60
_LSLOT_S     = 8 + 15 / 60
_LSLOT_E     = 17 + 15 / 60

# ── Output path ───────────────────────────────────────────────────────────────
DATASETS_DIR = os.path.join(_HERE, "datasets")

# ── Building metadata for energy dataset ─────────────────────────────────────
_BLD_TYPE: Dict[str, str] = {
    "lagaan": "outdoor_venue", "multipurpose-hall": "event_hall",
    "hostel-a": "hostel", "hostel-c": "hostel",
    "dept-textile": "academic", "dept-transport": "academic",
    "dept-civil": "academic", "sumanadasa": "academic",
    "goda-canteen": "canteen", "sentra-court": "canteen",
    "l-canteen": "canteen", "wala-canteen": "canteen",
    "faculty-it": "academic", "faculty-business": "academic",
    "dept-maths": "admin", "faculty-medicine": "academic",
    "dept-ete": "academic", "na-hall": "lecture_hall",
    "dept-material": "academic", "dept-chemical": "academic",
    "dept-mechanical": "academic",
    "registrar": "admin", "admin": "admin",
    "dept-design": "academic", "faculty-grad": "academic",
    "library": "library",
}


# =============================================================================
# Shared helpers
# =============================================================================

def _label(r: float) -> str:
    """Map occupancy ratio to a congestion label."""
    if r < 0.25:
        return "Low"
    if r < 0.50:
        return "Moderate"
    if r < 0.75:
        return "Busy"
    return "Packed"


def _ctx(d: date, hour: float) -> dict:
    """Build the full context dict for (date, hour). Private keys prefixed _."""
    ad   = _acal.get_day(d)
    is_h = is_holiday(d)
    is_w = d.weekday() >= 5
    aet  = _evt_cal.active_event_types(d, hour)
    avf  = _evt_cal.active_venue_fill(d, hour)
    evts = sorted(aet)
    return dict(
        academic_day=ad,
        is_holiday=int(is_h),
        holiday_name=_HOL_NAMES.get(d, ""),
        is_weekend=int(is_w),
        activity_type=str(ad.activity.value),
        congestion_fraction=round(ad.congestion_fraction, 4),
        is_exam_period=int(ad.is_exam_period),
        is_low_attendance=int(ad.is_low_attendance),
        is_essentially_empty=int(ad.is_essentially_empty),
        tua_active=int(ad.tua_active),
        lecture_scale=round(ad.lecture_scale, 4),
        active_events="|".join(evts),
        # Private — not written to CSV
        _aet=aet,
        _avf=avf,
        _isH=is_h,
        _isW=is_w,
    )


def _event_mult(aet: set, room_type: str) -> float:
    """Compound crowd-redistribution multiplier for a given room type."""
    mult = 1.0
    for evt in aet:
        mult *= _EVENT_CROWD_DRAIN.get(evt, {}).get(room_type, 1.0)
    return mult


def _stable_hash(text: str) -> int:
    h = 0
    for ch in text:
        h = (h * 31 + ord(ch)) % 100000
    return h


def _occ_window_stats(mean: float, capacity: int, rng: random.Random) -> Dict[str, float]:
    if capacity <= 0:
        return {
            "min": 0.0,
            "max": 0.0,
            "avg": 0.0,
            "stddev": 0.0,
            "sum_avg": 0.0,
            "count": 0,
            "quality_avg": 1.0,
        }

    if mean <= 0.0:
        samples = [0.0] * _WINDOW_MINUTES
    else:
        sigma = max(1.0, capacity * 0.05)
        samples = [
            max(0.0, min(capacity, rng.gauss(mean, sigma)))
            for _ in range(_WINDOW_MINUTES)
        ]

    avg = sum(samples) / len(samples) if samples else 0.0
    var = sum((v - avg) ** 2 for v in samples) / len(samples) if samples else 0.0
    quality_avg = min(1.0, max(0.9, rng.gauss(0.98, 0.01)))

    return {
        "min": round(min(samples), 4) if samples else 0.0,
        "max": round(max(samples), 4) if samples else 0.0,
        "avg": round(avg, 4),
        "stddev": round(math.sqrt(var), 4),
        "sum_avg": round(sum(samples), 4),
        "count": int(_WINDOW_MINUTES * _SAMPLES_PER_MIN),
        "quality_avg": round(quality_avg, 4),
    }


# =============================================================================
# Occupancy ratio functions (exact zone logic)
# =============================================================================

def _canteen_occ_det(hour: float, ctx: dict) -> float:
    """
    Deterministic canteen occupancy ratio for the aggregate of all 4 canteens.
    Replicates CanteenZone._target_ratio() + ZoneOccupancySensor event drain.
    """
    ad, is_h, is_w = ctx["academic_day"], ctx["_isH"], ctx["_isW"]
    avf, aet       = ctx["_avf"], ctx["_aet"]

    if hour < 6.5 or hour >= 20.0:
        return 0.0
    if is_h:
        return 0.15

    base = _crat(hour)
    if is_w:
        base *= 0.40
    if ad.is_essentially_empty:
        base = max(0.05, base * 0.30)
    else:
        base *= ad.congestion_fraction

    # Event crowd drain/boost for canteen room_type
    base *= _event_mult(aet, "canteen")

    # Food festival: sentra-court (100/440 of total) gets a direct venue fill.
    # Weighted-average sentra's boosted fill into the campus canteen aggregate.
    if "sentra-court" in avf:
        sf   = avf["sentra-court"]
        base = (100 * sf + 340 * base) / 440

    return min(1.0, max(0.0, base))


def _library_occ_det(hour: float, ctx: dict) -> float:
    """
    Deterministic library occupancy ratio for the aggregate library building.
    Replicates LibraryZone._target_ratio() + event drain.
    """
    ad, is_h, is_w = ctx["academic_day"], ctx["_isH"], ctx["_isW"]
    aet            = ctx["_aet"]

    if hour < 8.0 or hour >= 21.0:
        return 0.0
    if is_h:
        return 0.20

    base = _lrat(hour, ad.is_exam_period)
    if is_w:
        base *= 0.55

    mult = _event_mult(aet, "library")

    if ad.is_low_attendance:
        return min(1.0, max(0.0, base * 0.80 * ad.congestion_fraction * mult))
    return min(1.0, max(0.0, base * ad.congestion_fraction * mult))


def _room_occ_det(room_type: str, hour: float, ctx: dict, bld_id: str) -> float:
    """
    Deterministic occupancy ratio for any room type in any building.
    Handles event venue-fill override and crowd redistribution.
    """
    ad, is_h, is_w = ctx["academic_day"], ctx["_isH"], ctx["_isW"]
    avf, aet       = ctx["_avf"], ctx["_aet"]

    # Venue fill override (this building is hosting an event)
    if bld_id in avf:
        return float(avf[bld_id])

    if room_type in ("server_room", "outdoor"):
        return 0.0

    mult = _event_mult(aet, room_type)

    if room_type in ("classroom", "lab"):
        if hour >= 22.0 or hour < 6.0:
            return 0.0
        if is_h:
            return 0.03
        if is_w:
            return 0.0
        base = _examrat(hour) if ad.is_exam_period else _lecrat(hour)
        return min(1.0, base * ad.lecture_scale * mult)

    if room_type == "canteen":
        return min(1.0, _canteen_occ_det(hour, ctx) * mult)

    if room_type == "library":
        return min(1.0, _library_occ_det(hour, ctx) * mult)

    if room_type == "office":
        if is_h or is_w:
            return 0.0
        return _offrat(hour)

    if room_type == "hostel":
        return _hosrat(hour, is_w, ad.is_essentially_empty)

    if room_type == "auditorium":
        if hour < 6.0 or hour >= 22.0 or is_h or is_w:
            return 0.0
        if ad.is_exam_period and is_during_lectures(hour):
            return 0.85 * ad.lecture_scale
        return 0.0

    return 0.0


def _room_energy_w(
    room_type: str, occ: float, hour: float, rng: random.Random
) -> float:
    """
    Energy draw in Watts for one room. Mirrors energy.py exactly.
    """
    if room_type == "server_room":
        return max(200.0, min(500.0, 350.0 + rng.gauss(0, 15.0)))
    if room_type == "outdoor":
        return 0.0

    base = _BASE_W.get(room_type, 80.0)
    stby = _STBY_W.get(room_type, 20.0)

    if (hour < 6.5 or hour >= 22.0) and occ < 0.02:
        return max(0.0, stby + rng.gauss(0, 2.0))

    occ_load  = _OCC_GAIN * occ
    ramp_s    = _LSLOT_S - _EQUIP_RAMP
    if hour < ramp_s or hour > _LSLOT_E:
        ef = 0.0
    elif hour < _LSLOT_S:
        ef = (hour - ramp_s) / _EQUIP_RAMP
    else:
        ef = 1.0
    equip = _EQUIP_GAIN * occ * ef
    total = base + occ_load + equip + rng.gauss(0, 8.0)
    return max(stby, min(500.0, total))


# =============================================================================
# Dataset 1 — Canteen Congestion (30-min resolution)
# =============================================================================

_OCC_FIELDS = [
    "timestamp",
    "is_weekend", "is_holiday", "holiday_name",
    "activity_type", "congestion_fraction",
    "is_exam_period", "is_low_attendance", "is_essentially_empty",
    "tua_active", "lecture_scale",
    "active_events",
    "building_id", "room_id", "floor", "room_type", "capacity",
    "sensor_type",
    "min", "max", "avg", "stddev", "sum_avg", "count", "quality_avg",
]

_CANTEEN_FIELDS = _OCC_FIELDS


def gen_canteen_dataset(out_path: str) -> None:
    print(f"  Generating canteen dataset…")

    warmup_start = date(2023, 12, 25)
    data_start   = date(2024, 1, 1)
    data_end     = date(2025, 12, 31)

    rooms = [r for r in _topo.all_rooms() if r.room_type == "canteen"]
    room_series: Dict[str, List[dict]] = {r.room_id: [] for r in rooms}

    cur = warmup_start
    while cur <= data_end:
        for slot in range(48):
            h   = slot * 0.5
            ctx = _ctx(cur, h)
            dt = datetime(cur.year, cur.month, cur.day, slot // 2, (slot % 2) * 30, 0, tzinfo=ZoneInfo(_sim_config.campus_timezone))
            ts = dt.isoformat()

            for room in rooms:
                ratio = _room_occ_det(room.room_type, h, ctx, room.building_id)
                seed  = cur.toordinal() * 48 * 1000 + slot * 100 + _stable_hash(room.room_id) + 100_001
                rng   = random.Random(seed)
                stats = _occ_window_stats(ratio * room.capacity, room.capacity, rng)

                room_series[room.room_id].append({
                    "timestamp": ts,
                    "is_weekend": ctx["is_weekend"],
                    "is_holiday": ctx["is_holiday"],
                    "holiday_name": ctx["holiday_name"],
                    "activity_type": ctx["activity_type"],
                    "congestion_fraction": ctx["congestion_fraction"],
                    "is_exam_period": ctx["is_exam_period"],
                    "is_low_attendance": ctx["is_low_attendance"],
                    "is_essentially_empty": ctx["is_essentially_empty"],
                    "tua_active": ctx["tua_active"],
                    "lecture_scale": ctx["lecture_scale"],
                    "active_events": ctx["active_events"],
                    "building_id": room.building_id,
                    "room_id": room.room_id,
                    "floor": room.floor,
                    "room_type": room.room_type,
                    "capacity": room.capacity,
                    "sensor_type": "occupancy",
                    **stats,
                })
        cur += timedelta(days=1)

    warmup_n = (data_start - warmup_start).days * 48
    all_rows: List[tuple] = []
    for room_id, series in room_series.items():
        for i, row in enumerate(series):
            all_rows.append((row["timestamp"], room_id, i))
    all_rows.sort(key=lambda x: (x[0], x[1]))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CANTEEN_FIELDS)
        w.writeheader()
        for _, room_id, i in all_rows:
            if i < warmup_n:
                continue
            series = room_series[room_id]
            row    = series[i]
            w.writerow({k: row[k] for k in _CANTEEN_FIELDS if k in row})
            written += 1

    print(f"    DONE {written:,} rows  ->  {out_path}")


# =============================================================================
# Dataset 2 — Library Congestion (30-min resolution)
# =============================================================================

_LIBRARY_FIELDS = _OCC_FIELDS


def gen_library_dataset(out_path: str) -> None:
    print(f"  Generating library dataset…")

    warmup_start = date(2023, 12, 25)
    data_start   = date(2024, 1, 1)
    data_end     = date(2025, 12, 31)

    rooms = [r for r in _topo.all_rooms() if r.room_type == "library"]
    room_series: Dict[str, List[dict]] = {r.room_id: [] for r in rooms}

    cur = warmup_start
    while cur <= data_end:
        for slot in range(48):
            h   = slot * 0.5
            ctx = _ctx(cur, h)
            dt = datetime(cur.year, cur.month, cur.day, slot // 2, (slot % 2) * 30, 0, tzinfo=ZoneInfo(_sim_config.campus_timezone))
            ts = dt.isoformat()

            for room in rooms:
                ratio = _room_occ_det(room.room_type, h, ctx, room.building_id)
                seed  = cur.toordinal() * 48 * 1000 + slot * 100 + _stable_hash(room.room_id) + 200_001
                rng   = random.Random(seed)
                stats = _occ_window_stats(ratio * room.capacity, room.capacity, rng)

                room_series[room.room_id].append({
                    "timestamp": ts,
                    "is_weekend": ctx["is_weekend"],
                    "is_holiday": ctx["is_holiday"],
                    "holiday_name": ctx["holiday_name"],
                    "activity_type": ctx["activity_type"],
                    "congestion_fraction": ctx["congestion_fraction"],
                    "is_exam_period": ctx["is_exam_period"],
                    "is_low_attendance": ctx["is_low_attendance"],
                    "is_essentially_empty": ctx["is_essentially_empty"],
                    "tua_active": ctx["tua_active"],
                    "lecture_scale": ctx["lecture_scale"],
                    "active_events": ctx["active_events"],
                    "building_id": room.building_id,
                    "room_id": room.room_id,
                    "floor": room.floor,
                    "room_type": room.room_type,
                    "capacity": room.capacity,
                    "sensor_type": "occupancy",
                    **stats,
                })
        cur += timedelta(days=1)

    warmup_n = (data_start - warmup_start).days * 48
    all_rows: List[tuple] = []
    for room_id, series in room_series.items():
        for i, row in enumerate(series):
            all_rows.append((row["timestamp"], room_id, i))
    all_rows.sort(key=lambda x: (x[0], x[1]))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_LIBRARY_FIELDS)
        w.writeheader()
        for _, room_id, i in all_rows:
            if i < warmup_n:
                continue
            series = room_series[room_id]
            row    = series[i]
            w.writerow({k: row[k] for k in _LIBRARY_FIELDS if k in row})
            written += 1

    print(f"    DONE {written:,} rows  ->  {out_path}")


# =============================================================================
# Dataset 3 — Building Energy Forecast (hourly, per building)
# =============================================================================

_ENERGY_FIELDS = [
    "timestamp",
    "is_weekend", "is_holiday", "holiday_name",
    "activity_type", "congestion_fraction",
    "is_exam_period", "is_low_attendance", "is_essentially_empty",
    "tua_active", "lecture_scale",
    "active_events",
    "building_id", "building_type", "n_rooms", "total_capacity",
    "avg_occupancy_ratio",
    "total_energy_w", "total_energy_kwh",
]


def gen_energy_dataset(out_path: str) -> None:
    print(f"  Generating energy dataset…")

    warmup_start = date(2023, 12, 25)
    data_start   = date(2024, 1, 1)
    data_end     = date(2025, 12, 31)

    # One series per building: list of dicts in chronological order
    bld_ids   = list(_topo.buildings.keys())
    bld_series: Dict[str, List[dict]] = {b: [] for b in bld_ids}

    cur = warmup_start
    while cur <= data_end:
        for hour in range(24):
            h   = float(hour)
            ctx = _ctx(cur, h)
            dt = datetime(cur.year, cur.month, cur.day, hour, 0, 0, tzinfo=ZoneInfo(_sim_config.campus_timezone))
            ts = dt.isoformat()

            for bld_id in bld_ids:
                bld   = _topo.buildings[bld_id]
                rooms = bld.rooms

                # Compute per-room energy and aggregate
                total_w   = 0.0
                total_occ = 0.0
                total_cap = 0
                n_rooms   = 0
                for room in rooms:
                    n_rooms += 1
                    cap      = room.capacity
                    rt       = room.room_type
                    occ_det  = _room_occ_det(rt, h, ctx, bld_id)
                    rng      = random.Random(
                        cur.toordinal() * 24 * 10_000
                        + hour * 10_000
                        + hash(room.room_id) % 10_000
                        + 300_001
                    )
                    # Occupancy noise (±2%)
                    occ = max(0.0, min(1.0, occ_det + rng.gauss(0, 0.02)))
                    energy_w = _room_energy_w(rt, occ, h, rng)
                    total_w   += energy_w
                    total_occ += occ
                    total_cap += cap

                avg_occ    = round(total_occ / n_rooms, 4) if n_rooms > 0 else 0.0
                energy_kwh = round(total_w / 1000.0, 4)  # W → kWh for 1 h

                bld_series[bld_id].append({
                    "timestamp": ts,
                    "is_weekend": ctx["is_weekend"],
                    "is_holiday": ctx["is_holiday"],
                    "holiday_name": ctx["holiday_name"],
                    "activity_type": ctx["activity_type"],
                    "congestion_fraction": ctx["congestion_fraction"],
                    "is_exam_period": ctx["is_exam_period"],
                    "is_low_attendance": ctx["is_low_attendance"],
                    "is_essentially_empty": ctx["is_essentially_empty"],
                    "tua_active": ctx["tua_active"],
                    "lecture_scale": ctx["lecture_scale"],
                    "active_events": ctx["active_events"],
                    "building_id": bld_id,
                    "building_type": _BLD_TYPE.get(bld_id, "other"),
                    "n_rooms": n_rooms,
                    "total_capacity": total_cap,
                    "avg_occupancy_ratio": avg_occ,
                    "total_energy_w": round(total_w, 2),
                    "total_energy_kwh": energy_kwh,
                })
        cur += timedelta(days=1)

    # Write all buildings interleaved chronologically (sort by timestamp then bld)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    warmup_n = (data_start - warmup_start).days * 24  # hours to skip per building

    # Build list of all (timestamp, bld_id, row_idx) sorted by timestamp
    all_rows: List[tuple] = []
    for bld_id, series in bld_series.items():
        for i, row in enumerate(series):
            all_rows.append((row["timestamp"], bld_id, i))
    all_rows.sort(key=lambda x: (x[0], x[1]))

    written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_ENERGY_FIELDS)
        w.writeheader()
        for ts, bld_id, i in all_rows:
            # Skip warm-up rows
            if i < warmup_n:
                continue
            series  = bld_series[bld_id]
            row     = series[i]
            w.writerow({k: row[k] for k in _ENERGY_FIELDS if k in row})
            written += 1

    print(f"    DONE {written:,} rows  ->  {out_path}")


# =============================================================================
# Entry point
# =============================================================================

def main() -> None:
    os.makedirs(DATASETS_DIR, exist_ok=True)
    print(f"\nSmart Campus ML Dataset Generator")
    print(f"Output directory: {DATASETS_DIR}\n")

    gen_canteen_dataset(
        os.path.join(DATASETS_DIR, "canteen_congestion_2024_2025.csv")
    )
    gen_library_dataset(
        os.path.join(DATASETS_DIR, "library_congestion_2024_2025.csv")
    )
    gen_energy_dataset(
        os.path.join(DATASETS_DIR, "energy_forecast_2024_2025.csv")
    )

    print("\nAll datasets generated successfully.")
    print("Column summary:")
    print(f"  canteen_congestion  : {len(_CANTEEN_FIELDS)} columns, ~35 040 rows")
    print(f"  library_congestion  : {len(_LIBRARY_FIELDS)} columns, ~35 040 rows")
    print(f"  energy_forecast     : {len(_ENERGY_FIELDS)} columns, ~456 960 rows")


if __name__ == "__main__":
    main()
