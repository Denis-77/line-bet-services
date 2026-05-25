from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.messaging.line_provider_client import LineProviderClient
from src.models.events_cache import TERMINAL_EVENT_STATUSES
from src.repositories.events_cache import EventsCacheRepository
from src.services.bets import BetsService

logger = logging.getLogger(__name__)


async def reconcile_events(
    session_factory: async_sessionmaker[AsyncSession],
    line_provider: LineProviderClient,
) -> None:
    """Pull all events from line-provider, refresh the local cache and
    re-apply any terminal statuses to bets that may have been missed.

    This guards against bets staying in PENDING forever if a message was lost
    or never delivered (worker downtime, RabbitMQ outage, etc).
    """
    try:
        events = await line_provider.list_events(active=False)
    except Exception:
        logger.exception("Reconcile failed: cannot fetch events from line-provider")
        return

    if not events:
        logger.info("Reconcile: no events to process")
        return

    async with session_factory() as session:
        cache_repo = EventsCacheRepository(session)
        bets_service = BetsService(session, line_provider)

        terminal_count = 0
        settled_total = 0
        for event in events:
            await cache_repo.upsert_if_newer(
                event_id=event.id,
                coefficient=event.coefficient,
                deadline=event.deadline,
                status=event.status,
                version=event.version,
            )
            if event.status in TERMINAL_EVENT_STATUSES:
                terminal_count += 1
                settled_total += await bets_service.settle_terminal_event(event.id, event.status)
        await session.commit()
        logger.info(
            "Reconcile: synced %d events, %d terminal, %d bets settled",
            len(events),
            terminal_count,
            settled_total,
        )
