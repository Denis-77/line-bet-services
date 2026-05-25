from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, get_line_provider
from src.messaging.line_provider_client import LineProviderClient
from src.schemas.event import EventRead
from src.services.events import EventsService

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventRead])
async def list_events(
    session: AsyncSession = Depends(get_db_session),
    line_provider: LineProviderClient = Depends(get_line_provider),
) -> list[EventRead]:
    service = EventsService(session, line_provider)
    events = await service.list_active()
    return [EventRead.model_validate(event) for event in events]
