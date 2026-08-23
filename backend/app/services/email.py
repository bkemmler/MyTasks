from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.user_mail import SmtpConfig

logger = logging.getLogger(__name__)


async def send_email(
    to: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    smtp: SmtpConfig | None = None,
) -> bool:
    """Versendet eine Email im multipart/alternative-Format (Text + HTML).

    Benötigt eine SMTP-Konfiguration (pro Nutzer). Ohne Konfiguration
    oder bei unvollständiger Konfiguration wird nicht versendet.
    """
    if smtp is None or not smtp.is_complete():
        logger.warning("Keine SMTP-Konfiguration vorhanden, Email wird nicht versendet")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((smtp.from_name or "", smtp.from_address))
    msg["To"] = to

    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    def _send():
        if smtp.security == "ssl":
            with smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=30) as s:
                if smtp.username:
                    s.login(smtp.username, smtp.password or "")
                s.send_message(msg)
        else:
            with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as s:
                if smtp.security == "starttls":
                    s.starttls()
                if smtp.username:
                    s.login(smtp.username, smtp.password or "")
                s.send_message(msg)
        return True

    for attempt in range(2):
        try:
            return await asyncio.to_thread(_send)
        except Exception as e:
            logger.warning("SMTP-Versand fehlgeschlagen (Versuch %d): %s", attempt + 1, e)
            if attempt == 1:
                return False
            await asyncio.sleep(5)
    return False


def render_summary_html(user: dict[str, Any], tasks_by_section: dict[str, list[dict]]) -> str:
    """Rendert die HTML-Version der täglichen Zusammenfassung."""
    sections = {
        "ueberfaellig": ("Überfällig", "#dc2626"),
        "heute": ("Heute fällig", "#2563eb"),
        "in_bearbeitung": ("In Bearbeitung", "#7c3aed"),
        "wartend": ("Wartend", "#d97706"),
        "diese_woche": ("Diese Woche", "#0891b2"),
    }
    css = "font-family:system-ui,sans-serif;max-width:680px;margin:0 auto;color:#1c1917;"
    h2 = "font-size:14px;font-weight:600;margin:24px 0 8px;border-bottom:1px solid #e7e5e4;padding-bottom:4px;"
    task = "padding:6px 0;border-bottom:1px solid #f5f5f4;"
    prio_colors = {1: "#dc2626", 2: "#ea580c", 3: "#a8a29e", 4: "#d6d3d1"}
    intro = f"Hallo {user.get('display_name') or user.get('username', '')},"

    html_parts = [
        f'<div style="{css}">',
        "<h1 style=\"font-size:18px;margin:16px 0;\">MyTasks — Tägliche Zusammenfassung</h1>",
        f"<p>{intro}</p>",
        "<p>Hier deine Übersicht für heute:</p>",
    ]

    for key, (label, color) in sections.items():
        items = tasks_by_section.get(key, [])
        if not items:
            continue
        html_parts.append(f'<h2 style="{h2}color:{color};">{label} ({len(items)})</h2>')
        for t in items:
            due_str = ""
            if t.get("due_at"):
                due_str = f' <span style="color:#78716c;font-size:12px;">· {t["due_at"]}</span>'
            wait_str = ""
            if t.get("waiting_for"):
                wait_str = f' <span style="color:#d97706;font-size:12px;">· wartet auf {t["waiting_for"]}</span>'
            p_color = prio_colors.get(t.get("priority", 3), "#a8a29e")
            html_parts.append(
                f'<div style="{task}">'
                f'<span style="display:inline-block;width:24px;text-align:center;'
                f'background:{p_color};color:white;border-radius:3px;font-size:11px;font-weight:600;">'
                f'P{t.get("priority", 3)}</span> '
                f'<span>{t["title"]}</span>{due_str}{wait_str}'
                f"</div>"
            )

    if tasks_by_section.get("llm_einordnung"):
        html_parts.append(
            f'<h2 style="{h2}color:#7c3aed;">Empfehlung</h2>'
            f'<p style="padding:8px;background:#f5f3ff;border-radius:6px;color:#5b21b6;">'
            f"{tasks_by_section['llm_einordnung']}</p>"
        )

    html_parts.append(
        "<p style=\"color:#a8a29e;font-size:12px;margin-top:32px;\">"
        "MyTasks — LLM-gestützte Task-Verwaltung</p>"
        "</div>"
    )
    return "".join(html_parts)


def render_summary_text(user: dict[str, Any], tasks_by_section: dict[str, list[dict]]) -> str:
    """Plain-Text-Version der Zusammenfassung (für Clients ohne HTML)."""
    lines = [f"Hallo {user.get('display_name') or user.get('username', '')},",
             "",
             "Hier deine Übersicht für heute:",
             ""]

    for key, label in [
        ("ueberfaellig", "ÜBERFÄLLIG"),
        ("heute", "HEUTE"),
        ("in_bearbeitung", "IN BEARBEITUNG"),
        ("wartend", "WARTEND"),
        ("diese_woche", "DIESE WOCHE"),
    ]:
        items = tasks_by_section.get(key, [])
        if not items:
            continue
        lines.append(f"== {label} ({len(items)}) ==")
        for t in items:
            parts = [f"[P{t.get('priority', 3)}] {t['title']}"]
            if t.get("due_at"):
                parts.append(f"· {t['due_at']}")
            if t.get("waiting_for"):
                parts.append(f"· wartet auf {t['waiting_for']}")
            lines.append("  " + " ".join(parts))
        lines.append("")

    if tasks_by_section.get("llm_einordnung"):
        lines.append("== EMPFEHLUNG ==")
        lines.append(tasks_by_section["llm_einordnung"])
        lines.append("")

    lines.append("--")
    lines.append("MyTasks — LLM-gestützte Task-Verwaltung")
    return "\n".join(lines)
