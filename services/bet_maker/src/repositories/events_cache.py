from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.events_cache import EventCache, EventStatus


class EventsCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, event_id: str) -> EventCache | None:
        return await self._session.get(EventCache, event_id)

    async def list_active(self, now: datetime) -> Sequence[EventCache]:
        stmt = (
            select(EventCache)
            .where(EventCache.status == EventStatus.NEW, EventCache.deadline > now)
            .order_by(EventCache.deadline.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def upsert_if_newer(
        self,
        event_id: str,
        coefficient: Decimal,
        deadline: datetime,
        status: EventStatus,
        version: int,
    ) -> EventCache:
        """Insert a new cache entry or update an existing one only if the
        supplied version is strictly greater than the persisted one.

        The check is enforced inside the same transaction so concurrent
        out-of-order deliveries do not regress the snapshot.
        """
        existing = await self._session.get(EventCache, event_id, with_for_update=False)
        if existing is None:
            entity = EventCache(
                event_id=event_id,
                coefficient=coefficient,
                deadline=deadline,
                status=status,
                version=version,
            )
            self._session.add(entity)
            await self._session.flush()
            return entity

        if version > existing.version:
            existing.coefficient = coefficient
            existing.deadline = deadline
            existing.status = status
            existing.version = version
            await self._session.flush()

        return existing
