from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.services.sse import sse_manager

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def events(request: Request):
    queue = sse_manager.add_queue()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30)
                    yield message
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            sse_manager.remove_queue(queue)

    return EventSourceResponse(event_generator())
