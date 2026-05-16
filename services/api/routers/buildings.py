"""
Building endpoints — metadata from PostgreSQL, summary aggregates from InfluxDB.
All endpoints require JWT. Building access verified against token.buildings claim.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.security import TokenClaims, assert_building_access, get_current_user
from api.db.postgres import session_dep
from api.db.repos.building import BuildingRepo
from api.models.schemas import BuildingOut, BuildingSummary, BuildingWithRoomsOut, RoomOut

router = APIRouter(prefix="/buildings", tags=["Buildings"])


@router.get(
    "",
    response_model=list[BuildingOut],
    summary="List all buildings accessible to the caller",
    description="Returns only the buildings present in the JWT `buildings` claim.",
)
async def list_buildings(
    claims: TokenClaims = Depends(get_current_user),
    session: AsyncSession = Depends(session_dep),
) -> list[BuildingOut]:
    repo = BuildingRepo(session)
    all_buildings = await repo.list_all()
    accessible = [b for b in all_buildings if claims.can_access(b.id)]
    return [BuildingOut.model_validate(b) for b in accessible]


@router.get(
    "/{building_id}",
    response_model=BuildingWithRoomsOut,
    summary="Get building with its rooms",
)
async def get_building(
    building_id: uuid.UUID,
    claims: TokenClaims = Depends(get_current_user),
    session: AsyncSession = Depends(session_dep),
) -> BuildingWithRoomsOut:
    assert_building_access(claims, building_id)
    repo = BuildingRepo(session)
    building = await repo.get_with_rooms(building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")
    return BuildingWithRoomsOut(
        **BuildingOut.model_validate(building).model_dump(),
        rooms=[RoomOut.model_validate(r) for r in building.rooms],
    )


@router.get(
    "/{building_id}/summary",
    response_model=BuildingSummary,
    summary="Aggregate building stats — avg temp/humidity, alert count, per-floor breakdown",
)
async def building_summary(
    building_id: uuid.UUID,
    claims: TokenClaims = Depends(get_current_user),
    session: AsyncSession = Depends(session_dep),
) -> BuildingSummary:
    assert_building_access(claims, building_id)
    from api.db.repos.alert import AlertRepo
    from api.models.schemas import FloorSummary
    from api.routers.rooms import _get_influx

    repo = BuildingRepo(session)
    building = await repo.get_with_rooms(building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    influx = _get_influx()
    df = await influx.latest_for_building(str(building_id))

    alerts_repo = AlertRepo(session)
    alerts, alert_total = await alerts_repo.list_alerts(building_id, resolved=False, offset=0, limit=1000)

    avg_temp = avg_hum = avg_occ = total_kw = None
    floor_data: dict[int, dict] = {}

    if not df.empty:
        def _avg(field: str):
            s = df[df["sensor_type"] == field]["_value"].dropna().astype(float)
            return round(float(s.mean()), 2) if not s.empty else None

        avg_temp = _avg("temperature")
        avg_hum  = _avg("humidity")
        avg_occ  = _avg("occupancy")
        kw_s = df[df["sensor_type"] == "power_kw"]["_value"].dropna().astype(float)
        total_kw = round(float(kw_s.sum()), 2) if not kw_s.empty else None

        for floor_num, grp in df.groupby("floor"):
            fl = int(floor_num)
            t = grp[grp["sensor_type"] == "temperature"]["_value"].dropna().astype(float)
            h = grp[grp["sensor_type"] == "humidity"]["_value"].dropna().astype(float)
            floor_data[fl] = {
                "avg_temp":     round(float(t.mean()), 2) if not t.empty else None,
                "avg_humidity": round(float(h.mean()), 2) if not h.empty else None,
                "room_count":   int(grp["room_id"].nunique()),
                "alert_count":  0,
            }

    for a in alerts:
        room = await session.get(type(building.rooms[0]), a.room_id) if building.rooms else None
        if room and int(getattr(room, "floor", 0)) in floor_data:
            floor_data[int(room.floor)]["alert_count"] += 1

    return BuildingSummary(
        building_id=building_id,
        avg_temp=avg_temp,
        avg_humidity=avg_hum,
        avg_occupancy=avg_occ,
        total_power_kw=total_kw,
        alert_count=alert_total,
        room_count=len(building.rooms),
        floor_summaries=[
            FloorSummary(floor=fl, **data)
            for fl, data in sorted(floor_data.items())
        ],
    )
