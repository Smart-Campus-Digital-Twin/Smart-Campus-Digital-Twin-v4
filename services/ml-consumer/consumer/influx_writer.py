"""
InfluxDB writer for the ML consumer.

Converts Kafka sensor payloads to InfluxDB line protocol points
and writes them asynchronously using the official influxdb-client-python.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from influxdb_client import Point
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write_api_async import WriteApiAsync
from influxdb_client.domain.write_precision import WritePrecision

logger = logging.getLogger("ml-consumer.influx")

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "smart-campus")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "campus_sensors")


class InfluxWriter:
    """Async InfluxDB writer — one shared client for the process."""

    def __init__(self) -> None:
        self._client: InfluxDBClientAsync | None = None
        self._write_api: WriteApiAsync | None = None

    async def _ensure_connected(self) -> None:
        if self._client is None:
            self._client = InfluxDBClientAsync(
                url=INFLUXDB_URL,
                token=INFLUXDB_TOKEN,
                org=INFLUXDB_ORG,
            )
            self._write_api = self._client.write_api()
            logger.info("Connected to InfluxDB", extra={"url": INFLUXDB_URL})

    def _build_point(self, topic: str, payload: dict) -> Point | None:
        sensor_type = str(payload.get("sensor_type") or topic.split(".")[-1])
        measurement = f"sensor_{sensor_type}"
        room_id = str(payload.get("room_id", "unknown"))
        sensor_id = str(payload.get("sensor_id", "unknown"))
        building_id = str(payload.get("building_id") or payload.get("building") or "unknown")

        # Build Point based on measurement type
        point = (
            Point(measurement)
            .tag("sensor_type", sensor_type)
            .tag("room_id", room_id)
            .tag("sensor_id", sensor_id)
            .tag("building_id", building_id)
            .tag("floor", str(payload.get("floor", "unknown")))
            .tag("behavior_mode", str(payload.get("behavior_mode", "normal")))
            .tag("unit", str(payload.get("unit", "")))
        )

        if sensor_type == "temperature":
            val = payload.get("value") or payload.get("temperature")
            if val is not None:
                point = point.field("value", float(val))
                point = point.field("celsius", float(val))
            humidity = payload.get("humidity")
            if humidity is not None:
                point = point.field("humidity", float(humidity))

        elif sensor_type == "occupancy":
            val = payload.get("value") or payload.get("occupancy") or payload.get("count")
            if val is not None:
                point = point.field("value", float(val))
                point = point.field("count", int(val))

        elif sensor_type == "energy":
            val = payload.get("value") or payload.get("energy") or payload.get("kwh")
            if val is not None:
                point = point.field("value", float(val))
                point = point.field("kwh", float(val))
            power = payload.get("power_kw")
            if power is not None:
                point = point.field("power_kw", float(power))

        else:
            # Unknown measurement — store raw value field
            val = payload.get("value")
            if val is not None:
                point = point.field("value", float(val))

        quality = payload.get("quality")
        if quality is not None:
            point = point.field("quality", float(quality))

        # Timestamp from payload or now. Convert to nanoseconds so the write
        # call's precision matches the Point's stored time and InfluxDB does
        # not mis-interpret a millisecond value as nanoseconds (epoch 1970).
        ts = payload.get("timestamp_ms") or payload.get("timestamp") or payload.get("ts")
        if ts:
            try:
                if isinstance(ts, (int, float)):
                    point = point.time(int(ts) * 1_000_000, WritePrecision.NS)
                else:
                    dt = datetime.fromisoformat(str(ts))
                    point = point.time(dt, WritePrecision.NS)
            except (ValueError, TypeError):
                pass  # Use server time

        return point

    async def write(self, topic: str, payload: dict) -> None:
        await self._ensure_connected()
        point = self._build_point(topic, payload)
        if point is None:
            return
        try:
            await self._write_api.write(
                bucket=INFLUXDB_BUCKET,
                org=INFLUXDB_ORG,
                record=point,
                precision=WritePrecision.NS,
            )
        except Exception as exc:
            logger.error("InfluxDB write failed", extra={"error": str(exc)}, exc_info=True)
            raise

    async def write_batch(self, items: list[tuple[str, dict]]) -> None:
        """Write many readings in one HTTP request."""
        if not items:
            return
        await self._ensure_connected()
        points = [p for p in (self._build_point(t, pl) for t, pl in items) if p is not None]
        if not points:
            return
        try:
            await self._write_api.write(
                bucket=INFLUXDB_BUCKET,
                org=INFLUXDB_ORG,
                record=points,
                precision=WritePrecision.NS,
            )
        except Exception as exc:
            logger.error("InfluxDB batch write failed", extra={"count": len(points), "error": str(exc)}, exc_info=True)
            raise

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("InfluxDB connection closed.")
