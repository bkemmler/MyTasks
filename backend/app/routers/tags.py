from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.repositories.tag_repo import TagRepository

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("")
async def list_tags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = TagRepository(db, current_user.id)
    return await repo.get_all()
