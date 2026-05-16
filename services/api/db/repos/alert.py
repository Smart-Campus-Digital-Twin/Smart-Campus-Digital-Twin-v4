"""AlertRepo — async repository for the alerts table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.orm import Alert


class AlertRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_alerts(
        self,
        building_id: uuid.UUID | None,
        resolved: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Alert], int]:
        """Return (alerts, total_count) with optional filters."""
        q = select(Alert).options(selectinload(Alert.room))

        if building_id is not None:
            q = q.where(Alert.building_id == building_id)
        if resolved is not None:
            q = q.where(Alert.resolved == resolved)

        total_q = select(func.count()).select_from(q.subquery())
        total = (await self._s.execute(total_q)).scalar_one()

        q = q.order_by(Alert.created_at.desc()).offset(offset).limit(limit)
        rows = list((await self._s.execute(q)).scalars())
        return rows, total

    async def get(self, alert_id: uuid.UUID) -> Alert | None:
        result = await self._s.execute(
            select(Alert)
            .where(Alert.id == alert_id)
            .options(selectinload(Alert.room))
        )
        return result.scalar_one_or_none()

    async def resolve(self, alert_id: uuid.UUID) -> Alert | None:
        """Mark alert as resolved, return updated row."""
        await self._s.execute(
            update(Alert)
            .where(Alert.id == alert_id, Alert.resolved == False)  # noqa: E712
            .values(resolved=True, resolved_at=datetime.now(UTC))
        )
        await self._s.flush()
        return await self.get(alert_id)
