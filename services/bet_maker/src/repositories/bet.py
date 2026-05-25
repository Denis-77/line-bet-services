from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bet import Bet, BetStatus


class BetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, event_id: str, amount: Decimal) -> Bet:
        bet = Bet(id=uuid.uuid4(), event_id=event_id, amount=amount, status=BetStatus.PENDING)
        self._session.add(bet)
        await self._session.flush()
        return bet

    async def list_all(self) -> Sequence[Bet]:
        result = await self._session.execute(select(Bet).order_by(Bet.created_at.desc()))
        return result.scalars().all()

    async def settle_for_event(self, event_id: str, new_status: BetStatus) -> int:
        """Move all PENDING bets on the given event to the new terminal status.

        Returns number of rows updated.
        """
        stmt = (
            update(Bet)
            .where(Bet.event_id == event_id, Bet.status == BetStatus.PENDING)
            .values(status=new_status)
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0
