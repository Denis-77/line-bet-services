from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from src.schemas.event import EventStatus, LineProviderEvent
from tests.conftest import FakeLineProvider


def _future_dt(seconds: int = 3600) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _past_dt(seconds: int = 3600) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def _add_event(
    provider: FakeLineProvider,
    *,
    event_id: str,
    status: EventStatus = EventStatus.NEW,
    deadline: datetime | None = None,
    coefficient: Decimal = Decimal("1.50"),
    version: int = 1,
) -> None:
    provider.add(
        LineProviderEvent(
            id=event_id,
            coefficient=coefficient,
            deadline=deadline or _future_dt(),
            status=status,
            version=version,
        )
    )


@pytest.mark.asyncio
async def test_place_bet_success(
    client: AsyncClient, fake_line_provider: FakeLineProvider
) -> None:
    _add_event(fake_line_provider, event_id="evt-1")

    response = await client.post("/bet", json={"event_id": "evt-1", "amount": "10.50"})
    assert response.status_code == 201, response.text
    assert "bet_id" in response.json()


@pytest.mark.asyncio
async def test_place_bet_event_not_found(client: AsyncClient) -> None:
    response = await client.post(
        "/bet", json={"event_id": "missing", "amount": "10.00"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_place_bet_event_with_terminal_status_rejected(
    client: AsyncClient, fake_line_provider: FakeLineProvider
) -> None:
    _add_event(
        fake_line_provider, event_id="evt-done", status=EventStatus.FIRST_TEAM_WON
    )

    response = await client.post(
        "/bet", json={"event_id": "evt-done", "amount": "5.00"}
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_place_bet_after_deadline_rejected(
    client: AsyncClient, fake_line_provider: FakeLineProvider
) -> None:
    _add_event(fake_line_provider, event_id="evt-past", deadline=_past_dt())

    response = await client.post(
        "/bet", json={"event_id": "evt-past", "amount": "5.00"}
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_place_bet_invalid_amount_rejected(client: AsyncClient) -> None:
    response = await client.post("/bet", json={"event_id": "evt", "amount": "-1.00"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_bets(
    client: AsyncClient, fake_line_provider: FakeLineProvider
) -> None:
    _add_event(fake_line_provider, event_id="evt-list")
    create_response = await client.post(
        "/bet", json={"event_id": "evt-list", "amount": "20.00"}
    )
    assert create_response.status_code == 201
    bet_id = create_response.json()["bet_id"]

    list_response = await client.get("/bets")
    assert list_response.status_code == 200
    data = list_response.json()
    assert len(data) == 1
    item = data[0]
    assert item["bet_id"] == bet_id
    assert item["event_id"] == "evt-list"
    assert item["status"] == "PENDING"
    assert Decimal(item["amount"]) == Decimal("20.00")
