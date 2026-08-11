from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.task import Subtask, Task
from app.repositories.base import UserScopedRepository


class TaskRepository(UserScopedRepository[Task]):
    model = Task

    async def get_by_uuid(self, uuid: str) -> Task:
        result = await self.db.execute(
            self._base_query()
            .where(Task.uuid == uuid, Task.deleted_at.is_(None))
            .options(
                selectinload(Task.subtasks),
                selectinload(Task.reminders),
                selectinload(Task.task_tags),
            )
        )
        obj = result.scalar_one_or_none()
        if not obj:
            raise NotFoundError()
        return obj

    async def get_all(
        self,
        status: str | None = None,
        category_id: int | None = None,
        priority: int | None = None,
        due_before: datetime | None = None,
        due_after: datetime | None = None,
        tag: str | None = None,
        needs_review: bool | None = None,
        include_completed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        conditions = [Task.deleted_at.is_(None)]

        if not include_completed:
            conditions.append(Task.status.notin_(["erledigt", "abgebrochen"]))

        if status:
            conditions.append(Task.status == status)
        if category_id is not None:
            conditions.append(Task.category_id == category_id)
        if priority is not None:
            conditions.append(Task.priority == priority)
        if due_before:
            conditions.append(Task.due_at <= due_before)
        if due_after:
            conditions.append(Task.due_at >= due_after)
        if needs_review is not None:
            conditions.append(Task.needs_review == needs_review)

        stmt = (
            select(Task)
            .where(Task.user_id == self.user_id, and_(*conditions))
            .options(selectinload(Task.subtasks), selectinload(Task.task_tags))
            .order_by(Task.due_at.asc().nulls_last(), Task.priority.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> Task:

        kwargs.setdefault("uuid", str(_uuid.uuid4()))
        kwargs.setdefault("user_id", self.user_id)
        obj = Task(**kwargs)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        await self.db.refresh(obj, ["subtasks", "task_tags"])
        return obj

    async def update(self, obj: Task, **kwargs: Any) -> Task:
        for key, value in kwargs.items():
            if hasattr(obj, key) and value is not None:
                setattr(obj, key, value)
        await self.db.commit()
        await self.db.refresh(obj)
        await self.db.refresh(obj, ["subtasks", "task_tags"])
        return obj

    async def soft_delete(self, task: Task) -> Task:
        task.deleted_at = datetime.now(UTC)
        await self.db.commit()
        return task

    async def complete(self, task: Task) -> Task:
        from app.services.recurrence import compute_next_occurrence

        task.status = "erledigt"
        task.completed_at = datetime.now(UTC)
        task.progress_percent = 100

        next_instance = None
        if task.recurrence_rule:
            next_due = compute_next_occurrence(
                task.recurrence_rule, task.due_at or task.completed_at
            )
            if next_due:
                next_instance = Task(
                    uuid=str(_uuid.uuid4()),
                    user_id=task.user_id,
                    title=task.title,
                    description=task.description,
                    source_text=task.source_text,
                    due_at=next_due,
                    due_is_all_day=task.due_is_all_day,
                    category_id=task.category_id,
                    priority=task.priority,
                    status="offen",
                    estimated_minutes=task.estimated_minutes,
                    waiting_for=task.waiting_for,
                    location=task.location,
                    url=task.url,
                    recurrence_rule=task.recurrence_rule,
                    parent_task_id=task.id,
                    llm_state="none",
                )
                self.db.add(next_instance)

        await self.db.commit()
        await self.db.refresh(task)
        if next_instance:
            await self.db.refresh(next_instance, ["subtasks", "task_tags"])
        return task


class SubtaskRepository:
    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.task_repo = TaskRepository(db, user_id)

    async def create(self, task_uuid: str, title: str, **kwargs: Any) -> Subtask:
        task = await self.task_repo.get_by_uuid(task_uuid)
        subtask = Subtask(task_id=task.id, title=title, **kwargs)
        self.db.add(subtask)
        await self.db.commit()
        await self.db.refresh(subtask)
        return subtask

    async def toggle(self, task_uuid: str, subtask_id: int) -> Subtask:
        task = await self.task_repo.get_by_uuid(task_uuid)
        result = await self.db.execute(
            select(Subtask).where(Subtask.id == subtask_id, Subtask.task_id == task.id)
        )
        subtask = result.scalar_one_or_none()
        if not subtask:
            raise NotFoundError()
        subtask.is_done = not subtask.is_done
        subtask.completed_at = datetime.now(UTC) if subtask.is_done else None
        await self.db.commit()
        return subtask

    async def delete(self, task_uuid: str, subtask_id: int) -> None:
        task = await self.task_repo.get_by_uuid(task_uuid)
        result = await self.db.execute(
            select(Subtask).where(Subtask.id == subtask_id, Subtask.task_id == task.id)
        )
        subtask = result.scalar_one_or_none()
        if not subtask:
            raise NotFoundError()
        await self.db.delete(subtask)
        await self.db.commit()
