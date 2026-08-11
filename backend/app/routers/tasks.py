from __future__ import annotations

import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.llm import LLMJob
from app.models.user import User
from app.repositories.tag_repo import TagRepository
from app.repositories.task_repo import SubtaskRepository, TaskRepository
from app.schemas.task import (
    CaptureRequest,
    SubtaskCreate,
    SubtaskOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _task_repo(db: AsyncSession, user: User) -> TaskRepository:
    return TaskRepository(db, user.id)


def _sub_repo(db: AsyncSession, user: User) -> SubtaskRepository:
    return SubtaskRepository(db, user.id)


def _tag_repo(db: AsyncSession, user: User) -> TagRepository:
    return TagRepository(db, user.id)


def _task_to_out(task) -> TaskOut:
    data = {}
    for col in task.__table__.columns:
        data[col.name] = getattr(task, col.name)
    data["subtasks"] = [SubtaskOut.model_validate(st) for st in task.subtasks]
    data["tags"] = []
    if task.task_tags:
        data["tags"] = [tt.tag.name for tt in task.task_tags if tt.tag]
    return TaskOut(**data)


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    status: str | None = None,
    category_id: int | None = None,
    priority: int | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    tag: str | None = None,
    needs_review: bool | None = None,
    include_completed: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _task_repo(db, current_user)
    tasks = await repo.get_all(
        status=status,
        category_id=category_id,
        priority=priority,
        due_before=due_before,
        due_after=due_after,
        needs_review=needs_review,
        include_completed=include_completed,
        limit=limit,
        offset=offset,
    )
    return [_task_to_out(t) for t in tasks]


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _task_repo(db, current_user)
    tag_repo = _tag_repo(db, current_user)

    tags = body.tags
    data = body.model_dump(exclude={"tags"})
    task = await repo.create(**data)

    if tags:
        await tag_repo.set_tags(task.id, tags)
        await db.refresh(task, ["subtasks", "task_tags"])

    return _task_to_out(task)


@router.post("/capture", response_model=list[TaskOut], status_code=201)
async def capture_task(
    body: CaptureRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _task_repo(db, current_user)
    texts = _split_if_multi(body.text, body.mode)
    tasks_out = []

    for source in texts:
        title = source[:200].replace("\n", " ").strip()
        task = await repo.create(
            title=title if title else "Unbenannt",
            source_text=source,
            description=source if len(source) > 200 else None,
            llm_state="pending",
        )
        job = LLMJob(
            user_id=current_user.id,
            task_id=task.id,
            job_type="capture",
            payload=json.dumps({"task_id": task.id, "source_text": source}),
            state="queued",
        )
        db.add(job)
        await db.commit()
        await db.refresh(task, ["subtasks", "task_tags"])
        tasks_out.append(_task_to_out(task))

    return tasks_out


@router.get("/search", response_model=list[TaskOut])
async def search_tasks(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    from app.models.task import Task

    stmt = (
        sa_select(Task)
        .where(
            Task.user_id == current_user.id,
            Task.deleted_at.is_(None),
            Task.title.ilike(f"%{q}%"),
        )
        .options(selectinload(Task.subtasks), selectinload(Task.task_tags))
        .limit(50)
    )
    result = await db.execute(stmt)
    return [_task_to_out(t) for t in result.scalars().all()]


@router.post("/{uuid}/confirm-review", response_model=TaskOut)
async def confirm_review(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _task_repo(db, current_user)
    task = await repo.get_by_uuid(uuid)
    task.needs_review = False
    await db.commit()
    await db.refresh(task, ["subtasks", "task_tags"])
    return _task_to_out(task)


@router.post("/{uuid}/reparse", response_model=TaskOut)
async def reparse_task(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _task_repo(db, current_user)
    task = await repo.get_by_uuid(uuid)

    if not task.source_text:
        from app.core.exceptions import ValidationError

        raise ValidationError("Task hat keinen source_text")

    task.llm_state = "pending"
    job = LLMJob(
        user_id=current_user.id,
        task_id=task.id,
        job_type="reparse",
        payload=json.dumps({"task_id": task.id, "source_text": task.source_text}),
        state="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(task, ["subtasks", "task_tags"])
    return _task_to_out(task)


@router.get("/{uuid}", response_model=TaskOut)
async def get_task(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _task_repo(db, current_user)
    task = await repo.get_by_uuid(uuid)
    return _task_to_out(task)


@router.patch("/{uuid}", response_model=TaskOut)
async def update_task(
    uuid: str,
    body: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _task_repo(db, current_user)
    task = await repo.get_by_uuid(uuid)
    updates = body.model_dump(exclude_none=True)

    # Wenn der Nutzer den Titel korrigiert, auch source_text aktualisieren.
    # Sonst verwendet "Reparse" beim erneuten LLM-Durchlauf den alten Text.
    if "title" in updates and updates["title"] != task.title:
        updates["source_text"] = updates["title"]

    # Ursprüngliches Fälligkeitsdatum speichern, wenn es geändert wird
    if "due_at" in updates and task.due_at and updates["due_at"] != task.due_at:
        updates["original_due_at"] = task.due_at

    task = await repo.update(task, **updates)
    await db.refresh(task, ["subtasks", "task_tags"])
    return _task_to_out(task)


@router.delete("/{uuid}", status_code=204)
async def delete_task(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _task_repo(db, current_user)
    task = await repo.get_by_uuid(uuid)
    await repo.soft_delete(task)


@router.post("/{uuid}/complete", response_model=TaskOut)
async def complete_task(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = _task_repo(db, current_user)
    task = await repo.get_by_uuid(uuid)
    task = await repo.complete(task)
    await db.refresh(task, ["subtasks", "task_tags"])
    return _task_to_out(task)


@router.post("/{uuid}/subtasks", response_model=SubtaskOut, status_code=201)
async def create_subtask(
    uuid: str,
    body: SubtaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub_repo = _sub_repo(db, current_user)
    return await sub_repo.create(uuid, body.title)


@router.post("/{uuid}/subtasks/{subtask_id}/toggle", response_model=SubtaskOut)
async def toggle_subtask(
    uuid: str,
    subtask_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub_repo = _sub_repo(db, current_user)
    return await sub_repo.toggle(uuid, subtask_id)


@router.delete("/{uuid}/subtasks/{subtask_id}", status_code=204)
async def delete_subtask(
    uuid: str,
    subtask_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub_repo = _sub_repo(db, current_user)
    await sub_repo.delete(uuid, subtask_id)


def _split_if_multi(text: str, mode: str) -> list[str]:
    """Splittet den Capture-Text in mehrere Einzel-Tasks falls erkennbar.

    Auto-Erkennung aktiviert bei mode="auto" ODER wenn der Text mehr als
    200 Zeichen lang ist oder Aufzählungszeichen enthält.
    """
    if mode in ("single",) and len(text) <= 200 and not _has_bullets(text):
        return [text]

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Wenn Aufzählungszeichen (1. 2. - * • etc) oder mehrere Zeilen mit Kommata
    bullets = [line for line in lines if re.match(r"^[\d]+[\.\)]\s+", line) or line.startswith(("- ", "* ", "• "))]

    if len(bullets) >= 2:
        return [re.sub(r"^[\d]+[\.\)]\s+", "", b).strip() for b in bullets[:8]]

    # Ohne Aufzählung aber mehrere Zeilen → jede Zeile ein Task
    if len(lines) >= 2 and all(len(line) >= 10 for line in lines):
        return lines[:8]

    # Fallback: ganzer Text als ein Task
    return [text]


def _has_bullets(text: str) -> bool:
    lines = text.split("\n")
    bullets = [ln for ln in lines if re.match(r"^[\d]+[\.\)]\s+", ln) or ln.startswith(("- ", "* ", "• "))]
    return len(bullets) >= 2
