from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.user import User
from app.services.email import render_summary_html, render_summary_text, send_email

logger = logging.getLogger(__name__)


def _naive_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def build_summary_for_user(
    db: AsyncSession, user: User
) -> tuple[dict[str, list[dict]], str, str]:
    """Baut die Zusammenfassung für einen Nutzer (Sektionen + Text + HTML)."""
    now = _naive_utc()
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999_999)
    week_start = now - timedelta(days=now.weekday())
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

    result = await db.execute(
        select(Task)
        .where(Task.user_id == user.id, Task.deleted_at.is_(None))
    )
    tasks = list(result.scalars().all())

    sections: dict[str, list[dict]] = {
        "ueberfaellig": [],
        "heute": [],
        "in_bearbeitung": [],
        "wartend": [],
        "diese_woche": [],
    }

    for t in tasks:
        if t.status in ("erledigt", "abgebrochen"):
            continue
        due = t.due_at
        item = {
            "title": t.title,
            "priority": t.priority,
            "due_at": due.strftime("%d.%m. %H:%M") if due else None,
            "waiting_for": t.waiting_for if t.status == "wartend" else None,
        }
        if due and due < now and t.status not in ("erledigt", "abgebrochen"):
            sections["ueberfaellig"].append(item)
        elif due and due <= today_end:
            sections["heute"].append(item)
        elif t.status == "in_bearbeitung":
            sections["in_bearbeitung"].append(item)
        elif t.status == "wartend":
            sections["wartend"].append(item)
        elif due and week_start <= due <= week_end:
            sections["diese_woche"].append(item)

    for k in sections:
        sections[k].sort(key=lambda x: (x["priority"], x.get("due_at") or ""))

    llm_einordnung = await _maybe_llm_einordnung(sections, user)
    if llm_einordnung:
        sections["llm_einordnung"] = llm_einordnung

    user_dict = {"username": user.username, "display_name": user.display_name}
    text = render_summary_text(user_dict, sections)
    html = render_summary_html(user_dict, sections)
    return sections, text, html


async def _maybe_llm_einordnung(
    sections: dict[str, list[dict]], user: User
) -> str | None:
    """Wenn der Nutzer ein LLM aktiviert hat, ergänzt eine kurze Einordnung."""
    if user.daily_summary_enabled is False and not sections.get("heute") and not sections.get("ueberfaellig"):
        return None
    try:
        from app.core.config import settings

        if not settings.ollama_model:
            return None

        lines = []
        if sections.get("ueberfaellig"):
            lines.append(f"{len(sections['ueberfaellig'])} überfällig")
        if sections.get("heute"):
            lines.append(f"{len(sections['heute'])} heute fällig")
        if sections.get("in_bearbeitung"):
            lines.append(f"{len(sections['in_bearbeitung'])} in Bearbeitung")
        if sections.get("wartend"):
            lines.append(f"{len(sections['wartend'])} wartend")

        if not lines:
            return None

        prompt = (
            "Du bist eine knappe, motivierende Task-Assistentin. "
            "Gib eine 1-2-Sätze-Tagesplan-Empfehlung in der Du-Form, "
            "basierend auf dieser Übersicht. Keine Aufzählung, keine Fragen.\n\n"
            + " | ".join(lines)
        )
        import httpx

        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "format": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 200},
                },
            )
            r.raise_for_status()
            data = r.json()
            return data.get("message", {}).get("content", "").strip().strip('"') or None
    except Exception as e:
        logger.warning("LLM-Einordnung fehlgeschlagen: %s", e)
        return None


async def send_daily_summary_to_user(db: AsyncSession, user: User) -> bool:
    """Baut die Zusammenfassung und versendet sie an einen Nutzer."""
    if not user.email or not user.daily_summary_enabled:
        return False

    try:
        sections, text, html = await build_summary_for_user(db, user)
    except Exception as e:
        logger.exception("Summary-Build fehlgeschlagen für %s: %s", user.username, e)
        return False

    if not any(sections.get(k) for k in ("ueberfaellig", "heute", "in_bearbeitung", "wartend", "diese_woche")):
        return False

    subject = f"MyTasks — Tageszusammenfassung {datetime.now().strftime('%d.%m.%Y')}"
    return await send_email(
        to=user.email,
        subject=subject,
        text_body=text,
        html_body=html,
    )
