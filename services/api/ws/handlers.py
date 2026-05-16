"""
WebSocket endpoint handlers.

Route:  WS /ws/buildings/{building_id}?token={jwt}

Handshake sequence:
  1. Validate JWT from query param (browsers cannot set WS headers).
  2. Assert building_id is in token.buildings → close(4001) if not.
  3. Check per-building connection cap → close(4008) if exceeded.
  4. Accept connection, register in hub.
  5. Receive loop: handle "pong" frames; ignore unknown types.
  6. On disconnect / error: deregister from hub.

Close codes used:
  4001  invalid / expired token or building not in claims
  4008  per-building connection cap exceeded
  1001  server-side stale connection eviction (no pong)
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from api.core.security import validate_ws_token
from api.ws.hub import hub

logger = logging.getLogger("api.ws.handlers")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/buildings/{building_id}")
async def ws_building(
    building_id: str,
    ws: WebSocket,
    token: str = Query(..., description="Bearer JWT — passed as query param (WS limitation)"),
) -> None:
    """
    Real-time WebSocket feed for a single building.

    Clients receive:
      - **room_update**        every 500 ms — per-room sensor snapshot with status and emissive colour
      - **building_summary**   every 5 s — aggregate temp, humidity, alert count
      - **alert**              immediately on new unresolved alert
      - **ping**               every 15 s — client must reply `{"type":"pong"}`

    Close codes:
      - 4001 — invalid / expired token, or building not in token.buildings
      - 4008 — per-building connection cap (50) exceeded
    """
    # ── 1. Validate token (before accept() to avoid wasted upgrade) ──────────
    try:
        claims = await validate_ws_token(token)
    except ValueError as exc:
        logger.info("WS rejected — bad token: %s", exc)
        await ws.close(code=4001, reason="Invalid or expired token")
        return

    # ── 2. Building access check ─────────────────────────────────────────────
    if not claims.can_access(building_id):
        logger.info("WS rejected — building %s not in claims for user %s", building_id, claims.sub)
        await ws.close(code=4001, reason="Building not in token claims")
        return

    # ── 3. Cap check + accept ────────────────────────────────────────────────
    try:
        await hub.connect(building_id, ws, claims.sub)
    except RuntimeError as exc:
        logger.warning("WS cap exceeded building=%s: %s", building_id, exc)
        await ws.close(code=4008, reason=str(exc))
        return

    # ── 4. Receive loop ───────────────────────────────────────────────────────
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            if msg_type == "pong":
                hub.mark_pong(building_id, ws)
            # unknown types silently ignored — forward-compatible
    except WebSocketDisconnect:
        logger.info("WS disconnect building=%s user=%s", building_id, claims.sub)
    except Exception as exc:
        logger.warning("WS error building=%s user=%s: %s", building_id, claims.sub, exc)
    finally:
        hub.disconnect(building_id, ws)
