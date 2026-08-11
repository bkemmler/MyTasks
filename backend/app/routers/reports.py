from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.repositories.task_repo import TaskRepository

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/export")
async def export_tasks(
    format: str = Query("json", pattern="^(json|csv)$"),
    since: datetime | None = None,
    until: datetime | None = None,
    include_completed: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Datenexport (DSGVO Art. 20 — Recht auf Datenübertragbarkeit)."""
    repo = TaskRepository(db, current_user.id)
    tasks = await repo.get_all(
        include_completed=include_completed, limit=10_000
    )

    if since or until:
        filtered = []
        for t in tasks:
            t_time = t.completed_at or t.updated_at
            if since and t_time < since:
                continue
            if until and t_time > until:
                continue
            filtered.append(t)
        tasks = filtered

    rows: list[dict[str, Any]] = []
    for t in tasks:
        rows.append(
            {
                "uuid": t.uuid,
                "title": t.title,
                "description": t.description,
                "source_text": t.source_text,
                "status": t.status,
                "priority": t.priority,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "start_at": t.start_at.isoformat() if t.start_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                "category_id": t.category_id,
                "tags": [],
                "estimated_minutes": t.estimated_minutes,
                "waiting_for": t.waiting_for,
                "location": t.location,
                "url": t.url,
                "recurrence_rule": t.recurrence_rule,
                "progress_percent": t.progress_percent,
                "subtasks": [
                    {"title": st.title, "is_done": st.is_done} for st in t.subtasks
                ],
            }
        )

    if format == "json":
        content = json.dumps(
            {"exported_at": datetime.now(UTC).isoformat(), "tasks": rows},
            ensure_ascii=False,
            indent=2,
        )
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=MyTasks-export-{current_user.id}.json"
            },
        )

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(
            output,
            fieldnames=list(rows[0].keys()),
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            row["subtasks"] = json.dumps(row["subtasks"], ensure_ascii=False)
            writer.writerow(row)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=MyTasks-export-{current_user.id}.csv"
        },
    )


@router.get("/stats")
async def stats(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kennzahlen für Reports."""
    repo = TaskRepository(db, current_user.id)
    all_tasks = await repo.get_all(include_completed=True, limit=10_000)

    now = datetime.now(UTC)
    period_start = now - timedelta(days=days)

    completed = [t for t in all_tasks if t.completed_at and t.completed_at >= period_start.replace(tzinfo=None)]
    created = [t for t in all_tasks if t.created_at and t.created_at >= period_start.replace(tzinfo=None)]

    durations: list[float] = []
    for t in completed:
        if t.created_at and t.completed_at:
            d = (t.completed_at - t.created_at).total_seconds() / 3600
            durations.append(d)

    overdue = [t for t in all_tasks if t.due_at and t.due_at < now.replace(tzinfo=None) and t.status not in ("erledigt", "abgebrochen")]

    by_category: dict[int, int] = {}
    for t in all_tasks:
        if t.category_id and t.status == "erledigt":
            by_category[t.category_id] = by_category.get(t.category_id, 0) + 1

    by_priority: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
    for t in all_tasks:
        if t.status not in ("erledigt", "abgebrochen") and t.priority in by_priority:
            by_priority[t.priority] += 1

    return {
        "period_days": days,
        "created": len(created),
        "completed": len(completed),
        "completion_rate": round(len(completed) / max(len(created), 1), 3),
        "overdue": len(overdue),
        "avg_completion_hours": round(sum(durations) / max(len(durations), 1), 1) if durations else None,
        "open_by_priority": by_priority,
        "completed_by_category": [{"category_id": k, "count": v} for k, v in by_category.items()],
    }
