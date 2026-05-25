from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.v1.events import get_publisher, get_storage
from src.main import app
from src.schemas.event import Event
from src.storage.memory import InMemoryEventStorage


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[Event] = []

    async def publish_status_changed(self, event: Event) -> None:
        self.published.append(event)


@pytest_asyncio.fixture
async def storage() -> AsyncIterator[InMemoryEventStorage]:
    instance = InMemoryEventStorage()
    yield instance


@pytest.fixture
def fake_publisher() -> FakePublisher:
    return FakePublisher()


@pytest_asyncio.fixture
async def client(
    storage: InMemoryEventStorage, fake_publisher: FakePublisher
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_publisher] = lambda: fake_publisher
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
