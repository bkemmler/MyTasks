from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SSEManager:
    def __init__(self):
        self._queues: list[asyncio.Queue] = []

    def add_queue(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.append(q)
        return q

    def remove_queue(self, q: asyncio.Queue) -> None:
        if q in self._queues:
            self._queues.remove(q)

    def broadcast(self, event: str, data: dict[str, Any]) -> None:
        message = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        for q in self._queues:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(message)


sse_manager = SSEManager()
