from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.category import Category
from app.models.llm import LLMJob
from app.models.task import Task
from app.models.user import User
from app.schemas.llm import TaskExtraction
from app.services.local_extract import local_extract
from app.services.normalizer import normalize_extraction
from app.services.ollama import OllamaClient
from app.services.prompt import render_prompt
from app.services.user_llm import LLMConfig, get_llm_config

logger = logging.getLogger(__name__)

LOCAL_CONFIDENCE_THRESHOLD = 0.6


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def process_job(job_id: int) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(LLMJob).where(LLMJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job or job.state != "queued":
            return

        job.state = "running"
        job.started_at = _now()
        job.attempts += 1
        await db.commit()

        start = datetime.now(UTC)

        try:
            payload = json.loads(job.payload)
            task_id = payload.get("task_id")
            source_text = payload.get("source_text", "")
            user_id = job.user_id

            cats_result = await db.execute(
                select(Category).where(Category.user_id == user_id)
            )
            user_categories = list(cats_result.scalars().all())
            cat_aliases = {c.name: json.loads(c.aliases) if c.aliases else [] for c in user_categories}

            extraction, source, llm_cfg = await _extract(
                source_text=source_text,
                cat_aliases=cat_aliases,
                user_categories=user_categories,
                user_id=user_id,
                db=db,
            )

            normalized = normalize_extraction(
                extraction,
                user_categories=user_categories,
                default_due_time="17:00",
            )

            if task_id:
                task_result = await db.execute(
                    select(Task).where(Task.id == task_id, Task.user_id == user_id)
                )
                task = task_result.scalar_one_or_none()
                if task:
                    _apply_extraction(task, normalized)
                    task.llm_state = "done"
                    task.llm_confidence = normalized.get("confidence")
                    task.llm_model = "local" if source == "local" else llm_cfg.model
                    task.needs_review = normalized.get("needs_review_date", False) or (
                        source == "local" and normalized.get("confidence", 1.0) < 0.7
                    )
                    if task.needs_review and normalized.get("ambiguities"):
                        task.review_notes = json.dumps(normalized["ambiguities"])

            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            job.state = "done"
            job.finished_at = _now()
            job.duration_ms = int(elapsed)
            job.payload = json.dumps({**payload, "_source": source})
            await db.commit()

        except Exception as e:
            logger.exception("LLM job %s failed", job_id)
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            job.state = "failed"
            job.error = str(e)[:2000]
            job.finished_at = _now()
            job.duration_ms = int(elapsed)
            await db.commit()

            if payload.get("task_id"):
                task_result = await db.execute(
                    select(Task).where(Task.id == task_id)
                )
                task = task_result.scalar_one_or_none()
                if task and task.llm_state == "pending":
                    task.llm_state = "failed"
                    await db.commit()


async def _extract(
    source_text: str,
    cat_aliases: dict[str, list[str]],
    user_categories: list[Category],
    user_id: int,
    db: AsyncSession,
) -> tuple[dict, str, LLMConfig | None]:
    """Hybrid-Extraktion: zuerst lokal, LLM als Fallback bei niedriger Confidence.

    LLM nur mit eigener Konfiguration des Nutzers — ohne Konfiguration
    ausschließlich lokal (kein globaler Fallback).

    Returns (extraction_dict, source, llm_config) mit source in {"local", "llm"}.
    """
    raw = local_extract(source_text, category_aliases=cat_aliases)
    confidence = raw.get("confidence", 0.0)

    # Nutzer-Config laden (User-Objekt minimal nachbauen)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    llm_cfg = await get_llm_config(db, user) if user else None

    # Kein LLM konfiguriert → nur lokale Pipeline
    if llm_cfg is None:
        logger.info("Kein LLM konfiguriert — nur lokale Extraktion (confidence=%.2f)", confidence)
        return raw, "local", None

    if confidence >= LOCAL_CONFIDENCE_THRESHOLD:
        logger.info("Local extract OK (confidence=%.2f)", confidence)
        return raw, "local", llm_cfg

    logger.info(
        "Local extract unsicher (confidence=%.2f), fallback auf LLM", confidence
    )
    extraction, ok = await _llm_extract(
        source_text=source_text,
        cat_aliases=cat_aliases,
        user_categories=user_categories,
        user_id=user_id,
        db=db,
        llm_cfg=llm_cfg,
    )
    if ok:
        return extraction, "llm", llm_cfg

    return raw, "local", llm_cfg


async def _llm_extract(
    source_text: str,
    cat_aliases: dict[str, list[str]],
    user_categories: list[Category],
    user_id: int,
    db: AsyncSession,
    llm_cfg: LLMConfig,
) -> tuple[dict, bool]:
    """LLM-Extraktion mit der Konfiguration des Nutzers. Gibt (extraction, ok) zurück."""
    cat_data = [{"name": c.name, "aliases": cat_aliases.get(c.name, [])} for c in user_categories]
    prompt = render_prompt(
        user_text=source_text,
        categories=cat_data,
        user_context="",
        default_due_time="17:00",
        tz_name="Europe/Berlin",
        examples=await _load_examples(db, user_id, limit=8),
    )

    try:
        client = OllamaClient(base_url=llm_cfg.base_url)
        raw_output = await client.extract_task(
            system_prompt=prompt,
            user_text=source_text,
            timeout=llm_cfg.timeout_seconds,
            model=llm_cfg.model,
        )
        extraction = await _validate_and_repair(raw_output, client, prompt, source_text, model=llm_cfg.model)
        return extraction.model_dump(), True
    except Exception as e:
        logger.warning("LLM-Extraktion fehlgeschlagen: %s", e)
        return {}, False


async def _validate_and_repair(
    raw: dict,
    client: OllamaClient,
    prompt: str,
    user_text: str,
    max_retries: int = 2,
    model: str | None = None,
) -> TaskExtraction:
    for attempt in range(max_retries):
        try:
            return TaskExtraction.model_validate(raw)
        except ValidationError as e:
            if attempt == max_retries - 1:
                raise
            error_text = str(e.errors())
            retry_prompt = (
                prompt
                + f"\n\n## FEHLER BEI DER LETZTEN ANTWORT: {error_text}\n"
                "Bitte korrigiere das JSON entsprechend."
            )
            raw = await client.extract_task(
                system_prompt=retry_prompt,
                user_text=user_text,
                model=model,
            )

    raise ValueError("Max retries exceeded")


def _apply_extraction(task: Task, normalized: dict) -> None:
    task.title = normalized.get("title", task.title)
    task.description = normalized.get("description", task.description)
    task.due_is_all_day = normalized.get("due_is_all_day", False)

    if normalized.get("due_at"):
        with contextlib.suppress(ValueError, TypeError):
            task.due_at = datetime.fromisoformat(normalized["due_at"])

    if normalized.get("start_at"):
        with contextlib.suppress(ValueError, TypeError):
            task.start_at = datetime.fromisoformat(normalized["start_at"])

    task.category_id = normalized.get("category_id", task.category_id)
    task.priority = normalized.get("priority", task.priority)
    task.status = normalized.get("status", task.status)
    task.waiting_for = normalized.get("waiting_for", task.waiting_for)
    task.location = normalized.get("location", task.location)
    task.url = normalized.get("url", task.url)
    task.recurrence_rule = normalized.get("recurrence_rule", task.recurrence_rule)
    task.estimated_minutes = normalized.get("estimated_minutes", task.estimated_minutes)


async def _load_examples(
    db: AsyncSession, user_id: int, limit: int = 8
) -> list[dict]:
    from app.models.llm import LLMCorrection

    result = await db.execute(
        select(LLMCorrection)
        .where(
            LLMCorrection.user_id == user_id,
            LLMCorrection.use_as_example == True,  # noqa: E712
        )
        .order_by(LLMCorrection.created_at.desc())
        .limit(limit)
    )
    corrections = result.scalars().all()
    return [
        {"source_text": c.source_text, "corrected": c.corrected} for c in corrections
    ]
