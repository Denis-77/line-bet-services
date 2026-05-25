from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class BetStatus(str, enum.Enum):
    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"


TERMINAL_BET_STATUSES: frozenset[BetStatus] = frozenset({BetStatus.WON, BetStatus.LOST})


class Bet(Base):
    __tablename__ = "bets"
    __table_args__ = (
        CheckConstraint("amount > 0", name="bets_amount_positive"),
        Index("ix_bets_event_id", "event_id"),
        Index("ix_bets_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[BetStatus] = mapped_column(
        String(16),
        nullable=False,
        default=BetStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
