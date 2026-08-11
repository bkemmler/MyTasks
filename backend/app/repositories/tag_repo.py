from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag, TaskTag


class TagRepository:
    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    async def get_all(self) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Tag.name, func.count(TaskTag.task_id))
            .outerjoin(TaskTag, Tag.id == TaskTag.tag_id)
            .where(Tag.user_id == self.user_id)
            .group_by(Tag.id)
            .order_by(func.count(TaskTag.task_id).desc())
        )
        return [{"name": row[0], "task_count": row[1]} for row in result.all()]

    async def get_or_create(self, name: str) -> Tag:
        result = await self.db.execute(
            select(Tag).where(Tag.user_id == self.user_id, Tag.name == name)
        )
        tag = result.scalar_one_or_none()
        if tag:
            return tag
        tag = Tag(user_id=self.user_id, name=name)
        self.db.add(tag)
        await self.db.commit()
        await self.db.refresh(tag)
        return tag

    async def set_tags(self, task_id: int, tag_names: list[str]) -> list[Tag]:
        from sqlalchemy import delete as sa_delete

        await self.db.execute(sa_delete(TaskTag).where(TaskTag.task_id == task_id))
        tags: list[Tag] = []
        for name in tag_names:
            tag = await self.get_or_create(name.strip().lower())
            tt = TaskTag(task_id=task_id, tag_id=tag.id)
            self.db.add(tt)
            tags.append(tag)
        await self.db.commit()
        return tags

    async def get_for_task(self, task_id: int) -> list[str]:
        result = await self.db.execute(
            select(Tag.name)
            .join(TaskTag, Tag.id == TaskTag.tag_id)
            .where(TaskTag.task_id == task_id)
            .order_by(Tag.name)
        )
        return [row[0] for row in result.all()]
