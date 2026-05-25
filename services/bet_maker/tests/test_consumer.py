from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.bet import Bet, BetStatus
from src.models.events_cache import EventCache, EventStatus
from src.repositories.events_cache import EventsCacheRepository
from src.schemas.event import EventStatusMessage, LineProviderEvent
from src.services.bets import BetsService
from src.workers.handler import handle_status_message
from src.workers.reconcile import reconcile_events
from tests.conftest import FakeLineProvider


def _future_dt(seconds: int = 3600) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _make_message(
    *,
    event_id: str,
    status: EventStatus,
    version: int,
    coefficient: Decimal = Decimal("1.50"),
    deadline: datetime | None = None,
) -> EventStatusMessage:
    return EventStatusMessage(
        event_id=event_id,
        status=status,
        coefficient=coefficient,
        deadline=deadline or _future_dt(),
        version=version,
    )


@pytest.mark.asyncio
async def test_handler_inserts_into_cache(
    session: AsyncSession, fake_line_provider: FakeLineProvider
) -> None:
    message = _make_message(event_id="e1", status=EventStatus.NEW, version=1)
    await handle_status_message(session, fake_line_provider, message)

    cached = await session.get(EventCache, "e1")
    assert cached is not None
    assert cached.status == EventStatus.NEW
    assert cached.version == 1


@pytest.mark.asyncio
async def test_handler_settles_pending_bets_on_terminal_status(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    fake_line_provider: FakeLineProvider,
) -> None:
    fake_line_provider.add(
        LineProviderEvent(
            id="e1",
            coefficient=Decimal("1.50"),
            deadline=_future_dt(),
            status=EventStatus.NEW,
            version=1,
        )
    )

    async with session_factory() as bet_session:
        service = BetsService(bet_session, fake_line_provider)
        await service.place_bet(event_id="e1", amount=Decimal("10.00"))
        await service.place_bet(event_id="e1", amount=Decimal("20.00"))

    async with session_factory() as handler_session:
        await handle_status_message(
            handler_session,
            fake_line_provider,
            _make_message(event_id="e1", status=EventStatus.FIRST_TEAM_WON, version=2),
        )

    async with session_factory() as verify_session:
        result = await verify_session.execute(select(Bet).where(Bet.event_id == "e1"))
        bets = result.scalars().all()
        assert {bet.status for bet in bets} == {BetStatus.WON}


@pytest.mark.asyncio
async def test_handler_is_idempotent_by_version(
    session_factory: async_sessionmaker[AsyncSession],
    fake_line_provider: FakeLineProvider,
) -> None:
    fake_line_provider.add(
        LineProviderEvent(
            id="e1",
            coefficient=Decimal("1.50"),
            deadline=_future_dt(),
            status=EventStatus.NEW,
            version=1,
        )
    )

    async with session_factory() as bet_session:
        service = BetsService(bet_session, fake_line_provider)
        await service.place_bet(event_id="e1", amount=Decimal("10.00"))

    msg_v3 = _make_message(event_id="e1", status=EventStatus.FIRST_TEAM_WON, version=3)
    async with session_factory() as s:
        await handle_status_message(s, fake_line_provider, msg_v3)

    msg_v2_old = _make_message(event_id="e1", status=EventStatus.FIRST_TEAM_LOST, version=2)
    async with session_factory() as s:
        await handle_status_message(s, fake_line_provider, msg_v2_old)

    async with session_factory() as verify:
        cached = await verify.get(EventCache, "e1")
        assert cached is not None
        assert cached.status == EventStatus.FIRST_TEAM_WON
        assert cached.version == 3

        result = await verify.execute(select(Bet).where(Bet.event_id == "e1"))
        bets = result.scalars().all()
        assert all(bet.status == BetStatus.WON for bet in bets)


@pytest.mark.asyncio
async def test_handler_duplicate_terminal_message_safe(
    session_factory: async_sessionmaker[AsyncSession],
    fake_line_provider: FakeLineProvider,
) -> None:
    fake_line_provider.add(
        LineProviderEvent(
            id="e1",
            coefficient=Decimal("1.50"),
            deadline=_future_dt(),
            status=EventStatus.NEW,
            version=1,
        )
    )
    async with session_factory() as s:
        await BetsService(s, fake_line_provider).place_bet("e1", Decimal("10.00"))

    msg = _make_message(event_id="e1", status=EventStatus.FIRST_TEAM_LOST, version=2)
    async with session_factory() as s:
        await handle_status_message(s, fake_line_provider, msg)
    async with session_factory() as s:
        await handle_status_message(s, fake_line_provider, msg)

    async with session_factory() as verify:
        result = await verify.execute(select(Bet).where(Bet.event_id == "e1"))
        bets = result.scalars().all()
        assert {bet.status for bet in bets} == {BetStatus.LOST}


@pytest.mark.asyncio
async def test_reconcile_settles_missed_terminal_status(
    session_factory: async_sessionmaker[AsyncSession],
    fake_line_provider: FakeLineProvider,
) -> None:
    fake_line_provider.add(
        LineProviderEvent(
            id="reconcile-evt",
            coefficient=Decimal("1.80"),
            deadline=_future_dt(),
            status=EventStatus.NEW,
            version=1,
        )
    )
    async with session_factory() as s:
        await BetsService(s, fake_line_provider).place_bet(
            "reconcile-evt", Decimal("15.00")
        )

    fake_line_provider.add(
        LineProviderEvent(
            id="reconcile-evt",
            coefficient=Decimal("1.80"),
            deadline=_future_dt(),
            status=EventStatus.FIRST_TEAM_WON,
            version=5,
        )
    )

    await reconcile_events(session_factory, fake_line_provider)

    async with session_factory() as verify:
        result = await verify.execute(select(Bet).where(Bet.event_id == "reconcile-evt"))
        bets = result.scalars().all()
        assert {bet.status for bet in bets} == {BetStatus.WON}

        cached = await verify.get(EventCache, "reconcile-evt")
        assert cached is not None
        assert cached.version == 5
        assert cached.status == EventStatus.FIRST_TEAM_WON


@pytest.mark.asyncio
async def test_events_cache_repo_does_not_regress_on_old_version(
    session: AsyncSession,
) -> None:
    repo = EventsCacheRepository(session)
    deadline = _future_dt()
    await repo.upsert_if_newer(
        event_id="x",
        coefficient=Decimal("1.50"),
        deadline=deadline,
        status=EventStatus.FIRST_TEAM_WON,
        version=10,
    )
    await session.flush()

    await repo.upsert_if_newer(
        event_id="x",
        coefficient=Decimal("1.50"),
        deadline=deadline,
        status=EventStatus.NEW,
        version=2,
    )
    cached = await session.get(EventCache, "x")
    assert cached is not None
    assert cached.version == 10
    assert cached.status == EventStatus.FIRST_TEAM_WON
