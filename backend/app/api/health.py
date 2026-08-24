from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__ as _APP_VERSION  # noqa: N812

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    ollama: str = "per-user"


_start_time = time.monotonic()


@router.get("", response_model=HealthResponse)
async def health():
    # LLM ist pro Nutzer konfiguriert (siehe /auth/me/llm-config);
    # ein globaler Ollama-Status existiert nicht mehr.
    return HealthResponse(
        status="ok",
        version=_APP_VERSION,
        uptime_seconds=round(time.monotonic() - _start_time, 2),
        ollama="per-user",
    )
