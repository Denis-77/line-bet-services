from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.messaging.line_provider_client import LineProviderClient
from src.models.events_cache import EventCache, EventStatus
from src.repositories.events_cache import EventsCacheRepository

logger = logging.getLogger(__name__)


class EventsService:
    """Read-side service for events available for betting."""

    def __init__(self, session: AsyncSession, line_provider: LineProviderClient) -> None:
        self._session = session
        self._cache_repo = EventsCacheRepository(session)
        self._line_provider = line_provider

    async def list_active(self) -> Sequence[EventCache]:
        return await self._cache_repo.list_active(datetime.now(timezone.utc))

    async def get_for_bet(self, event_id: str) -> EventCache | None:
        """Resolve an event from cache; fall back to live line-provider if missing.

        On cache miss (e.g. shortly after startup before the worker reconciled)
        we query line-provider directly and upsert the snapshot, so POST /bet
        keeps working even with a cold cache.
        """
        cached = await self._cache_repo.get(event_id)
        if cached is not None:
            return cached

        try:
            live = await self._line_provider.get_event(event_id)
        except Exception:
            logger.exception("Failed to fetch event %s from line-provider", event_id)
            return None
        if live is None:
            return None

        upserted = await self._cache_repo.upsert_if_newer(
            event_id=live.id,
            coefficient=live.coefficient,
            deadline=live.deadline,
            status=live.status,
            version=live.version,
        )
        await self._session.commit()
        return upserted

    @staticmethod
    def is_open_for_bets(event: EventCache, now: datetime | None = None) -> bool:
        moment = now or datetime.now(timezone.utc)
        deadline = event.deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return event.status == EventStatus.NEW and deadline > moment
