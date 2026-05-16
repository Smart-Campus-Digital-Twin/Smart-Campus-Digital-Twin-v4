"""
Room endpoints — metadata from PostgreSQL, readings from InfluxDB.

All endpoints require JWT. Building access verified against token.buildings claim.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.security import TokenClaims, assert_building_access, get_current_user
from api.db.influx import InfluxDashboardClient
from api.db.postgres import session_dep
from api.db.repos.room import RoomRepo
from api.models.schemas import FieldReading, SensorHistoryPoint, SensorReading
from api.ws.hub import _EMISSIVE, _field_status, _unit_for

router = APIRouter(prefix="/buildings/{building_id}/rooms", tags=["Rooms"])


def _df_to_reading(df, room_id: str, building_id: str, threejs_node_id: str | None) -> SensorReading:
    """Convert a latest-readings DataFrame row-group to a SensorReading."""
    data: dict[str, FieldReading] = {}
    ts = None
    for _, row in df.iterrows():
        fld = str(row.get("sensor_type", ""))
        val = row.get("_value")
        if val is None:
            continue
        val = float(val)
        st = _field_status(fld, val)
        data[fld] = FieldReading(
            value=val,
            unit=_unit_for(fld),
            status=st,
            emissive=_EMISSIVE[st],
        )
        if ts is None:
            ts = row.get("_time")

    return SensorReading(
        room_id=room_id,
        building_id=building_id,
        threejs_node_id=threejs_node_id,
        ts=ts,
        data=data,
    )


# ── simple in-process TTL cache for /latest-all ────────────────────────────
_latest_all_cache: dict[str, tuple[float, dict]] = {}


@router.get(
    "",
    summary="List rooms in a building",
    description="Returns room metadata including the `threejs_node_id` for scene lookup.",
    tags=["Rooms"],
)
async def list_rooms(
    building_id: uuid.UUID,
    claims: TokenClaims = Depends(get_current_user),
    session: AsyncSession = Depends(session_dep),
):
    assert_building_access(claims, building_id)
    repo = RoomRepo(session)
    rooms = await repo.list_for_building(building_id)
    if not rooms:
        # Verify building exists
        from api.db.repos.building import BuildingRepo
        if not await BuildingRepo(session).get(building_id):
            raise HTTPException(status_code=404, detail="Building not found")
    from api.models.schemas import RoomOut
    return [RoomOut.model_validate(r) for r in rooms]


@router.get(
    "/latest-all",
    response_model=dict[str, SensorReading],
    summary="Latest readings for all rooms in a building",
    description=(
        "Single InfluxDB query for the whole building. "
        "Response keyed by `threejs_node_id` (falls back to `room_id` if unset). "
        "Cached for 500 ms."
    ),
    tags=["Rooms"],
)
async def latest_all(
    building_id: uuid.UUID,
    claims: TokenClaims = Depends(get_current_user),
    session: AsyncSession = Depends(session_dep),
    influx: InfluxDashboardClient = Depends(lambda: _get_influx()),
) -> dict[str, SensorReading]:
    assert_building_access(claims, building_id)
    bid = str(building_id)

    # TTL cache — avoids hammering InfluxDB on burst requests
    from api.core.config import settings
    cached = _latest_all_cache.get(bid)
    if cached and (time.monotonic() - cached[0]) * 1000 < settings.latest_all_cache_ttl_ms:
        return cached[1]

    node_map = await RoomRepo(session).node_id_map(building_id)
    df = await influx.latest_for_building(bid)

    result: dict[str, SensorReading] = {}
    if not df.empty:
        for room_id, grp in df.groupby("room_id"):
            node_id = node_map.get(str(room_id), str(room_id))
            result[node_id] = _df_to_reading(grp, str(room_id), bid, node_id)

    _latest_all_cache[bid] = (time.monotonic(), result)
    return result


@router.get(
    "/{room_id}/latest",
    response_model=SensorReading,
    summary="Latest reading for a single room",
    tags=["Rooms"],
)
async def latest_room(
    building_id: uuid.UUID,
    room_id: uuid.UUID,
    claims: TokenClaims = Depends(get_current_user),
    session: AsyncSession = Depends(session_dep),
    influx: InfluxDashboardClient = Depends(lambda: _get_influx()),
) -> SensorReading:
    assert_building_access(claims, building_id)
    room = await RoomRepo(session).get(room_id)
    if not room or room.building_id != building_id:
        raise HTTPException(status_code=404, detail="Room not found")

    df = await influx.latest_for_room(str(building_id), str(room_id))
    if df.empty:
        return SensorReading(
            room_id=str(room_id),
            building_id=str(building_id),
            threejs_node_id=room.threejs_node_id,
            ts=None,
            data={},
        )
    return _df_to_reading(df, str(room_id), str(building_id), room.threejs_node_id)


@router.get(
    "/{room_id}/history",
    response_model=list[SensorHistoryPoint],
    summary="Historical time-series for a room field",
    description="Downsampled aggregate. `window`: 5m|15m|1h|6h|24h|7d. `field`: temperature|humidity|co2|occupancy|power_kw|lux",
    tags=["Rooms"],
)
async def room_history(
    building_id: uuid.UUID,
    room_id: uuid.UUID,
    field: str = Query(..., description="Sensor field name"),
    window: str = Query("1h", description="Time window: 5m|15m|1h|6h|24h|7d"),
    claims: TokenClaims = Depends(get_current_user),
    session: AsyncSession = Depends(session_dep),
    influx: InfluxDashboardClient = Depends(lambda: _get_influx()),
) -> list[SensorHistoryPoint]:
    assert_building_access(claims, building_id)
    room = await RoomRepo(session).get(room_id)
    if not room or room.building_id != building_id:
        raise HTTPException(status_code=404, detail="Room not found")

    df = await influx.room_history(str(building_id), str(room_id), field, window)
    if df.empty:
        return []

    points = []
    for _, row in df.iterrows():
        points.append(SensorHistoryPoint(
            ts=row["_time"],
            room_id=str(room_id),
            building_id=str(building_id),
            sensor_type=field,
            avg=float(row.get("_value", 0)),
        ))
    return points


# ---------------------------------------------------------------------------
# Module-level client accessor (set by main.py)
# ---------------------------------------------------------------------------
_influx_client: InfluxDashboardClient | None = None


def set_influx_client(client: InfluxDashboardClient) -> None:
    global _influx_client
    _influx_client = client


def _get_influx() -> InfluxDashboardClient:
    if _influx_client is None:
        raise RuntimeError("InfluxDashboardClient not initialised")
    return _influx_client
