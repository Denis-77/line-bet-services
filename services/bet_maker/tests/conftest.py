from __future__ import annotations
import os

from collections.abc import AsyncIterator
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.api.deps import get_db_session, get_line_provider
from src.db.base import Base
from src.main import app
from src.schemas.event import LineProviderEvent
from src.core.config import settings


class FakeLineProvider:
    """In-memory stand-in for the real line-provider HTTP client."""

    def __init__(self) -> None:
        self.events: dict[str, LineProviderEvent] = {}

    def add(self, event: LineProviderEvent) -> None:
        self.events[event.id] = event

    async def list_events(self, *, active: bool = False) -> list[LineProviderEvent]:
        if not active:
            return list(self.events.values())
        now = datetime.now(tz=None)
        result: list[LineProviderEvent] = []
        for event in self.events.values():
            deadline = event.deadline
            if deadline.tzinfo is not None:
                deadline = deadline.replace(tzinfo=None)
            if event.status.value == "NEW" and deadline > now:
                result.append(event)
        return result

    async def get_event(self, event_id: str) -> LineProviderEvent | None:
        return self.events.get(event_id)

    async def close(self) -> None:
        return None


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    test_db_url = settings.TEST_DATABASE_URL

    eng = create_async_engine(test_db_url, future=True)

    async with eng.begin() as conn:

        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(
    engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    yield factory


@pytest_asyncio.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@pytest.fixture
def fake_line_provider() -> FakeLineProvider:
    return FakeLineProvider()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    fake_line_provider: FakeLineProvider,
) -> AsyncIterator[AsyncClient]:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_line_provider] = lambda: fake_line_provider
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
