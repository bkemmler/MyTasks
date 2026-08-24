from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import UserLLMConfig
from app.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Effektive LLM-Konfiguration eines Nutzers."""

    base_url: str
    model: str
    timeout_seconds: int = 90


async def get_llm_config_row(db: AsyncSession, user_id: int) -> UserLLMConfig | None:
    result = await db.execute(
        select(UserLLMConfig).where(UserLLMConfig.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_llm_config(db: AsyncSession, user: User) -> LLMConfig | None:
    """LLM-Konfiguration des Nutzers oder None (nur lokale Extraktion).

    Kein globaler Fallback: Ohne eigene Konfiguration (oder ohne Modell)
    wird kein LLM verwendet.
    """
    row = await get_llm_config_row(db, user.id)
    if not row or not row.ollama_model or not row.ollama_base_url:
        return None
    return LLMConfig(
        base_url=row.ollama_base_url.rstrip("/"),
        model=row.ollama_model,
    )


async def list_ollama_models(base_url: str, timeout: float = 5.0) -> list[str]:
    """Lädt die verfügbaren Modelle von einem Ollama-Server (/api/tags)."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(f"{base_url.rstrip('/')}/api/tags")
        r.raise_for_status()
        data = r.json()
    return sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
