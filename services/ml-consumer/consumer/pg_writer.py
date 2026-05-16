"""
Postgres writer for anomaly events.

Creates the anomaly_events table if it doesn't exist, then
persists anomaly dicts from the AnomalyDetector.
"""

from __future__ import annotations

import json
import logging
import os

import asyncpg

logger = logging.getLogger("ml-consumer.pg")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://campus:campus@postgres:5432/campus",
)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS anomaly_events (
    id              BIGSERIAL PRIMARY KEY,
    rule            TEXT NOT NULL,
    topic           TEXT NOT NULL,
    room_id         TEXT NOT NULL,
    sensor_id       TEXT,
    value           JSONB,
    severity        TEXT NOT NULL DEFAULT 'warning',
    detected_at     TIMESTAMPTZ NOT NULL,
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anomaly_room_id    ON anomaly_events (room_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_detected   ON anomaly_events (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_severity   ON anomaly_events (severity);
"""

INSERT_SQL = """
INSERT INTO anomaly_events
    (rule, topic, room_id, sensor_id, value, severity, detected_at, raw_payload)
VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8::jsonb)
"""


class PgWriter:
    """Async Postgres writer using asyncpg."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        """Connect and create table schema."""
        import asyncio

        for attempt in range(10):
            try:
                self._pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
                async with self._pool.acquire() as conn:
                    await conn.execute(CREATE_TABLE_SQL)
                logger.info("Postgres pool ready, anomaly_events table ensured.")
                return
            except Exception as exc:
                logger.warning(f"Postgres not ready (attempt {attempt + 1}/10): {exc}")
                await asyncio.sleep(5)
        raise RuntimeError("Failed to connect to Postgres after 10 attempts.")

    async def write_anomaly(self, anomaly: dict) -> None:
        """Insert one anomaly event."""
        if self._pool is None:
            raise RuntimeError("PgWriter not initialized — call init() first.")

        from datetime import datetime
        detected_at = anomaly.get("detected_at")
        if isinstance(detected_at, str):
            detected_at = datetime.fromisoformat(detected_at)

        async with self._pool.acquire() as conn:
            await conn.execute(
                INSERT_SQL,
                anomaly["rule"],
                anomaly["topic"],
                str(anomaly.get("room_id", "unknown")),
                str(anomaly.get("sensor_id", "unknown")),
                json.dumps(anomaly.get("value")),
                anomaly.get("severity", "warning"),
                detected_at,
                json.dumps(anomaly.get("raw_payload", {})),
            )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            logger.info("Postgres pool closed.")
