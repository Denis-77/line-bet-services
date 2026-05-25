from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session_factory
from src.messaging.line_provider_client import (
    LineProviderClient,
    get_line_provider_client,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


def get_line_provider() -> LineProviderClient:
    return get_line_provider_client()
