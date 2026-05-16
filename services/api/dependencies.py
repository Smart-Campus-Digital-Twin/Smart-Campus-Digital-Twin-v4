"""
FastAPI dependency injection — database clients as request-scoped dependencies.

Both clients are created once at startup (via lifespan) and injected per-request
via FastAPI's Depends() mechanism.  This means:
  - One asyncpg connection pool shared across all requests (efficient)
  - One InfluxDB client reused across all requests (HTTP keep-alive)
  - Both clients are closed cleanly on shutdown
"""

from __future__ import annotations

from api.clients import InfluxAPIClient, PostgresClient, RedisCache

# Module-level singletons — initialised in api/main.py lifespan handler
_influx:   InfluxAPIClient | None = None
_postgres: PostgresClient  | None = None
_redis:    RedisCache      | None = None


def set_clients(influx: InfluxAPIClient, postgres: PostgresClient, redis: RedisCache) -> None:
    global _influx, _postgres, _redis
    _influx   = influx
    _postgres = postgres
    _redis    = redis


def get_influx() -> InfluxAPIClient:
    assert _influx is not None, "InfluxDB client not initialised"
    return _influx


def get_postgres() -> PostgresClient:
    assert _postgres is not None, "PostgreSQL client not initialised"
    return _postgres


def get_redis() -> RedisCache:
    assert _redis is not None, "Redis cache not initialised"
    return _redis
