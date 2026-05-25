from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from src.schemas.event import Event, EventCreate, EventUpdate, TERMINAL_STATUSES


class EventAlreadyExistsError(Exception):
    pass


class EventNotFoundError(Exception):
    pass


class EventClosedError(Exception):
    """Thrown when attempting to modify a completed event."""

    pass


class InMemoryEventStorage:
    """Thread/async-safe in-memory storage for events."""

    def __init__(self) -> None:
        self._events: dict[str, Event] = {}
        self._lock = asyncio.Lock()

    async def create(self, payload: EventCreate) -> Event:
        async with self._lock:
            if payload.id in self._events:
                raise EventAlreadyExistsError(payload.id)
            event = Event(
                id=payload.id,
                coefficient=payload.coefficient,
                deadline=payload.deadline,
                status=payload.status,
                version=1,
                updated_at=datetime.now(timezone.utc),
            )
            self._events[event.id] = event
            return event

    async def get(self, event_id: str) -> Event:
        async with self._lock:
            event = self._events.get(event_id)
            if event is None:
                raise EventNotFoundError(event_id)
            return event

    async def list(self, *, active_only: bool = False) -> list[Event]:
        async with self._lock:
            events = list(self._events.values())

        if active_only:
            now = datetime.now(timezone.utc)
            events = [event for event in events if event.is_active(now)]
        return events

    async def update(self, event_id: str, payload: EventUpdate) -> tuple[Event, bool]:
        """Update an event. Returns (event, status_changed)."""
        async with self._lock:
            current = self._events.get(event_id)
            if current is None:
                raise EventNotFoundError(event_id)

            if current.status in TERMINAL_STATUSES:
                raise EventClosedError(
                    f"Cannot update event {event_id} in terminal status {current.status}"
                )

            update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
            if not update_data:
                return current, False

            status_changed = (
                "status" in update_data and update_data["status"] != current.status
            )

            update_data["version"] = current.version + 1
            update_data["updated_at"] = datetime.now(timezone.utc)

            updated = current.model_copy(update=update_data)

            self._events[event_id] = updated
            return updated, status_changed

    async def clear(self) -> None:
        async with self._lock:
            self._events.clear()


storage = InMemoryEventStorage()
