from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.bet import BetStatus


def _quantize_amount(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


Amount = Annotated[Decimal, Field(gt=Decimal("0"), max_digits=18, decimal_places=2)]


class BetCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    amount: Amount

    @field_validator("amount")
    @classmethod
    def _quantize(cls, value: Decimal) -> Decimal:
        return _quantize_amount(value)


class BetCreatedResponse(BaseModel):
    bet_id: uuid.UUID


class BetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(serialization_alias="bet_id")
    event_id: str
    amount: Decimal
    status: BetStatus
    created_at: datetime
