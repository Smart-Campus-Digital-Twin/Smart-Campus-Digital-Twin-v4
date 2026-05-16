"""Alert endpoints — PostgreSQL alerts table via AlertRepo. JWT required."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.security import TokenClaims, assert_building_access, get_current_user
from api.db.postgres import session_dep
from api.db.repos.alert import AlertRepo
from api.models.schemas import AlertOut, PagedAlerts, PageMeta

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _to_out(alert) -> AlertOut:
    node_id = getattr(alert.room, "threejs_node_id", None) if alert.room else None
    return AlertOut(
        id=alert.id,
        room_id=alert.room_id,
        building_id=alert.building_id,
        severity=alert.severity,
        message=alert.message,
        resolved=alert.resolved,
        created_at=alert.created_at,
        resolved_at=alert.resolved_at,
        threejs_node_id=node_id,
    )


@router.get(
    "",
    response_model=PagedAlerts,
    summary="List alerts with optional building and resolution filters",
    description="Paginated. `building_id` must be in token.buildings if supplied.",
)
async def list_alerts(
    building_id: uuid.UUID | None = Query(None),
    resolved: bool | None = Query(None, description="True=resolved, False=open, omit=all"),
    severity: str | None = Query(None, pattern="^(info|warning|critical)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    claims: TokenClaims = Depends(get_current_user),
    session: AsyncSession = Depends(session_dep),
) -> PagedAlerts:
    if building_id is not None:
        assert_building_access(claims, building_id)

    repo = AlertRepo(session)
    items, total = await repo.list_alerts(building_id, resolved, offset, limit)
    return PagedAlerts(
        meta=PageMeta(total=total, offset=offset, limit=limit),
        items=[_to_out(a) for a in items],
    )


@router.post(
    "/{alert_id}/resolve",
    response_model=AlertOut,
    summary="Mark an alert as resolved",
    status_code=200,
)
async def resolve_alert(
    alert_id: uuid.UUID,
    claims: TokenClaims = Depends(get_current_user),
    session: AsyncSession = Depends(session_dep),
) -> AlertOut:
    repo = AlertRepo(session)
    alert = await repo.get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    assert_building_access(claims, alert.building_id)

    updated = await repo.resolve(alert_id)
    if not updated:
        raise HTTPException(status_code=409, detail="Alert already resolved")
    return _to_out(updated)
