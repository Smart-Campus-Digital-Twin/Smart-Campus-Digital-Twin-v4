"""BuildingRepo — async repository for the buildings table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.orm import Building


class BuildingRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_all(self) -> list[Building]:
        """Return all buildings (no rooms loaded)."""
        result = await self._s.execute(select(Building).order_by(Building.name))
        return list(result.scalars())

    async def get(self, building_id: uuid.UUID) -> Building | None:
        """Return building without rooms."""
        return await self._s.get(Building, building_id)

    async def get_with_rooms(self, building_id: uuid.UUID) -> Building | None:
        """Return building with rooms eagerly loaded."""
        result = await self._s.execute(
            select(Building)
            .where(Building.id == building_id)
            .options(selectinload(Building.rooms))
        )
        return result.scalar_one_or_none()
