from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": ["string", "null"]},
        "due_at": {"type": ["string", "null"]},
        "due_source_phrase": {"type": ["string", "null"]},
        "due_is_all_day": {"type": "boolean"},
        "start_at": {"type": ["string", "null"]},
        "category": {"type": ["string", "null"]},
        "category_suggestion": {"type": ["string", "null"]},
        "priority": {"type": "integer", "minimum": 1, "maximum": 4},
        "status": {"type": "string", "enum": ["offen", "in_bearbeitung", "wartend", "erledigt"]},
        "waiting_for": {"type": ["string", "null"]},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "subtasks": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "estimated_minutes": {"type": ["integer", "null"]},
        "location": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "recurrence_rule": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "ambiguities": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title", "description", "due_at", "due_source_phrase", "due_is_all_day",
        "start_at", "category", "category_suggestion", "priority", "status",
        "waiting_for", "tags", "subtasks", "estimated_minutes", "location",
        "url", "recurrence_rule", "confidence", "ambiguities",
    ],
}


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")

    async def extract_task(
        self,
        system_prompt: str,
        user_text: str,
        model: str | None = None,
        timeout: int = 90,
    ) -> dict[str, Any]:
        model = model or settings.ollama_model
        url = f"{self.base_url}/api/chat"

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "format": EXTRACTION_SCHEMA,
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0.1,
                "num_ctx": 8192,
                "num_predict": 1024,
            },
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["message"]["content"]
        return json.loads(content)

    async def health_check(self) -> bool:
        try:
            url = f"{self.base_url}/api/tags"
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception:
            return False
