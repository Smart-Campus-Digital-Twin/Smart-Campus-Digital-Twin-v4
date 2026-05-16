"""
WebSocket hub — ConnectionManager + per-building push loop.

Design:
  - One asyncio.Task per building (started on first connect, cancelled on last disconnect).
  - Task polls InfluxDB every WS_POLL_MS ms and broadcasts room_update to all connected clients.
  - Every WS_SUMMARY_INTERVAL_S seconds: broadcast building_summary.
  - Every WS_PING_INTERVAL_S seconds: send ping; drop clients that don't pong within WS_PONG_TIMEOUT_S.
  - Hard cap: WS_MAX_PER_BUILDING connections per building (close 4008 if exceeded).

Message types emitted:
  room_update       – per-room sensor snapshot, every poll tick
  building_summary  – aggregate stats, every 5 s
  alert             – forwarded when AlertRepo detects new unresolved alerts
  ping              – keepalive, every 15 s (client must respond with {"type":"pong"})
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from api.core.config import settings

logger = logging.getLogger("api.ws.hub")

# ---------------------------------------------------------------------------
# Sensor thresholds → status colour mapping (Three.js emissive)
# ---------------------------------------------------------------------------

_THRESHOLDS: dict[str, tuple[float, float]] = {
    "temperature": (26.0, 30.0),   # (warning, critical) °C
    "humidity":    (70.0, 85.0),   # %
    "co2":         (800.0, 1200.0),# ppm
    "occupancy":   (70.0, 90.0),   # % of capacity — normalised upstream
    "power_kw":    (10.0, 20.0),   # kW
    "lux":         (200.0, 50.0),  # lux (low light) — inverted scale
}

_EMISSIVE: dict[str, int] = {
    "ok":       0x00C875,
    "warning":  0xF5A623,
    "critical": 0xE84040,
    "unknown":  0x888888,
}


def _field_status(field_name: str, value: float) -> str:
    """Map a sensor value to ok / warning / critical."""
    thresholds = _THRESHOLDS.get(field_name)
    if thresholds is None:
        return "ok"
    warn, crit = thresholds
    if field_name == "lux":                  # inverted: low lux = bad
        if value < crit:
            return "critical"
        if value < warn:
            return "warning"
        return "ok"
    if value >= crit:
        return "critical"
    if value >= warn:
        return "warning"
    return "ok"


# ---------------------------------------------------------------------------
# Per-connection state
# ---------------------------------------------------------------------------

@dataclass
class _Conn:
    ws: WebSocket
    user_id: str
    last_pong: float = field(default_factory=time.monotonic)

    def alive(self) -> bool:
        return (time.monotonic() - self.last_pong) < settings.ws_pong_timeout_s


# ---------------------------------------------------------------------------
# ConnectionManager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """
    Tracks WebSocket connections grouped by building_id.

    Thread-safety: all methods called from the single asyncio event loop.
    """

    def __init__(self) -> None:
        self._conns: dict[str, set[_Conn]] = {}          # building_id → set[_Conn]
        self._tasks: dict[str, asyncio.Task[None]] = {}  # building_id → push task
        # Set by main.py after clients are initialised
        self._influx: Any = None
        self._postgres: Any = None

    def init_clients(self, influx: Any, postgres: Any) -> None:
        """Inject DB clients (called from lifespan after both are ready)."""
        self._influx = influx
        self._postgres = postgres

    # ── connection lifecycle ────────────────────────────────────────────────

    async def connect(self, building_id: str, ws: WebSocket, user_id: str) -> None:
        """
        Register a new WebSocket connection.

        Raises RuntimeError if the per-building cap is reached (caller closes 4008).
        """
        bucket = self._conns.setdefault(building_id, set())
        if len(bucket) >= settings.ws_max_per_building:
            raise RuntimeError(f"Max {settings.ws_max_per_building} connections reached")

        await ws.accept()
        conn = _Conn(ws=ws, user_id=user_id)
        bucket.add(conn)
        logger.info("WS connect  building=%s user=%s total=%d", building_id, user_id, len(bucket))

        if building_id not in self._tasks or self._tasks[building_id].done():
            self._tasks[building_id] = asyncio.create_task(
                self._push_loop(building_id),
                name=f"ws-push-{building_id}",
            )

    def disconnect(self, building_id: str, ws: WebSocket) -> None:
        """Remove a connection; cancel push task when bucket is empty."""
        bucket = self._conns.get(building_id, set())
        bucket = {c for c in bucket if c.ws is not ws}
        self._conns[building_id] = bucket
        logger.info("WS disconnect building=%s remaining=%d", building_id, len(bucket))

        if not bucket:
            task = self._tasks.pop(building_id, None)
            if task and not task.done():
                task.cancel()

    def mark_pong(self, building_id: str, ws: WebSocket) -> None:
        """Update last_pong timestamp for the given connection."""
        for conn in self._conns.get(building_id, set()):
            if conn.ws is ws:
                conn.last_pong = time.monotonic()
                return

    # ── broadcast helpers ───────────────────────────────────────────────────

    async def _send(self, conn: _Conn, payload: dict) -> bool:
        """Send JSON to one connection. Return False if it failed."""
        try:
            await conn.ws.send_json(payload)
            return True
        except Exception:
            return False

    async def _broadcast(self, building_id: str, payload: dict) -> None:
        """Fan-out payload to every live connection for a building."""
        dead: list[_Conn] = []
        for conn in list(self._conns.get(building_id, set())):
            if not await self._send(conn, payload):
                dead.append(conn)
        for conn in dead:
            self.disconnect(building_id, conn.ws)

    # ── room metadata cache ─────────────────────────────────────────────────

    async def _room_meta(self, building_id: str) -> dict[str, str]:
        """
        Return {room_id: threejs_node_id} map from Postgres (cached per push loop).

        Falls back to empty dict if Postgres is unavailable.
        """
        try:
            rows = await self._postgres.fetch(
                "SELECT id::text, threejs_node_id FROM rooms WHERE building_id = $1",
                building_id,
            )
            return {r["id"]: r["threejs_node_id"] for r in rows if r["threejs_node_id"]}
        except Exception as exc:
            logger.warning("room_meta query failed building=%s: %s", building_id, exc)
            return {}

    # ── push loop ───────────────────────────────────────────────────────────

    async def _push_loop(self, building_id: str) -> None:
        """
        Per-building task: polls InfluxDB and broadcasts to all connected clients.

        Lifecycle:
          - Started when first client connects.
          - Cancelled (via asyncio.CancelledError) when last client disconnects.
        """
        logger.info("Push loop started building=%s", building_id)
        poll_s = settings.ws_poll_ms / 1000.0
        ping_every = settings.ws_ping_interval_s
        summary_every = settings.ws_summary_interval_s

        last_ping = time.monotonic()
        last_summary = time.monotonic()
        room_meta: dict[str, str] = {}
        meta_refreshed_at: float = 0.0

        try:
            while True:
                await asyncio.sleep(poll_s)
                now = time.monotonic()
                conns = self._conns.get(building_id, set())
                if not conns:
                    break

                # ── refresh room metadata every 60 s ──────────────────────
                if now - meta_refreshed_at > 60:
                    room_meta = await self._room_meta(building_id)
                    meta_refreshed_at = now

                # ── query InfluxDB (one query for the whole building) ──────
                try:
                    df = await self._influx.latest_readings(building_id, range_minutes=1)
                except Exception as exc:
                    logger.warning("InfluxDB poll failed building=%s: %s", building_id, exc)
                    df = None

                if df is not None and not df.empty:
                    # Group rows by room_id and build room_update messages
                    for room_id, group in df.groupby("room_id"):
                        node_id = room_meta.get(str(room_id), str(room_id))
                        data: dict[str, dict] = {}
                        ts = None

                        for _, row in group.iterrows():
                            fld = str(row.get("sensor_type", ""))
                            val = row.get("value")
                            if val is None:
                                continue
                            val = float(val)
                            unit = _unit_for(fld)
                            status = _field_status(fld, val)
                            data[fld] = {
                                "value":   val,
                                "unit":    unit,
                                "status":  status,
                                "emissive": _EMISSIVE[status],
                            }
                            if ts is None:
                                ts = row.get("_time")

                        if data:
                            await self._broadcast(building_id, {
                                "type":           "room_update",
                                "building_id":    building_id,
                                "room_id":        str(room_id),
                                "threejs_node_id": node_id,
                                "ts":             str(ts) if ts is not None else None,
                                "data":           data,
                            })

                # ── building summary (every 5 s) ──────────────────────────
                if now - last_summary >= summary_every:
                    summary = await self._build_summary(building_id, df)
                    await self._broadcast(building_id, {
                        "type":        "building_summary",
                        "building_id": building_id,
                        **summary,
                    })
                    last_summary = now

                # ── ping + stale-connection pruning (every 15 s) ──────────
                if now - last_ping >= ping_every:
                    stale = [c for c in list(conns) if not c.alive()]
                    for conn in stale:
                        logger.info(
                            "Closing stale WS building=%s user=%s (no pong)",
                            building_id, conn.user_id,
                        )
                        with contextlib.suppress(Exception):
                            await conn.ws.close(code=1001)
                        self.disconnect(building_id, conn.ws)

                    await self._broadcast(building_id, {"type": "ping"})
                    last_ping = now

        except asyncio.CancelledError:
            logger.info("Push loop cancelled building=%s", building_id)
        except Exception as exc:
            logger.exception("Push loop crashed building=%s: %s", building_id, exc)

    async def _build_summary(self, building_id: str, df: Any) -> dict:
        """Compute a lightweight building-level summary from the latest readings df."""
        if df is None or df.empty:
            return {"avg_temp": None, "avg_humidity": None, "alert_count": 0, "room_count": 0}

        temps = df[df["sensor_type"] == "temperature"]["value"].dropna().astype(float)
        hums  = df[df["sensor_type"] == "humidity"]["value"].dropna().astype(float)

        alert_count = 0
        try:
            row = await self._postgres.fetchval(
                "SELECT COUNT(*) FROM alerts WHERE building_id=$1 AND resolved=false",
                building_id,
            )
            alert_count = int(row or 0)
        except Exception:
            pass

        return {
            "avg_temp":     round(float(temps.mean()), 2) if not temps.empty else None,
            "avg_humidity": round(float(hums.mean()),  2) if not hums.empty else None,
            "room_count":   int(df["room_id"].nunique()),
            "alert_count":  alert_count,
        }

    async def broadcast_alert(self, building_id: str, alert: dict) -> None:
        """Push an alert event to all clients subscribed to a building."""
        await self._broadcast(building_id, {"type": "alert", **alert})


def _unit_for(sensor_type: str) -> str:
    return {
        "temperature": "°C",
        "humidity":    "%",
        "co2":         "ppm",
        "occupancy":   "%",
        "power_kw":    "kW",
        "lux":         "lux",
    }.get(sensor_type, "")


# Module-level singleton — imported by main.py and handlers.py
hub = ConnectionManager()
