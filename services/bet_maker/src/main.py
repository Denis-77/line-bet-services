from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.v1.bets import router as bets_router
from src.api.v1.events import router as events_router
from src.core.logging import configure_logging
from src.db.session import dispose_engine
from src.messaging.line_provider_client import close_line_provider_client


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    try:
        yield
    finally:
        await close_line_provider_client()
        await dispose_engine()


app = FastAPI(
    title="bet-maker",
    description="Accepts user bets on events",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(events_router)
app.include_router(bets_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
