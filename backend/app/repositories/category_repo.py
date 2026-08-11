from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from app.core.exceptions import ConflictError
from app.models.category import Category
from app.repositories.base import UserScopedRepository


class CategoryRepository(UserScopedRepository[Category]):
    model = Category

    async def create(self, **kwargs: Any) -> Category:
        existing = await self.db.execute(
            select(Category).where(
                Category.user_id == self.user_id, Category.name == kwargs["name"]
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Kategorie '{kwargs['name']}' existiert bereits")
        return await super().create(**kwargs)

    async def get_by_name(self, name: str) -> Category | None:
        result = await self.db.execute(
            select(Category).where(
                Category.user_id == self.user_id, Category.name == name
            )
        )
        return result.scalar_one_or_none()

    async def resolve_aliases(self, name_or_alias: str) -> Category | None:
        exact = await self.get_by_name(name_or_alias)
        if exact:
            return exact

        result = await self.db.execute(
            select(Category).where(Category.user_id == self.user_id)
        )
        for cat in result.scalars().all():
            if cat.aliases:
                try:
                    aliases = json.loads(cat.aliases)
                    if name_or_alias in aliases:
                        return cat
                except json.JSONDecodeError:
                    pass
        return None
