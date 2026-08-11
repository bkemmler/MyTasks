from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.repositories.category_repo import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


def _repo(db: AsyncSession, user: User) -> CategoryRepository:
    return CategoryRepository(db, user.id)


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _repo(db, current_user)
    return await repo.get_all()


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(
    body: CategoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _repo(db, current_user)
    kwargs = body.model_dump()
    if "aliases" in kwargs:
        kwargs["aliases"] = json.dumps(kwargs["aliases"])
    return await repo.create(**kwargs)


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int,
    body: CategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _repo(db, current_user)
    cat = await repo.get_by_id(category_id)
    updates = body.model_dump(exclude_none=True)
    if "aliases" in updates:
        updates["aliases"] = json.dumps(updates["aliases"])
    return await repo.update(cat, **updates)


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _repo(db, current_user)
    cat = await repo.get_by_id(category_id)
    await repo.delete(cat)
