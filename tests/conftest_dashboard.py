"""
Pytest fixtures for the dashboard data pipeline.

Mock hierarchy:
  mock_influx   — InfluxDashboardClient with canned DataFrames
  mock_session  — AsyncSession backed by SQLite in-memory (SQLAlchemy)
  client        — httpx.AsyncClient against the FastAPI app with auth bypassed
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.models.orm import Base, Building, Room

# ---------------------------------------------------------------------------
# Constants reused across tests
# ---------------------------------------------------------------------------

BUILDING_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
ROOM_ID     = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
USER_ID     = "test-user"
NODE_ID     = "room_lab_101"

FAKE_TOKEN_CLAIMS = {
    "sub": USER_ID,
    "buildings": [str(BUILDING_ID)],
    "exp": 9999999999,
    "iat": 1000000000,
}


# ---------------------------------------------------------------------------
# In-memory SQLite engine (mirrors schema, no Postgres needed)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def sqlite_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        # Seed a building + room
        session.add(Building(
            id=BUILDING_ID, name="Test Tower", floors=3,
        ))
        session.add(Room(
            id=ROOM_ID, building_id=BUILDING_ID, name="Lab 101",
            floor=1, room_type="laboratory", threejs_node_id=NODE_ID,
        ))
        await session.commit()
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Mock InfluxDashboardClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_influx():
    client = MagicMock()
    df = pd.DataFrame([
        {"room_id": str(ROOM_ID), "building_id": str(BUILDING_ID),
         "floor": 1, "sensor_type": "temperature", "_value": 23.5, "_time": datetime.now(UTC)},
        {"room_id": str(ROOM_ID), "building_id": str(BUILDING_ID),
         "floor": 1, "sensor_type": "humidity", "_value": 55.0, "_time": datetime.now(UTC)},
    ])
    async def mock_room_history(building_id, room_id, field, window="1h"):
        from api.db.influx import _validate_field, _validate_window
        _validate_field(field)
        _validate_window(window)
        return pd.DataFrame()

    client.latest_for_building = AsyncMock(return_value=df)
    client.latest_for_room     = AsyncMock(return_value=df)
    client.room_history        = AsyncMock(side_effect=mock_room_history)
    client.ping                = AsyncMock(return_value=True)
    return client


# ---------------------------------------------------------------------------
# FastAPI test client with auth bypassed
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def client(mock_influx, sqlite_session):
    from api.core.security import TokenClaims
    fake_claims = TokenClaims(
        sub=USER_ID,
        buildings=[str(BUILDING_ID)],
        exp=9999999999,
        iat=1000000000,
    )

    import api.routers.rooms as rooms_mod
    from api.core.security import get_current_user
    from api.db.postgres import session_dep
    from api.main import app

    rooms_mod.set_influx_client(mock_influx)

    app.dependency_overrides[get_current_user] = lambda: fake_claims
    app.dependency_overrides[session_dep] = lambda: sqlite_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
