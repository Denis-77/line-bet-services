from __future__ import annotations

import logging
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.messaging.line_provider_client import LineProviderClient
from src.models.bet import Bet, BetStatus
from src.models.events_cache import EventStatus
from src.repositories.bet import BetRepository
from src.services.events import EventsService

logger = logging.getLogger(__name__)


class BetError(Exception):
    pass


class EventNotFoundError(BetError):
    pass


class EventNotOpenForBetsError(BetError):
    pass


class BetsService:
    def __init__(self, session: AsyncSession, line_provider: LineProviderClient) -> None:
        self._session = session
        self._repo = BetRepository(session)
        self._events_service = EventsService(session, line_provider)

    async def place_bet(self, event_id: str, amount: Decimal) -> Bet:
        event = await self._events_service.get_for_bet(event_id)
        if event is None:
            raise EventNotFoundError(event_id)
        if not self._events_service.is_open_for_bets(event):
            raise EventNotOpenForBetsError(event_id)

        bet = await self._repo.create(event_id=event_id, amount=amount)
        await self._session.commit()
        await self._session.refresh(bet)
        return bet

    async def list_bets(self) -> Sequence[Bet]:
        return await self._repo.list_all()

    async def settle_terminal_event(self, event_id: str, status: EventStatus) -> int:
        """Apply terminal status to PENDING bets on this event."""
        if status == EventStatus.FIRST_TEAM_WON:
            target = BetStatus.WON
        elif status == EventStatus.FIRST_TEAM_LOST:
            target = BetStatus.LOST
        else:
            return 0
        updated = await self._repo.settle_for_event(event_id, target)
        if updated:
            logger.info("Settled %d bets for event %s as %s", updated, event_id, target.value)
        return updated
