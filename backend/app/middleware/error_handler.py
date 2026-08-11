from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.exceptions import AppError


class ExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        try:
            return await call_next(request)
        except AppError as e:
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "type": e.error_type,
                    "title": "Fehler",
                    "status": e.status_code,
                    "detail": e.detail,
                },
            )
