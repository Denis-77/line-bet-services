from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import FakePublisher


def _future(seconds: int = 3600) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _past(seconds: int = 3600) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


@pytest.mark.asyncio
async def test_create_and_get_event(client: AsyncClient) -> None:
    response = await client.post(
        "/events",
        json={"id": "evt-1", "coefficient": "1.50", "deadline": _future()},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "evt-1"
    assert data["status"] == "NEW"
    assert data["version"] == 1

    get_response = await client.get("/events/evt-1")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == "evt-1"


@pytest.mark.asyncio
async def test_create_duplicate_event_returns_409(client: AsyncClient) -> None:
    payload = {"id": "evt-dup", "coefficient": "2.00", "deadline": _future()}
    first = await client.post("/events", json=payload)
    assert first.status_code == 201
    second = await client.post("/events", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_get_unknown_event_returns_404(client: AsyncClient) -> None:
    response = await client.get("/events/missing")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_events_active_only(client: AsyncClient) -> None:
    await client.post(
        "/events",
        json={"id": "active", "coefficient": "1.50", "deadline": _future()},
    )
    await client.post(
        "/events",
        json={"id": "expired", "coefficient": "1.50", "deadline": _past()},
    )

    full = await client.get("/events")
    assert {item["id"] for item in full.json()} == {"active", "expired"}

    active = await client.get("/events", params={"active": "true"})
    assert {item["id"] for item in active.json()} == {"active"}


@pytest.mark.asyncio
async def test_patch_event_status_publishes_message(
    client: AsyncClient, fake_publisher: FakePublisher
) -> None:
    await client.post(
        "/events",
        json={"id": "evt-status", "coefficient": "1.50", "deadline": _future()},
    )
    response = await client.patch(
        "/events/evt-status", json={"status": "FIRST_TEAM_WON"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "FIRST_TEAM_WON"
    assert response.json()["version"] == 2
    assert len(fake_publisher.published) == 1
    assert fake_publisher.published[0].id == "evt-status"
    assert fake_publisher.published[0].status.value == "FIRST_TEAM_WON"


@pytest.mark.asyncio
async def test_patch_event_no_status_change_does_not_publish(
    client: AsyncClient, fake_publisher: FakePublisher
) -> None:
    await client.post(
        "/events",
        json={"id": "evt-coef", "coefficient": "1.50", "deadline": _future()},
    )
    response = await client.patch("/events/evt-coef", json={"coefficient": "2.50"})
    assert response.status_code == 200
    assert response.json()["coefficient"] == "2.50"
    assert fake_publisher.published == []


@pytest.mark.asyncio
async def test_patch_unknown_event_returns_404(client: AsyncClient) -> None:
    response = await client.patch("/events/missing", json={"status": "FIRST_TEAM_WON"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_coefficient_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/events",
        json={"id": "evt-bad", "coefficient": "-1.00", "deadline": _future()},
    )
    assert response.status_code == 422
