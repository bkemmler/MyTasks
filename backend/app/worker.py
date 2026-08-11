from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.llm import LLMJob
from app.models.task import Task
from app.models.user import User
from app.services.pipeline import process_job
from app.services.scheduler import send_daily_summary_to_user
from app.services.sse import sse_manager

logger = logging.getLogger(__name__)

_summary_last_sent: dict[int, datetime] = {}
_reschedule_last_run: datetime | None = None


async def _poll_loop() -> None:
    logger.info("Worker started, polling for LLM jobs...")
    last_summary_check: datetime | None = None
    while True:
        try:
            await _poll_llm_jobs()
            last_summary_check = await _poll_daily_summaries(last_summary_check)
            await _reschedule_overdue_tasks()
        except Exception as e:
            logger.exception("Worker error: %s", e)

        await asyncio.sleep(30)


async def _poll_llm_jobs() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(LLMJob)
            .where(LLMJob.state == "queued")
            .order_by(LLMJob.created_at.asc())
            .limit(1)
        )
        job = result.scalar_one_or_none()

        if job:
            logger.info("Processing job %s (type=%s)", job.id, job.job_type)
            user_id = job.user_id
            task_id = job.task_id
            await process_job(job.id)
            sse_manager.broadcast(
                "llm.done" if job.state == "done" else "llm.failed",
                {"task_id": task_id, "user_id": user_id, "job_id": job.id},
            )
            if task_id:
                sse_manager.broadcast(
                    "task.updated",
                    {"task_id": task_id, "user_id": user_id},
                )


async def _poll_daily_summaries(prev_check: datetime | None) -> datetime:
    """Prüft minütlich, ob ein Nutzer seine Sendezeit erreicht hat."""
    now = datetime.now(UTC)
    if prev_check is None or (now - prev_check) < timedelta(minutes=1):
        if prev_check is None:
            return now
        return prev_check

    async with async_session_factory() as db:
        result = await db.execute(
            select(User).where(User.is_active, User.daily_summary_enabled)
        )
        users = list(result.scalars().all())

    for u in users:
        last = _summary_last_sent.get(u.id)
        if last and (now - last) < timedelta(hours=23):
            continue

        if not _user_local_time_matches(u, now):
            continue

        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == u.id))
            fresh = result.scalar_one_or_none()
            if fresh and await send_daily_summary_to_user(db, fresh):
                _summary_last_sent[u.id] = now
                logger.info("Daily summary sent to user %s", u.username)

    return now


async def _reschedule_overdue_tasks() -> None:
    """Täglich um 12:00 UTC: Tasks von gestern auf heute verschieben."""
    global _reschedule_last_run
    now = datetime.now(UTC)

    # Nur einmal pro Tag ausführen, am oder nach 12:00 UTC
    if _reschedule_last_run and (now - _reschedule_last_run) < timedelta(hours=23):
        return
    if now.hour < 12:
        return

    yesterday = now.replace(tzinfo=None) - timedelta(days=1)
    yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Task).where(
                Task.deleted_at.is_(None),
                Task.status.notin_(["erledigt", "abgebrochen"]),
                Task.due_at >= yesterday_start,
                Task.due_at <= yesterday_end,
            )
        )
        overdue = list(result.scalars().all())

        if not overdue:
            _reschedule_last_run = now
            return

        today = now.replace(tzinfo=None)
        count = 0
        for task in overdue:
            if task.due_at:
                # Altes Fälligkeitsdatum vor der Änderung behalten
                task.original_due_at = task.due_at
                # Behalte die Uhrzeit, ändere nur das Datum auf heute
                time_part = task.due_at.replace(year=today.year, month=today.month, day=today.day)
                task.due_at = time_part
                count += 1

        await db.commit()
        _reschedule_last_run = now
        logger.info(
            "Reschedule: %d Tasks von %s auf %s verschoben",
            count,
            yesterday.strftime("%d.%m.%Y"),
            today.strftime("%d.%m.%Y"),
        )

        # SSE-Broadcast für jedes aktualisierte Task
        for task in overdue:
            sse_manager.broadcast(
                "task.updated",
                {"task_id": task.id, "user_id": task.user_id},
            )


def _user_local_time_matches(user: User, now_utc: datetime) -> bool:
    """True, wenn die Sendezeit des Nutzers genau in der aktuellen Minute liegt."""
    try:
        from zoneinfo import ZoneInfo

        local = now_utc.astimezone(ZoneInfo(user.timezone))
    except Exception:
        local = now_utc

    target = user.daily_summary_time or "07:00"
    try:
        hh, mm = target.split(":")
        return local.hour == int(hh) and local.minute == int(mm)
    except (ValueError, AttributeError):
        return False


_worker_task: asyncio.Task | None = None


async def start_worker() -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_poll_loop())
        logger.info("Worker task started")


async def stop_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _worker_task


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_poll_loop())
