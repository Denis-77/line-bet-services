from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.messaging.publisher import EventPublisher
from src.messaging.publisher import publisher as default_publisher
from src.schemas.event import Event, EventCreate, EventUpdate
from src.storage.memory import (
    EventAlreadyExistsError,
    EventNotFoundError,
    InMemoryEventStorage,
)
from src.storage.memory import storage as default_storage

router = APIRouter(prefix="/events", tags=["events"])


def get_storage() -> InMemoryEventStorage:
    return default_storage


def get_publisher() -> EventPublisher:
    return default_publisher


@router.post("", response_model=Event, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate,
    storage: InMemoryEventStorage = Depends(get_storage),
) -> Event:
    try:
        return await storage.create(payload)
    except EventAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Event with id {exc.args[0]!r} already exists",
        ) from exc


@router.get("", response_model=list[Event])
async def list_events(
    active: bool = Query(False, description="Return only events available for betting"),
    storage: InMemoryEventStorage = Depends(get_storage),
) -> list[Event]:
    return await storage.list(active_only=active)


@router.get("/{event_id}", response_model=Event)
async def get_event(
    event_id: str,
    storage: InMemoryEventStorage = Depends(get_storage),
) -> Event:
    try:
        return await storage.get(event_id)
    except EventNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {exc.args[0]!r} not found",
        ) from exc


@router.patch("/{event_id}", response_model=Event)
async def update_event(
    event_id: str,
    payload: EventUpdate,
    storage: InMemoryEventStorage = Depends(get_storage),
    publisher: EventPublisher = Depends(get_publisher),
) -> Event:
    try:
        event, status_changed = await storage.update(event_id, payload)
    except EventNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {exc.args[0]!r} not found",
        ) from exc

    if status_changed:
        await publisher.publish_status_changed(event)

    return event
