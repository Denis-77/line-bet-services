from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.messaging.line_provider_client import LineProviderClient
from src.models.events_cache import TERMINAL_EVENT_STATUSES
from src.repositories.events_cache import EventsCacheRepository
from src.schemas.event import EventStatusMessage
from src.services.bets import BetsService

logger = logging.getLogger(__name__)


async def handle_status_message(
    session: AsyncSession,
    line_provider: LineProviderClient,
    message: EventStatusMessage,
) -> None:
    """Apply an event status message.

    The function is idempotent: outdated messages (lower or equal version) are
    discarded by the cache repository, and bet settlement only affects PENDING
    bets, so re-deliveries are safe.
    """
    cache_repo = EventsCacheRepository(session)

    coefficient = message.coefficient
    deadline = message.deadline

    if coefficient is None or deadline is None:
        existing = await cache_repo.get(message.event_id)
        if existing is not None:
            coefficient = coefficient or existing.coefficient
            deadline = deadline or existing.deadline
        else:
            live = await line_provider.get_event(message.event_id)
            if live is None:
                logger.warning(
                    "Cannot resolve coefficient/deadline for event %s, skipping",
                    message.event_id,
                )
                return
            coefficient = coefficient or live.coefficient
            deadline = deadline or live.deadline

    await cache_repo.upsert_if_newer(
        event_id=message.event_id,
        coefficient=coefficient,
        deadline=deadline,
        status=message.status,
        version=message.version,
    )

    if message.status in TERMINAL_EVENT_STATUSES:
        bets_service = BetsService(session, line_provider)
        await bets_service.settle_terminal_event(message.event_id, message.status)

    await session.commit()
