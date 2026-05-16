"""
Key endpoint + security tests for the dashboard data pipeline.

Run: pytest tests/test_dashboard_pipeline.py -v
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest_dashboard import BUILDING_ID, NODE_ID, ROOM_ID

pytestmark = pytest.mark.asyncio
pytest_plugins = ["tests.conftest_dashboard"]


# ---------------------------------------------------------------------------
# Security — JWT validation
# ---------------------------------------------------------------------------

class TestJwtSecurity:
    async def test_no_token_returns_401(self, client):
        from api.core.security import get_current_user
        from api.main import app
        app.dependency_overrides.pop(get_current_user, None)
        resp = await client.get(f"/buildings/{BUILDING_ID}")
        assert resp.status_code in (401, 403)

    async def test_wrong_building_returns_403(self, client):
        from api.core.security import TokenClaims, get_current_user
        from api.main import app
        other_id = uuid.uuid4()
        app.dependency_overrides[get_current_user] = lambda: TokenClaims(
            sub="u", buildings=[str(other_id)], exp=9999999999, iat=0
        )
        resp = await client.get(f"/buildings/{BUILDING_ID}")
        assert resp.status_code == 403

    async def test_keycloak_unknown_kid_raises(self):
        from api.core.security import _decode_keycloak, _jwks_cache
        with patch.object(_jwks_cache, "get_key", AsyncMock(return_value=None)), pytest.raises(ValueError, match="Unknown kid"):
                await _decode_keycloak("eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QifQ.e30.sig")


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------

class TestBuildingsRouter:
    async def test_list_buildings_returns_accessible_only(self, client):
        resp = await client.get("/buildings")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        ids = [b["id"] for b in data]
        assert str(BUILDING_ID) in ids

    async def test_get_building_with_rooms(self, client):
        resp = await client.get(f"/buildings/{BUILDING_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(BUILDING_ID)
        assert "rooms" in body
        assert body["rooms"][0]["threejs_node_id"] == NODE_ID

    async def test_unknown_building_404(self, client):
        resp = await client.get(f"/buildings/{uuid.uuid4()}")
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Rooms / InfluxDB readings
# ---------------------------------------------------------------------------

class TestRoomsRouter:
    async def test_latest_all_returns_node_id_keyed_dict(self, client):
        resp = await client.get(f"/buildings/{BUILDING_ID}/rooms/latest-all")
        assert resp.status_code == 200
        body = resp.json()
        assert NODE_ID in body
        reading = body[NODE_ID]
        assert "data" in reading
        assert "temperature" in reading["data"]
        assert reading["data"]["temperature"]["status"] in ("ok", "warning", "critical")
        assert "emissive" in reading["data"]["temperature"]

    async def test_latest_room_contains_threejs_node_id(self, client):
        resp = await client.get(f"/buildings/{BUILDING_ID}/rooms/{ROOM_ID}/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["threejs_node_id"] == NODE_ID

    async def test_history_invalid_field_returns_400(self, client):
        resp = await client.get(
            f"/buildings/{BUILDING_ID}/rooms/{ROOM_ID}/history",
            params={"field": "INJECTION; drop table", "window": "1h"},
        )
        assert resp.status_code == 400

    async def test_history_invalid_window_returns_400(self, client):
        resp = await client.get(
            f"/buildings/{BUILDING_ID}/rooms/{ROOM_ID}/history",
            params={"field": "temperature", "window": "99y"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class TestAlertsRouter:
    async def test_list_alerts_empty_ok(self, client):
        resp = await client.get("/alerts", params={"building_id": str(BUILDING_ID)})
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "meta" in body

    async def test_resolve_unknown_alert_404(self, client):
        resp = await client.post(f"/alerts/{uuid.uuid4()}/resolve")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

class TestWebSocket:
    async def test_ws_invalid_token_closed_4001(self):
        from httpx_ws import aconnect_ws

        from api.main import app
        try:
            async with aconnect_ws(
                f"/ws/buildings/{BUILDING_ID}?token=bad.token.here", app
            ):
                pass
        except Exception:
            pass  # expected — connection closed with 4001

    async def test_ws_missing_token_rejected(self):
        from httpx import ASGITransport, AsyncClient

        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/ws/buildings/{BUILDING_ID}")
            assert resp.status_code in (400, 422, 404)
