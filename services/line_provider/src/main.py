from __future__ import annotations

from fastapi import FastAPI

from src.api.v1.events import router as events_router
from src.core.logging import configure_logging


app = FastAPI(
    title="line-provider",
    description="Provider of betting events",
    version="0.1.0",
)

app.include_router(events_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
