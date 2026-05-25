from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class EventStatus(str, enum.Enum):
    NEW = "NEW"
    FIRST_TEAM_WON = "FIRST_TEAM_WON"
    FIRST_TEAM_LOST = "FIRST_TEAM_LOST"


TERMINAL_EVENT_STATUSES: frozenset[EventStatus] = frozenset(
    {EventStatus.FIRST_TEAM_WON, EventStatus.FIRST_TEAM_LOST}
)


class EventCache(Base):
    __tablename__ = "events_cache"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    coefficient: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[EventStatus] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
