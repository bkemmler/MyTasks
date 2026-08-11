from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__ as _APP_VERSION  # noqa: N812
from app.core.config import settings
from app.services.ollama import OllamaClient

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    ollama: str = "unknown"


_start_time = time.monotonic()


@router.get("", response_model=HealthResponse)
async def health():
    ollama_status = "unknown"
    if not settings.ollama_model:
        ollama_status = "disabled"
    else:
        try:
            client = OllamaClient()
            if await client.health_check():
                ollama_status = "ok"
            else:
                ollama_status = "error"
        except Exception:
            ollama_status = "error"

    return HealthResponse(
        status="ok",
        version=_APP_VERSION,
        uptime_seconds=round(time.monotonic() - _start_time, 2),
        ollama=ollama_status,
    )
