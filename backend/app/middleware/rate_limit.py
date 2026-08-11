from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/v1/auth/login"):
            client_ip = request.client.host if request.client else "unknown"
            now = time.monotonic()
            bucket = self._buckets[client_ip]
            bucket[:] = [ts for ts in bucket if now - ts < self.window_seconds]

            if len(bucket) >= 5:
                return Response(
                    content='{"detail":"Zu viele Anfragen"}',
                    status_code=429,
                    media_type="application/json",
                )
            bucket.append(now)

        return await call_next(request)
