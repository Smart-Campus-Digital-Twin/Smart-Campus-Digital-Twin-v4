from __future__ import annotations

from fastapi import APIRouter, Depends

from api.clients import InfluxAPIClient, PostgresClient
from api.config import config
from api.dependencies import get_influx, get_postgres
from api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health(
    influx:   InfluxAPIClient = Depends(get_influx),
    postgres: PostgresClient  = Depends(get_postgres),
) -> HealthResponse:
    try:
        await influx.ping()
        influx_status = "up"
    except Exception:  # noqa: BLE001 — any network failure marks influx down
        influx_status = "down"

    postgres_status = "up" if await postgres.health_check() else "down"

    overall = "ok" if influx_status == "up" and postgres_status == "up" else "degraded"

    return HealthResponse(
        status   = overall,
        influxdb = influx_status,
        postgres = postgres_status,
        version  = config.api_version,
    )
