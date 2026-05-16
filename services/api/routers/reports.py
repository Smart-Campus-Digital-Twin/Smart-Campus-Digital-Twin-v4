"""
Report endpoints — served from PostgreSQL (structured, joined, historical).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.clients import PostgresClient
from api.config import config
from api.dependencies import get_postgres
from api.schemas import EnergyDailyResponse, PagedResponse

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "/energy",
    response_model=PagedResponse,
    summary="Daily energy totals per building",
)
async def energy_daily(
    start:       str          = Query(...,  description="Start date YYYY-MM-DD"),
    end:         str          = Query(...,  description="End date YYYY-MM-DD"),
    building_id: str | None   = Query(default=None),
    limit:       int          = Query(default=config.default_page_size, ge=1, le=1000),
    offset:      int          = Query(default=0, ge=0),
    postgres:    PostgresClient = Depends(get_postgres),
) -> PagedResponse:
    rows = await postgres.get_energy_daily(
        building_id = building_id,
        start       = start,
        end         = end,
        limit       = limit,
        offset      = offset,
    )
    items = [EnergyDailyResponse(**dict(r)) for r in rows]
    return PagedResponse(total=len(items), offset=offset, limit=limit, items=items)
