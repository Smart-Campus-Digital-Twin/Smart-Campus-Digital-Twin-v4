"""
InfluxDB async query layer for the dashboard data pipeline.

Measurement:  sensor_data
Tags:         building_id, room_id, floor, sensor_type
Fields:       temperature (float), humidity (float), co2 (int),
              occupancy (float — % of capacity), power_kw (float), lux (float)

All tag values are validated with _validate_tag() before interpolation
to prevent Flux query injection from user-supplied path/query params.

Slow queries (>INFLUXDB_SLOW_QUERY_MS) are logged at WARNING level.
InfluxDB errors raise HTTP 503 with Retry-After: 5.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import UTC, datetime
from functools import partial

import pandas as pd
from fastapi import HTTPException, status
from influxdb_client import InfluxDBClient
from influxdb_client.client.exceptions import InfluxDBError

from api.core.config import settings

logger = logging.getLogger("api.db.influx")

_TAG_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}\Z")

_ALLOWED_FIELDS = frozenset({"temperature", "humidity", "co2", "occupancy", "power_kw", "lux"})
_ALLOWED_WINDOWS = frozenset({"5m", "15m", "1h", "6h", "24h", "7d"})


def _validate_tag(value: str, name: str) -> str:
    if not _TAG_RE.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {name}: must match [A-Za-z0-9_-]{{1,64}}",
        )
    return value


def _validate_field(field: str) -> str:
    if field not in _ALLOWED_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"field must be one of {sorted(_ALLOWED_FIELDS)}",
        )
    return field


def _validate_window(window: str) -> str:
    if window not in _ALLOWED_WINDOWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"window must be one of {sorted(_ALLOWED_WINDOWS)}",
        )
    return window


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class InfluxDashboardClient:
    """Async-safe InfluxDB client — wraps sync client in executor."""

    def __init__(self) -> None:
        self._client = InfluxDBClient(
            url=settings.influxdb_url,
            token=settings.influxdb_token,
            org=settings.influxdb_org,
        )
        self._qapi = self._client.query_api()

    def close(self) -> None:
        self._client.close()

    async def ping(self) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._client.ping)

    async def _query(self, flux: str, label: str = "") -> pd.DataFrame:
        """Run a Flux query off-thread; log and raise HTTP 503 on failure."""
        loop = asyncio.get_running_loop()
        t0 = time.monotonic()
        try:
            fn = partial(self._qapi.query_data_frame, flux)
            df = await loop.run_in_executor(None, fn)
        except InfluxDBError as exc:
            logger.error("InfluxDB error [%s]: %s", label, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Time-series database unavailable",
                headers={"Retry-After": "5"},
            ) from exc
        elapsed = (time.monotonic() - t0) * 1000
        if elapsed > settings.influxdb_slow_query_ms:
            logger.warning("Slow InfluxDB query [%s] %.0f ms", label, elapsed)
        if isinstance(df, list):
            df = pd.concat(df, ignore_index=True) if df else pd.DataFrame()
        return df

    # ── Public query methods ────────────────────────────────────────────────

    async def latest_for_building(self, building_id: str, range_minutes: int = 1) -> pd.DataFrame:
        """
        One query, all rooms in a building — latest value per sensor_type per room.

        Returns DataFrame with columns:
          building_id, room_id, floor, sensor_type, _value, _time
        """
        _validate_tag(building_id, "building_id")
        flux = f"""
from(bucket: "{settings.influxdb_bucket_raw}")
  |> range(start: -{range_minutes}m)
  |> filter(fn: (r) => r._measurement =~ /^sensor_[a-z]/)
  |> filter(fn: (r) => r.building_id == "{building_id}")
  |> filter(fn: (r) => r._field == "value")
  |> last()
  |> keep(columns: ["_time", "_field", "_value", "building_id", "room_id", "floor", "sensor_type"])
"""
        return await self._query(flux, label=f"latest_building:{building_id}")

    async def latest_for_room(self, building_id: str, room_id: str) -> pd.DataFrame:
        """Latest reading per field for a single room."""
        _validate_tag(building_id, "building_id")
        _validate_tag(room_id, "room_id")
        flux = f"""
from(bucket: "{settings.influxdb_bucket_raw}")
  |> range(start: -1m)
  |> filter(fn: (r) => r._measurement =~ /^sensor_[a-z]/)
  |> filter(fn: (r) => r.building_id == "{building_id}")
  |> filter(fn: (r) => r.room_id == "{room_id}")
  |> filter(fn: (r) => r._field == "value")
  |> last()
  |> keep(columns: ["_time", "_field", "_value", "building_id", "room_id", "floor", "sensor_type"])
"""
        return await self._query(flux, label=f"latest_room:{room_id}")

    async def room_history(
        self,
        building_id: str,
        room_id: str,
        field: str,
        window: str = "1h",
    ) -> pd.DataFrame:
        """
        Downsampled history for one room + field.

        window: 5m | 15m | 1h | 6h | 24h | 7d
        field:  temperature | humidity | co2 | occupancy | power_kw | lux
        """
        _validate_tag(building_id, "building_id")
        _validate_tag(room_id, "room_id")
        _validate_field(field)
        _validate_window(window)

        # Choose bucket — raw for short windows, 1m/1h for longer
        bucket = settings.influxdb_bucket_raw
        if window in ("6h", "24h", "7d"):
            bucket = settings.influxdb_bucket_1h

        flux = f"""
from(bucket: "{bucket}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "sensor_data")
  |> filter(fn: (r) => r.building_id == "{building_id}")
  |> filter(fn: (r) => r.room_id == "{room_id}")
  |> filter(fn: (r) => r.sensor_type == "{field}")
  |> aggregateWindow(every: {_agg_every(window)}, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value", "room_id", "building_id", "sensor_type"])
  |> sort(columns: ["_time"])
"""
        return await self._query(flux, label=f"history:{room_id}:{field}:{window}")


def _agg_every(window: str) -> str:
    return {
        "5m": "30s", "15m": "1m", "1h": "5m",
        "6h": "30m", "24h": "1h", "7d": "6h",
    }.get(window, "5m")
