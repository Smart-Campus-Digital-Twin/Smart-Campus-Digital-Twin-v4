"""
Extended API configuration — adds JWT, rate-limit, and WebSocket settings
on top of the base APIConfig in api/config.py.

All values sourced from environment variables (or .env file).
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_KNOWN_BAD = frozenset({"changeme-secret", "secret", ""})


class Settings(BaseSettings):
    """Single source of truth for the entire API surface."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        env_file=".env",
    )

    # ── InfluxDB ────────────────────────────────────────────────────────────
    influxdb_url: str = Field("http://influxdb:8086", description="Internal Docker hostname")
    influxdb_token: str = Field("", description="Scoped read token — never admin token")
    influxdb_org: str = Field("smart-campus")
    influxdb_bucket_raw: str = Field("campus_raw")
    influxdb_bucket_1m: str = Field("campus_1m")
    influxdb_bucket_1h: str = Field("campus_1h")
    influxdb_slow_query_ms: int = Field(200, description="Log queries slower than this")

    # ── PostgreSQL (SQLAlchemy async URL) ───────────────────────────────────
    database_url: str = Field("", description="postgresql+asyncpg://user:pass@postgres/db")

    # ── JWT / Keycloak ───────────────────────────────────────────────────────
    # Production: set KEYCLOAK_JWKS_URL → RS256 verified against Keycloak public keys.
    # Local dev:  leave KEYCLOAK_JWKS_URL empty + set JWT_SECRET → HS256 fallback.
    keycloak_jwks_url: str = Field(
        "",
        description="e.g. http://keycloak:8080/realms/campus/protocol/openid-connect/certs",
    )
    keycloak_issuer: str = Field(
        "",
        description="Token iss claim — e.g. http://keycloak:8080/realms/campus",
    )
    keycloak_audience: str = Field(
        "campus-api",
        description="Expected aud claim value configured in the Keycloak client",
    )
    keycloak_buildings_claim: str = Field(
        "buildings",
        description="Custom JWT claim that carries the list of accessible building UUIDs",
    )
    jwks_cache_ttl_s: int = Field(300, description="Seconds to cache JWKS before re-fetching")

    jwt_secret: str = Field(
        "",
        description="HS256 secret — only used when KEYCLOAK_JWKS_URL is empty (dev only)",
    )
    jwt_algorithm: str = Field("HS256")
    jwt_ttl_minutes: int = Field(15, description="Access token lifetime in minutes")

    # ── Rate limiting ────────────────────────────────────────────────────────
    rate_limit_rest: str = Field("100/minute", description="REST limit per IP")
    rate_limit_ws: str = Field("10/minute", description="WS connect limit per IP")
    ws_max_per_building: int = Field(50, description="Hard cap on WS connections per building")
    ws_poll_ms: int = Field(500, description="InfluxDB poll interval for WS push")
    ws_ping_interval_s: int = Field(15, description="WS ping cadence (seconds)")
    ws_pong_timeout_s: int = Field(30, description="Close stale connection after this many seconds")
    ws_summary_interval_s: int = Field(5, description="BuildingSummary broadcast cadence")

    # ── Caches ───────────────────────────────────────────────────────────────
    latest_all_cache_ttl_ms: int = Field(500, description="TTL for /rooms/latest-all response")

    # ── API meta ─────────────────────────────────────────────────────────────
    api_title: str = "Smart Campus Digital Twin API"
    api_version: str = "2.0.0"
    cors_origins: list[str] = ["http://localhost:3001", "http://localhost:3002", "http://localhost:3000"]
    log_level: str = "INFO"
    default_page_size: int = Field(100, ge=1, le=1000)

    @field_validator("jwt_secret")
    @classmethod
    def _require_jwt_secret(cls, v: str) -> str:
        # Validated at runtime in security.py — empty is allowed when KEYCLOAK_JWKS_URL is set
        return v

    @field_validator("influxdb_token")
    @classmethod
    def _require_influx_token(cls, v: str) -> str:
        if v in _KNOWN_BAD:
            raise ValueError("INFLUXDB_TOKEN must be set")
        return v

    @field_validator("database_url")
    @classmethod
    def _require_database_url(cls, v: str) -> str:
        if v in _KNOWN_BAD:
            raise ValueError("DATABASE_URL must be set (env var DATABASE_URL)")
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


settings = Settings()
