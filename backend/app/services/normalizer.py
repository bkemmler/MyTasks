from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import dateparser
from dateutil.rrule import rrulestr

from app.models.category import Category

logger = logging.getLogger(__name__)


def normalize_extraction(
    raw: dict,
    user_categories: list[Category],
    default_due_time: str = "17:00",
    now: datetime | None = None,
) -> dict:
    if now is None:
        now = datetime.now(UTC).replace(tzinfo=None)

    result = dict(raw)

    if result.get("priority"):
        result["priority"] = min(max(int(result["priority"]), 1), 4)
    else:
        result["priority"] = 3

    if result.get("status") not in ("offen", "in_bearbeitung", "wartend", "erledigt"):
        result["status"] = "offen"

    tags = result.get("tags", [])
    if isinstance(tags, list):
        result["tags"] = list({t.strip().lower() for t in tags})[:5]
    else:
        result["tags"] = []

    subtasks = result.get("subtasks", [])
    if not isinstance(subtasks, list):
        result["subtasks"] = []

    title = result.get("title", "Unbenannt")
    if len(title) > 200:
        result["title"] = title[:200]

    result["category_id"], result["category_suggestion"] = _match_category(
        result.get("category"), result.get("category_suggestion"), user_categories
    )

    result["due_at"], result["needs_review_date"] = _resolve_date(
        result.get("due_at"),
        result.get("due_source_phrase"),
        default_due_time,
        result.get("due_is_all_day", False),
        now,
    )

    result["start_at"], _ = _resolve_date(
        result.get("start_at"), None, default_due_time, False, now
    )

    if result.get("recurrence_rule"):
        try:
            rrulestr(result["recurrence_rule"])
        except Exception:
            result["recurrence_rule"] = None

    confidence = result.get("confidence", 0.5)
    try:
        confidence = min(max(float(confidence), 0.0), 1.0)
    except (ValueError, TypeError):
        confidence = 0.5
    result["confidence"] = confidence

    return result


def _match_category(
    category_name: str | None,
    suggestion: str | None,
    user_categories: list[Category],
) -> tuple[int | None, str | None]:
    if not category_name:
        return None, suggestion

    category_name_lower = category_name.strip().lower()

    for cat in user_categories:
        if cat.name.lower() == category_name_lower:
            return cat.id, None
        if cat.aliases:
            try:
                aliases = json.loads(cat.aliases)
                if category_name_lower in (a.lower() for a in aliases):
                    return cat.id, None
            except (json.JSONDecodeError, TypeError):
                pass

    for cat in user_categories:
        if category_name_lower in cat.name.lower() or cat.name.lower() in category_name_lower:
            return cat.id, None

    return None, suggestion if suggestion else category_name


def _resolve_date(
    iso_date: str | None,
    source_phrase: str | None,
    default_due_time: str,
    is_all_day: bool,
    now: datetime,
) -> tuple[str | None, bool]:
    if not iso_date:
        return None, False

    llm_date = _parse_iso(iso_date)
    parser_date = None

    if source_phrase:
        parser_date = _parse_with_dateparser(source_phrase, now)

    needs_review = False

    if llm_date and parser_date:
        diff_hours = abs((llm_date - parser_date).total_seconds()) / 3600
        if diff_hours <= 1:
            final_date = llm_date
        elif diff_hours > 24:
            final_date = parser_date
            needs_review = True
        else:
            final_date = parser_date
            needs_review = True
    elif llm_date:
        final_date = llm_date
        needs_review = True
    else:
        return None, False

    if final_date < now:
        needs_review = True

    delta_days = (final_date - now).days
    if delta_days > 730:
        needs_review = True

    return final_date.isoformat(), needs_review


def _parse_iso(value: str) -> datetime | None:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None) - dt.utcoffset()
        return dt
    except (ValueError, TypeError):
        return None


def _parse_with_dateparser(text: str, now: datetime) -> datetime | None:
    try:
        settings = {
            "RELATIVE_BASE": now,
            "PREFER_DATES_FROM": "future",
            "PREFER_DAY_OF_MONTH": "first",
        }
        result = dateparser.parse(text, languages=["de"], settings=settings)
        if result:
            if result.tzinfo is not None:
                result = result.replace(tzinfo=None) - result.utcoffset()
            return result
    except Exception:
        pass
    return None
