from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError

T = TypeVar("T")


class UserScopedRepository[T]:
    model: type[T]
    user_id_field: str = "user_id"

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    def _base_query(self):
        return select(self.model).where(
            getattr(self.model, self.user_id_field) == self.user_id
        )

    async def get_by_id(self, id: int) -> T:
        result = await self.db.execute(
            self._base_query().where(self.model.id == id)
        )
        obj = result.scalar_one_or_none()
        if not obj:
            raise NotFoundError()
        return obj

    async def get_all(self) -> list[T]:
        result = await self.db.execute(self._base_query())
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> T:
        kwargs.setdefault(self.user_id_field, self.user_id)
        obj = self.model(**kwargs)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: T, **kwargs: Any) -> T:
        for key, value in kwargs.items():
            if hasattr(obj, key) and value is not None:
                setattr(obj, key, value)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: T) -> None:
        await self.db.delete(obj)
        await self.db.commit()
