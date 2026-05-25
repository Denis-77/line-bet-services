from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from src.core.config import settings
from src.schemas.event import LineProviderEvent

logger = logging.getLogger(__name__)


class LineProviderClient:
    """Async HTTP client for the line-provider service."""

    def __init__(
        self,
        base_url: str = settings.LINE_PROVIDER_URL,
        timeout_seconds: float = settings.LINE_PROVIDER_TIMEOUT_SECONDS,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def list_events(self, *, active: bool = False) -> list[LineProviderEvent]:
        response = await self._client.get(
            "/events", params={"active": str(active).lower()}
        )
        response.raise_for_status()
        return [LineProviderEvent.model_validate(item) for item in response.json()]

    async def get_event(self, event_id: str) -> LineProviderEvent | None:
        response = await self._client.get(f"/events/{event_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return LineProviderEvent.model_validate(response.json())


_client: LineProviderClient | None = None


def get_line_provider_client() -> LineProviderClient:
    global _client
    if _client is None:
        _client = LineProviderClient()
    return _client


async def close_line_provider_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def line_provider_dependency() -> AsyncIterator[LineProviderClient]:
    yield get_line_provider_client()
