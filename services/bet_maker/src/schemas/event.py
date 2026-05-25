from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.models.events_cache import EventStatus


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    coefficient: Decimal
    deadline: datetime
    status: EventStatus


class EventStatusMessage(BaseModel):
    """Payload published by line-provider."""

    event_id: str
    status: EventStatus
    coefficient: Decimal | None = None
    deadline: datetime | None = None
    version: int
    occurred_at: datetime | None = None


class LineProviderEvent(BaseModel):
    """Event entity as exposed by line-provider REST API."""

    id: str
    coefficient: Decimal
    deadline: datetime
    status: EventStatus
    version: int = 1
