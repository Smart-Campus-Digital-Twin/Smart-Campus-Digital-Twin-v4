"""RoomRepo — async repository for the rooms table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.orm import Room


class RoomRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_for_building(self, building_id: uuid.UUID) -> list[Room]:
        """All rooms in a building, ordered by floor then name."""
        result = await self._s.execute(
            select(Room)
            .where(Room.building_id == building_id)
            .order_by(Room.floor, Room.name)
        )
        return list(result.scalars())

    async def get(self, room_id: uuid.UUID) -> Room | None:
        return await self._s.get(Room, room_id)

    async def get_with_sensors(self, room_id: uuid.UUID) -> Room | None:
        result = await self._s.execute(
            select(Room)
            .where(Room.id == room_id)
            .options(selectinload(Room.sensors))
        )
        return result.scalar_one_or_none()

    async def node_id_map(self, building_id: uuid.UUID) -> dict[str, str]:
        """Return {room_id_str: threejs_node_id} for rooms that have a node id."""
        result = await self._s.execute(
            select(Room.id, Room.threejs_node_id)
            .where(Room.building_id == building_id, Room.threejs_node_id.is_not(None))
        )
        return {str(row.id): row.threejs_node_id for row in result}
