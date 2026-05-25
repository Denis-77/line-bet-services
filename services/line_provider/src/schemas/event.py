from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, AfterValidator


class EventStatus(str, Enum):
    NEW = "NEW"
    FIRST_TEAM_WON = "FIRST_TEAM_WON"
    FIRST_TEAM_LOST = "FIRST_TEAM_LOST"


TERMINAL_STATUSES: frozenset[EventStatus] = frozenset(
    {EventStatus.FIRST_TEAM_WON, EventStatus.FIRST_TEAM_LOST}
)


def _quantize_coefficient(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _ensure_tzaware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


Coefficient = Annotated[
    Decimal, Field(gt=Decimal("0"), max_digits=8), AfterValidator(_quantize_coefficient)
]

TzAwareDatetime = Annotated[datetime, AfterValidator(_ensure_tzaware)]


class EventBase(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    coefficient: Coefficient
    deadline: TzAwareDatetime
    status: EventStatus = EventStatus.NEW


class EventCreate(EventBase):
    id: str = Field(min_length=1, max_length=128)


class EventUpdate(BaseModel):
    coefficient: Coefficient | None = None
    deadline: TzAwareDatetime | None = None
    status: EventStatus | None = None


class Event(EventBase):
    id: str
    version: int = 1
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_active(self, now: datetime | None = None) -> bool:
        moment = now or datetime.now(timezone.utc)
        return self.status == EventStatus.NEW and self.deadline > moment
