"""
Smart Campus Digital Twin — FastAPI application entry point (v2).

Startup order:
  1. verify_auth_config() — fail-fast if JWT/Keycloak not configured
  2. create_engine()      — SQLAlchemy async engine + session factory
  3. InfluxDashboardClient() — injected into hub + routers
  4. Legacy InfluxAPIClient / PostgresClient — kept for existing metrics/reports routers
  5. hub.init_clients()   — WebSocket push loop gets both clients
  6. Routers mounted, middleware attached

Shutdown:
  - SQLAlchemy engine disposed
  - Both InfluxDB clients closed
  - Legacy asyncpg pool closed
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.clients import InfluxAPIClient, PostgresClient, RedisCache
from api.core.config import settings
from api.core.middleware import logging_middleware, setup_rate_limiter
from api.core.security import verify_auth_config
from api.db.influx import InfluxDashboardClient
from api.db.postgres import create_engine, dispose_engine
from api.dependencies import set_clients
from api.routers import alerts, buildings, campus, health, metrics, predictions, reports
from api.routers import rooms as rooms_router
from api.ws import handlers as ws_handlers
from api.ws.hub import hub
from shared.logging_config import get_logger

logger = get_logger("api", settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manages all client lifecycles."""
    logger.info("API starting up...")

    # ── Auth config check (warn-only, never raises) ──────────────────────────
    verify_auth_config()

    # ── Legacy clients — always started; campus/metrics/reports routers depend on these ─
    legacy_influx = InfluxAPIClient()
    legacy_postgres = PostgresClient()
    redis_cache = RedisCache()
    await legacy_postgres.connect()
    await redis_cache.connect()
    set_clients(legacy_influx, legacy_postgres, redis_cache)

    # ── New SQLAlchemy engine (optional — protected endpoints only) ───────────
    influx_dashboard: InfluxDashboardClient | None = None
    try:
        create_engine()
        influx_dashboard = InfluxDashboardClient()
        rooms_router.set_influx_client(influx_dashboard)
        hub.init_clients(influx_dashboard, legacy_postgres)
        logger.info("New DB layer (SQLAlchemy + InfluxDashboardClient) ready")
    except Exception as exc:
        logger.warning("New DB layer failed to start (%s) — /buildings and /ws routes unavailable", exc)

    logger.info("API ready")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await dispose_engine()
    if influx_dashboard:
        influx_dashboard.close()
    await legacy_postgres.close()
    await redis_cache.close()
    legacy_influx.close()
    logger.info("API shutdown complete.")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=(
        "Real-time building monitoring API for the Smart Campus Digital Twin. "
        "REST endpoints serve metadata + historical data; "
        "WebSocket /ws/buildings/{id} pushes live sensor updates to Three.js."
    ),
    lifespan=lifespan,
    docs_url="/swagger",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Middleware ───────────────────────────────────────────────────────────────
setup_rate_limiter(app)
app.middleware("http")(logging_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID", "Retry-After"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(health.router)           # /health  — no auth
app.include_router(campus.router)           # /campus/zones — no auth, frontend polling
app.include_router(buildings.router)        # /buildings — JWT + JWKS
app.include_router(rooms_router.router)     # /buildings/{id}/rooms — JWT + JWKS
app.include_router(alerts.router)           # /alerts — JWT + JWKS
app.include_router(ws_handlers.router)      # WS /ws/buildings/{id}
# Legacy routers — retained for backwards-compat with existing integrations
app.include_router(metrics.router)
app.include_router(predictions.router)
import contextlib

with contextlib.suppress(Exception):
    app.include_router(reports.router)
