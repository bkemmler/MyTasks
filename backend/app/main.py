from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__ as _APP_VERSION  # noqa: N812
from app.api.health import router as health_router
from app.api.version import router as version_router
from app.core.config import settings
from app.core.database import engine, init_db
from app.middleware.error_handler import ExceptionMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.categories import router as categories_router
from app.routers.reports import router as reports_router
from app.routers.sse import router as sse_router
from app.routers.tags import router as tags_router
from app.routers.tasks import router as tasks_router
from app.worker import start_worker, stop_worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    worker_enabled = os.environ.get("TASKS_WORKER_ENABLED", "true").lower() == "true"
    if worker_enabled:
        await start_worker()
    try:
        yield
    finally:
        if worker_enabled:
            await stop_worker()
        await engine.dispose()


app = FastAPI(
    title="MyTasks",
    description="LLM-gestützte Task-Anwendung",
    version=_APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(ExceptionMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
if settings.rate_limit_enabled:
    app.add_middleware(RateLimitMiddleware)

app.include_router(health_router, prefix="/api/v1")
app.include_router(version_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(categories_router, prefix="/api/v1")
app.include_router(tags_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(sse_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


# Static-File-Routing mit korrekten Cache-Headern.
# HTML wird nie gecacht (damit Updates sofort wirken),
# hashed Assets (/assets/*) werden 1 Jahr gecacht.
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.is_dir():
    assets_dir = static_dir / "assets"

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(request: Request, full_path: str = ""):
        # API-Routen durchlassen (für den Fall, dass jemand /api/... hier trifft)
        if full_path.startswith("api/"):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not Found")

        # Wenn die angefragte Datei existiert, direkt servieren
        target = static_dir / full_path
        if full_path and target.is_file():
            return _file_response(target, assets_dir)

        # SPA-Fallback: index.html (immer no-cache)
        index = static_dir / "index.html"
        if index.is_file():
            return FileResponse(
                str(index),
                media_type="text/html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Frontend not built")

    def _file_response(path: Path, assets_dir: Path | None) -> FileResponse:
        """Serviert eine Datei mit passendem Cache-Header."""
        if assets_dir and assets_dir in path.parents:
            # Hashed Assets: 1 Jahr cachen (Vite benennt sie mit Hash im Namen)
            cache = "public, max-age=31536000, immutable"
        else:
            # Andere Dateien (HTML, favicon): no-cache
            cache = "no-cache, no-store, must-revalidate"
        return FileResponse(str(path), headers={"Cache-Control": cache})

    # Original SPA-Routes (für direkte Datei-Auflösung ohne Catch-All)
    app.mount(
        "/assets",
        StaticFiles(directory=str(assets_dir) if assets_dir and assets_dir.is_dir() else "/dev/null"),
        name="assets",
    )
