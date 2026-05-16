"""
PostgreSQL async client for the API — uses asyncpg for non-blocking queries.

Connection pool is created once at startup (lifespan) and shared across requests.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from api.config import config


class PostgresClient:
    """Async PostgreSQL client backed by a connection pool."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            dsn      = config.database_url,
            min_size = 2,
            max_size = 10,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def fetch(self, sql: str, *args: Any) -> list[asyncpg.Record]:
        if self._pool is None:
            raise RuntimeError("PostgresClient not connected — call await connect() first")
        async with self._pool.acquire() as conn:
            return await conn.fetch(sql, *args)

    async def fetchrow(self, sql: str, *args: Any) -> asyncpg.Record | None:
        if self._pool is None:
            raise RuntimeError("PostgresClient not connected — call await connect() first")
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(sql, *args)

    async def fetchval(self, sql: str, *args: Any) -> Any:
        if self._pool is None:
            raise RuntimeError("PostgresClient not connected — call await connect() first")
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, *args)

    # ------------------------------------------------------------------
    # Domain queries
    # ------------------------------------------------------------------

    async def get_buildings(self) -> list[asyncpg.Record]:
        return await self.fetch(
            "SELECT id, name, lat, lon, floors, capacity FROM buildings ORDER BY id"
        )

    async def get_building(self, building_id: str) -> asyncpg.Record | None:
        return await self.fetchrow(
            "SELECT id, name, lat, lon, floors, capacity FROM buildings WHERE id = $1",
            building_id,
        )

    async def get_rooms(self, building_id: str) -> list[asyncpg.Record]:
        return await self.fetch(
            "SELECT id, building_id, floor, room_type, capacity "
            "FROM rooms WHERE building_id = $1 ORDER BY floor, id",
            building_id,
        )

    async def get_energy_daily(
        self,
        building_id: str | None,
        start: str,
        end: str,
        limit: int,
        offset: int,
    ) -> list[asyncpg.Record]:
        if building_id:
            return await self.fetch(
                "SELECT date::text, building_id, total_kwh, peak_w, avg_w, sample_hours "
                "FROM energy_daily "
                "WHERE building_id = $1 AND date BETWEEN $2 AND $3 "
                "ORDER BY date DESC, building_id "
                "LIMIT $4 OFFSET $5",
                building_id, start, end, limit, offset,
            )
        return await self.fetch(
            "SELECT date::text, building_id, total_kwh, peak_w, avg_w, sample_hours "
            "FROM energy_daily "
            "WHERE date BETWEEN $1 AND $2 "
            "ORDER BY date DESC, building_id "
            "LIMIT $3 OFFSET $4",
            start, end, limit, offset,
        )

    async def get_anomalies(
        self,
        building_id: str | None,
        severity: str | None,
        since: str,
        limit: int,
        offset: int,
    ) -> list[asyncpg.Record]:
        conditions = ["detected_at > $1::timestamptz"]
        params: list[Any] = [since]
        idx = 2

        if building_id:
            conditions.append(f"building_id = ${idx}")
            params.append(building_id)
            idx += 1
        if severity:
            conditions.append(f"severity = ${idx}")
            params.append(severity)
            idx += 1

        where = " AND ".join(conditions)
        params += [limit, offset]

        return await self.fetch(
            f"SELECT anomaly_id, detected_at, building_id, floor, room_id, "
            f"sensor_type, anomaly_type, severity, value, threshold, message "
            f"FROM anomalies WHERE {where} "
            f"ORDER BY detected_at DESC "
            f"LIMIT ${idx} OFFSET ${idx + 1}",
            *params,
        )

    async def health_check(self) -> bool:
        try:
            await self.fetchval("SELECT 1")
            return True
        except Exception:
            return False
