from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__ as _APP_VERSION  # noqa: N812
from app.core.config import settings

router = APIRouter(prefix="/version", tags=["version"])


class VersionResponse(BaseModel):
    app: str
    api: str
    db_schema: str
    git_sha: str
    built_at: str
    min_android: str


@router.get("", response_model=VersionResponse)
async def version():
    return VersionResponse(
        app=_APP_VERSION,
        api=settings.api_version,
        db_schema=settings.db_schema_revision,
        git_sha=settings.git_sha,
        built_at=settings.built_at,
        min_android=settings.min_android_version,
    )
