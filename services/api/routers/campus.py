"""
Public campus endpoints — no JWT required.

GET /campus/zones
  Returns Zone[] matching the frontend DashboardTypes.ts Zone shape exactly.
  Aggregates: sum for occupancy/energy, mean for temperature, count for anomalies.

GET /campus/buildings/{building_id}/rooms
  Returns per-room live sensor data for the indoor floor plan component.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.clients import InfluxAPIClient, PostgresClient, RedisCache
from api.dependencies import get_influx, get_postgres, get_redis

router = APIRouter(prefix="/campus", tags=["Campus (public)"])

# ---------------------------------------------------------------------------
# Frontend zone id → simulator building_id
# ---------------------------------------------------------------------------

_ZONE_TO_BUILDING: dict[str, str] = {
    "lagaan":       "lagaan",
    "conference":   "multipurpose-hall",
    "hostel_a":     "hostel-a",
    "textile":      "dept-textile",
    "transport":    "dept-transport",
    "civil":        "dept-civil",
    "cse":          "sumanadasa",
    "Goda canteen": "goda-canteen",
    "Sentra":       "sentra-court",
    "canteen":      "l-canteen",
    "it":           "faculty-it",
    "hostel":       "hostel-c",
    "buildeco":     "faculty-business",
    "maths":        "dept-maths",
    "medicine":     "faculty-medicine",
    "electronics":  "dept-ete",
    "na1":          "na-hall",
    "wala_canteen": "wala-canteen",
    "material":     "dept-material",
    "chemical":     "dept-chemical",
    "mechanical":   "dept-mechanical",
    "registrar":    "registrar",
    "admin":        "admin",
    "intdesign":    "dept-design",
    "graduate":     "faculty-grad",
    "library":      "library",
}

# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------

class ZoneData(BaseModel):
    id: str
    name: str
    buildingId: str
    totalCapacity: int
    currentOccupancy: int
    energyKw: float
    occupancy: int            # capped 0-100 — UI gauge value
    occupancyTheoretical: int # raw (currentOccupancy/totalCapacity)*100, may exceed 100
    temperatureC: float
    anomalyCount: int
    status: str               # "normal" | "busy" | "critical"
    hasData: bool


class RoomData(BaseModel):
    room_id: str
    floor: int
    temperature: float
    occupancy: int
    energy: float


_ZONE_NAMES: dict[str, str] = {
    "lagaan":       "Lagaan",
    "conference":   "Multipurpose Hall",
    "hostel_a":     "Hostel A",
    "textile":      "Dept of Textile & Clothing",
    "transport":    "Dept of Transport & Logistics",
    "civil":        "Dept of Civil Engineering",
    "cse":          "Dept of Computer Science & Engineering",
    "Goda canteen": "Goda Canteen",
    "Sentra":       "Sentra Court",
    "canteen":      "L Canteen",
    "it":           "Faculty of Information Technology",
    "hostel":       "Hostel C",
    "buildeco":     "Faculty of Business Science",
    "maths":        "Dept of Maths",
    "medicine":     "Faculty of Medicine",
    "electronics":  "Dept of Electronics & Telecommunication Engineering",
    "na1":          "NA1&2",
    "wala_canteen": "Wala Canteen",
    "material":     "Dept of Material Science & Engineering",
    "chemical":     "Dept of Chemical & Process Engineering",
    "mechanical":   "Dept of Mechanical Engineering",
    "registrar":    "Registrar Office & Examination",
    "admin":        "Admin Building",
    "intdesign":    "Dept of Integrated Design",
    "graduate":     "Faculty of Graduate Studies",
    "library":      "Library",
}

_DEFAULT: dict[str, float] = {
    "temperature": 28.0,
    "occupancy":   0.0,
    "energy":      0.0,
}

_ANOMALY_CRITICAL_THRESHOLD = 3
_ANOMALY_BUSY_THRESHOLD     = 1


def _derive_status(total_occ: float, avg_temp: float, anomaly_count: int) -> str:
    if anomaly_count >= _ANOMALY_CRITICAL_THRESHOLD or total_occ > 300 or avg_temp > 34:
        return "critical"
    if anomaly_count >= _ANOMALY_BUSY_THRESHOLD or total_occ > 150 or avg_temp > 31:
        return "busy"
    return "normal"


# ---------------------------------------------------------------------------
# /campus/zones
# ---------------------------------------------------------------------------

@router.get(
    "/zones",
    response_model=list[ZoneData],
    summary="Live stats for all campus zones — no auth required",
)
async def campus_zones(
    influx: InfluxAPIClient = Depends(get_influx),
    postgres: PostgresClient = Depends(get_postgres),
    redis: RedisCache = Depends(get_redis),
) -> list[ZoneData]:
    """
    Raw per-room Flux query → aggregate per building → map to Zone[].
    Aggregation: avg occupancy %, sum(energy), mean(temperature).
    Falls back to safe defaults for any building with no recent data.
    Cached in Redis for 5 seconds to reduce load on InfluxDB/PostgreSQL.
    """
    # Try cache first
    cache_key = "campus:zones"
    cached = await redis.get(cache_key)
    if cached is not None:
        return [ZoneData(**z) for z in cached]
    try:
        df = await influx.all_buildings_latest(range_minutes=5)
    except Exception:
        df = None

    try:
        anom_df = await influx.all_buildings_anomaly_counts(range_minutes=5)
    except Exception:
        anom_df = None

    # ── aggregate per building ──────────────────────────────────────────────
    occ_lists:  dict[str, list[float]] = defaultdict(list)
    temp_lists: dict[str, list[float]] = defaultdict(list)
    nrg_lists:  dict[str, list[float]] = defaultdict(list)

    if df is not None and not df.empty:
        for _, row in df.iterrows():
            bld   = str(row.get("building_id", ""))
            stype = str(row.get("sensor_type", ""))
            val   = row.get("_value")
            if not bld or not stype or val is None:
                continue
            v = float(val)
            if stype == "temperature":
                temp_lists[bld].append(v)
            elif stype == "occupancy":
                occ_lists[bld].append(v)
            elif stype == "energy":
                nrg_lists[bld].append(v)

    anomaly_counts: dict[str, int] = {}
    if anom_df is not None and not anom_df.empty:
        for _, row in anom_df.iterrows():
            bld = str(row.get("building_id", ""))
            cnt = row.get("_value")
            if bld and cnt is not None:
                anomaly_counts[bld] = int(cnt)

    # ── get building capacities from PostgreSQL ────────────────────────────
    capacity_map: dict[str, int] = {}
    try:
        rows = await postgres.fetch(
            "SELECT building_id, SUM(capacity) as total_capacity FROM rooms GROUP BY building_id"
        )
        for row in rows:
            capacity_map[row["building_id"]] = int(row["total_capacity"])
    except Exception:
        pass  # If query fails, fall back to defaults

    # ── build zone list ─────────────────────────────────────────────────────
    zones: list[ZoneData] = []
    for zone_id, zone_name in _ZONE_NAMES.items():
        bld_id = _ZONE_TO_BUILDING[zone_id]

        temps = temp_lists.get(bld_id, [])
        occs  = occ_lists.get(bld_id,  [])
        nrgs  = nrg_lists.get(bld_id,  [])

        has_data = bool(temps or occs or nrgs)

        avg_temp  = round(sum(temps) / len(temps), 1) if temps else _DEFAULT["temperature"]
        total_occ_count = sum(occs) if occs else 0
        total_capacity = capacity_map.get(bld_id, 1)
        theoretical_pct = int(round((total_occ_count / total_capacity) * 100)) if total_capacity > 0 else 0
        # Cap the displayed percentage at 100 so a runaway sensor or anomaly
        # spike does not produce 300% in the UI; the raw value is kept under
        # occupancyTheoretical for diagnostics.
        occupancy_pct = min(100, max(0, theoretical_pct))

        total_nrg = sum(nrgs) if nrgs else _DEFAULT["energy"]
        energy_kw = round(total_nrg / 1000.0 if total_nrg > 500 else total_nrg, 1)
        anom_cnt  = anomaly_counts.get(bld_id, 0)

        zones.append(ZoneData(
            id=zone_id,
            name=zone_name,
            buildingId=bld_id,
            totalCapacity=max(0, total_capacity),
            currentOccupancy=max(0, int(round(total_occ_count))),
            temperatureC=avg_temp,
            occupancy=occupancy_pct,
            occupancyTheoretical=theoretical_pct,
            energyKw=energy_kw,
            anomalyCount=anom_cnt,
            status=_derive_status(occupancy_pct, avg_temp, anom_cnt),
            hasData=has_data,
        ))

    # Cache for 5 seconds
    await redis.set(cache_key, [z.model_dump() for z in zones], ttl_seconds=5)

    return zones


# ---------------------------------------------------------------------------
# /campus/buildings/{building_id}/rooms
# ---------------------------------------------------------------------------

class SensorHealth(BaseModel):
    sensor_id: str
    room_id: str
    building_id: str
    sensor_type: str
    last_seen_ms: int | None
    last_value: float | None
    seconds_since: int | None
    broken: bool       # no data within stale threshold
    anomalous: bool    # >=1 anomaly event in last 5 min


class AnomalyEntry(BaseModel):
    detected_at: str
    rule: str
    severity: str
    sensor_id: str
    room_id: str
    value: dict | float | int | str


_STALE_AFTER_S = 60   # sensor considered broken if no reading in 60s


@router.get(
    "/sensors/health",
    response_model=list[SensorHealth],
    summary="Per-sensor liveness + anomaly status — no auth required",
)
async def sensors_health(
    influx: InfluxAPIClient = Depends(get_influx),
    postgres: PostgresClient = Depends(get_postgres),
) -> list[SensorHealth]:
    try:
        df = await influx.sensors_last_seen(range_minutes=15)
    except Exception:
        df = None

    # Anomaly counts per sensor in the last 5 minutes from postgres.
    anomalies_by_sensor: dict[str, int] = defaultdict(int)
    try:
        rows = await postgres.fetch(
            "SELECT sensor_id, COUNT(*) AS c FROM anomaly_events "
            "WHERE detected_at > NOW() - INTERVAL '5 minutes' GROUP BY sensor_id"
        )
        for row in rows:
            anomalies_by_sensor[row["sensor_id"]] = int(row["c"])
    except Exception:
        pass

    import time
    now_ms = int(time.time() * 1000)
    out: list[SensorHealth] = []
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            sid = str(row.get("sensor_id", ""))
            if not sid:
                continue
            ts = row.get("_time")
            try:
                last_ms = int(ts.timestamp() * 1000) if ts is not None else None
            except Exception:
                last_ms = None
            seconds_since = int((now_ms - last_ms) / 1000) if last_ms else None
            broken = seconds_since is None or seconds_since > _STALE_AFTER_S
            out.append(SensorHealth(
                sensor_id=sid,
                room_id=str(row.get("room_id", "")),
                building_id=str(row.get("building_id", "")),
                sensor_type=str(row.get("sensor_type", "")),
                last_seen_ms=last_ms,
                last_value=float(row["_value"]) if row.get("_value") is not None else None,
                seconds_since=seconds_since,
                broken=broken,
                anomalous=anomalies_by_sensor.get(sid, 0) > 0,
            ))
    return out


@router.get(
    "/anomalies/recent",
    response_model=list[AnomalyEntry],
    summary="Most recent anomaly events — no auth required",
)
async def anomalies_recent(
    limit: int = 50,
    postgres: PostgresClient = Depends(get_postgres),
) -> list[AnomalyEntry]:
    limit = max(1, min(500, int(limit)))
    try:
        rows = await postgres.fetch(
            "SELECT detected_at, rule, severity, sensor_id, room_id, value "
            "FROM anomaly_events ORDER BY detected_at DESC LIMIT $1",
            limit,
        )
    except Exception:
        return []
    import json as _json
    out: list[AnomalyEntry] = []
    for r in rows:
        raw_val = r["value"]
        try:
            parsed = _json.loads(raw_val) if isinstance(raw_val, str) else raw_val
        except Exception:
            parsed = str(raw_val)
        out.append(AnomalyEntry(
            detected_at=str(r["detected_at"]),
            rule=str(r["rule"]),
            severity=str(r["severity"]),
            sensor_id=str(r["sensor_id"] or ""),
            room_id=str(r["room_id"] or ""),
            value=parsed,
        ))
    return out


@router.get(
    "/buildings/{building_id}/rooms",
    response_model=list[RoomData],
    summary="Live per-room sensor data for the indoor floor plan — no auth required",
)
async def building_rooms(
    building_id: str,
    influx: InfluxAPIClient = Depends(get_influx),
) -> list[RoomData]:
    """
    Returns the latest temperature, occupancy and energy for every room in the
    given building. Room IDs match the influxRoomId fields in the frontend
    FloorData.ts, enabling the floor plan to display real sensor values.
    """
    try:
        df = await influx.building_rooms_latest(building_id)
    except HTTPException:
        raise
    except Exception:
        return []

    if df is None or df.empty:
        return []

    # Build lookup: room_id → {floor, sensor_type: value}
    rooms: dict[str, dict] = {}
    for _, row in df.iterrows():
        rid   = str(row.get("room_id",    ""))
        stype = str(row.get("sensor_type",""))
        val   = row.get("_value")
        floor_raw = row.get("floor")
        if not rid or not stype or val is None:
            continue
        if rid not in rooms:
            try:
                floor_num = int(floor_raw) if floor_raw is not None else 0
            except (ValueError, TypeError):
                floor_num = 0
            rooms[rid] = {"floor": floor_num}
        rooms[rid][stype] = float(val)

    result: list[RoomData] = []
    for rid, data in rooms.items():
        result.append(RoomData(
            room_id=rid,
            floor=data.get("floor", 0),
            temperature=round(data.get("temperature", 28.0), 1),
            occupancy=max(0, int(round(data.get("occupancy", 0)))),
            energy=round(data.get("energy", 0.0), 1),
        ))

    return result
