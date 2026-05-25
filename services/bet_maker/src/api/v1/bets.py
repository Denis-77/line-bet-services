from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, get_line_provider
from src.messaging.line_provider_client import LineProviderClient
from src.schemas.bet import BetCreate, BetCreatedResponse, BetRead
from src.services.bets import (
    BetsService,
    EventNotFoundError,
    EventNotOpenForBetsError,
)

router = APIRouter(tags=["bets"])


@router.post("/bet", response_model=BetCreatedResponse, status_code=status.HTTP_201_CREATED)
async def place_bet(
    payload: BetCreate,
    session: AsyncSession = Depends(get_db_session),
    line_provider: LineProviderClient = Depends(get_line_provider),
) -> BetCreatedResponse:
    service = BetsService(session, line_provider)
    try:
        bet = await service.place_bet(event_id=payload.event_id, amount=payload.amount)
    except EventNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {exc.args[0]!r} not found",
        ) from exc
    except EventNotOpenForBetsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Event {exc.args[0]!r} is not open for bets",
        ) from exc
    return BetCreatedResponse(bet_id=bet.id)


@router.get("/bets", response_model=list[BetRead], response_model_by_alias=True)
async def list_bets(
    session: AsyncSession = Depends(get_db_session),
    line_provider: LineProviderClient = Depends(get_line_provider),
) -> list[BetRead]:
    service = BetsService(session, line_provider)
    bets = await service.list_bets()
    return [BetRead.model_validate(bet) for bet in bets]
