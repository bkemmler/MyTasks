from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


PRIO_KEYWORDS: dict[int, list[str]] = {
    1: [
        "sofort",
        "dringend",
        "eilig",
        "kritisch",
        "höchste priorität",
        "asap",
        "dringend!",
    ],
    2: [
        "wichtig",
        "muss bis",
        "vertrag",
        "dsgvo",
        "frist",
    ],
    4: [
        "bei gelegenheit",
        "wäre schön",
        "kein stress",
        "hat zeit",
        "irgendwann",
        "relaxed",
    ],
}

WARTEND_TRIGGERS = [
    r"\bwarte\b",
    r"\bwarten\b",
    r"\bwarte auf\b",
    r"\bantwort\s+ausstehend\b",
    r"\bnoch nicht da\b",
    r"\bseit \w+ tagen\b",
    r"\bausstehend\b",
]

DONE_TRIGGERS = [
    r"\berledigt\b",
    r"\babgehakt\b",
    r"\bfertig\b",
]

URL_RE = re.compile(r"https?://[^\s]+")
TAG_RE = re.compile(r"#(\w+)")


def _strip_urls(text: str) -> tuple[str, str | None]:
    m = URL_RE.search(text)
    if not m:
        return text, None
    return (text[: m.start()] + text[m.end():]).strip(), m.group(0)


def _detect_priority(text: str) -> int:
    """Liefert 1, 2 oder 4 wenn Schlüsselwörter matchen, sonst 3 (default)."""
    t = text.lower()
    for level in (1, 2, 4):
        for kw in PRIO_KEYWORDS[level]:
            if kw in t:
                return level
    return 3


def _detect_status(text: str) -> tuple[str, str | None]:
    """Returns (status, waiting_for)."""
    t = text.lower()
    for pat in DONE_TRIGGERS:
        if re.search(pat, t):
            return "erledigt", None
    for pat in WARTEND_TRIGGERS:
        m = re.search(pat, t)
        if m:
            after = text[m.end():].strip(" .,!?")
            person = _extract_person(after) or after[:50]
            return "wartend", person or None
    return "offen", None


def _extract_person(text: str) -> str | None:
    """Versucht einen Personennamen aus 'warte auf X' / 'X schickt das' zu extrahieren."""
    m = re.search(
        r"(?:von|auf|bei|für|mit)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)",
        text,
    )
    if m:
        candidate = m.group(1).strip()
        if candidate.lower() not in {"antwort", "frage", "info", "nachricht", "mail", "email", "bestätigung", "rückmeldung"}:
            return candidate

    m = re.search(r"([A-ZÄÖÜ][a-zäöüß]+)\s+(?:schickt|meldet|antwortet|liefert|schickt|ruft an)", text)
    if m:
        return m.group(1).strip()
    return None


def _extract_tags(text: str) -> list[str]:
    return list({m.group(1).lower() for m in TAG_RE.finditer(text)})


SUBTASK_VERBS = {
    "machen",
    "tun",
    "erledigen",
    "kontaktieren",
    "rufen",
    "schicken",
    "senden",
    "prüfen",
    "erstellen",
    "kontrollieren",
    "sammeln",
    "besorgen",
    "auflisten",
    "vorbereiten",
    "sortieren",
    "einrichten",
    "testen",
    "bestätigen",
    "abschicken",
    "überarbeiten",
    "aktualisieren",
    "beantworten",
    "erinnern",
    "bestellen",
    "buchen",
    "installieren",
    "konfigurieren",
}


def _extract_subtasks(text: str) -> list[str]:
    """Erkennt eine Komma-getrennte Aufzählung von Tätigkeiten.

    Heuristik: Wenn mindestens 2 der Komma-getrennten Teile ein Verb aus
    SUBTASK_VERBS enthalten, sind das Subtasks.
    """
    if "," not in text:
        return []

    parts = [p.strip(" .,-") for p in text.split(",")]
    parts = [p for p in parts if 3 < len(p) <= 100]

    if len(parts) < 2:
        return []

    has_verb = sum(
        1 for p in parts for v in SUBTASK_VERBS if re.search(rf"\b{v}\b", p, re.IGNORECASE)
    )

    if has_verb >= 2:
        return parts[:8]

    return []


def _clean_title(text: str, due_phrase: str | None) -> str:
    """Bereinigt den Rohtext zu einem kurzen, imperativischen Titel."""
    cleaned = text
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = TAG_RE.sub("", cleaned)

    if due_phrase:
        cleaned = cleaned.replace(due_phrase, " ")

    # Übrig gebliebene Konnektoren am Ende entfernen ("Zahnarzt am")
    cleaned = re.sub(
        r"\s+(?:am|um|ab|bis|zur|zum|in|nächste[nr]?|kommende[nr]?|diese[ns]?)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(
        r"\s+(?:bitte|sofort|dringend|wichtig|bei gelegenheit|heute|morgen|übermorgen|nächste[nr]? woche|bis (?:morgen|freitag|montag|dienstag|mittwoch|donnerstag|sonntag|samstag)|\d{1,2}\.\d{1,2}\.?|\d{1,2}:\d{2})\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = cleaned.strip(" .,;:-")
    if not cleaned:
        return text.strip()[:200]

    if len(cleaned) > 200:
        cleaned = cleaned[:200].rsplit(" ", 1)[0]

    return cleaned


def local_extract(
    source_text: str,
    default_due_time: str = "17:00",
    category_aliases: dict[str, list[str]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Regelbasierte Extraktion. Liefert ein Schema-konformes dict plus confidence.

    Args:
        now: Referenzzeitpunkt für relative Daten (Tests/Eval); Default: jetzt.

    Felder:
      - title: bereinigter Titel
      - due_at, due_source_phrase, due_is_all_day
      - priority: 1..4
      - status: offen|wartend|erledigt
      - waiting_for: str|None
      - tags: list[str]
      - subtasks: list[str]
      - category, category_suggestion: aus Alias-Mapping oder leer
      - ambiguities: list[str]
      - confidence: 0..1
    """
    text = source_text.strip()
    if not text:
        return {
            "title": "",
            "description": None,
            "due_at": None,
            "due_source_phrase": None,
            "due_is_all_day": False,
            "start_at": None,
            "category": None,
            "category_suggestion": None,
            "priority": 3,
            "status": "offen",
            "waiting_for": None,
            "tags": [],
            "subtasks": [],
            "estimated_minutes": None,
            "location": None,
            "url": None,
            "recurrence_rule": None,
            "confidence": 0.0,
            "ambiguities": ["leerer text"],
        }

    text_no_url, url = _strip_urls(text)

    due_at, due_phrase, due_all_day = _extract_due(
        text_no_url, default_due_time, now=now
    )

    title = _clean_title(text_no_url, due_phrase)
    priority = _detect_priority(text_no_url)
    status, waiting_for = _detect_status(text_no_url)

    tags = _extract_tags(text_no_url)
    subtasks = _extract_subtasks(text_no_url) if "," in text_no_url else []

    category, category_suggestion = _match_category(text_no_url, category_aliases or {})

    ambiguities: list[str] = []
    if due_phrase and due_at is None:
        ambiguities.append(f"Datums-Phrase '{due_phrase}' nicht aufgelöst")
    if status == "wartend" and not waiting_for:
        ambiguities.append("wartet-Status ohne erkannte Person")
    if subtasks and title and len(title) < 15:
        ambiguities.append("Subtasks erkannt, Titel ungewöhnlich kurz")

    confidence = _score_confidence(
        title=title,
        due_resolved=due_at is not None,
        has_priority=priority != 3,
        status_certain=status != "offen" or priority != 3 or tags or subtasks,
        ambiguities=ambiguities,
    )

    return {
        "title": title,
        "description": text if len(text) > 200 else None,
        "due_at": due_at,
        "due_source_phrase": due_phrase,
        "due_is_all_day": due_all_day,
        "start_at": None,
        "category": category,
        "category_suggestion": category_suggestion,
        "priority": priority,
        "status": status,
        "waiting_for": waiting_for,
        "tags": tags,
        "subtasks": subtasks,
        "estimated_minutes": None,
        "location": None,
        "url": url,
        "recurrence_rule": None,
        "confidence": confidence,
        "ambiguities": ambiguities,
    }


def _extract_due(
    text: str, default_due_time: str, now: datetime | None = None
) -> tuple[str | None, str | None, bool]:
    """Versucht eine Datums-Phrase zu erkennen und aufzulösen.

    Returns (iso_due_at, phrase, due_is_all_day).
    Eine im Text genannte Uhrzeit ("um 8", "14:30 uhr") wird übernommen;
    ohne Zeit gilt default_due_time und due_is_all_day=True.
    """
    from app.services.date_extract import find_date_phrase, resolve_phrase

    phrase, _end = find_date_phrase(text)
    if not phrase:
        return None, None, False

    try:
        parsed, explicit_time = resolve_phrase(
            phrase,
            now or datetime.now(UTC).replace(tzinfo=None),
            default_time=default_due_time,
        )
        if not parsed:
            return None, phrase, False
        return parsed.isoformat(), phrase, not explicit_time
    except Exception:
        return None, phrase, False


def _match_category(text: str, aliases: dict[str, list[str]]) -> tuple[str | None, str | None]:
    """Sehr einfache Kategorie-Erkennung über exakten Match oder Alias."""
    if not aliases:
        return None, None
    t = text.lower()
    for cat, al in aliases.items():
        if cat.lower() in t:
            return cat, None
        for a in al:
            if a.lower() in t:
                return cat, None
    return None, None


def _score_confidence(
    title: str,
    due_resolved: bool,
    has_priority: bool,
    status_certain: bool,
    ambiguities: list[str],
) -> float:
    score = 0.4
    if title and len(title) >= 5:
        score += 0.2
    if due_resolved:
        score += 0.2
    if has_priority:
        score += 0.1
    if status_certain:
        score += 0.1
    if not title or len(title) < 8:
        score -= 0.2
    score -= 0.1 * len(ambiguities)
    return max(0.0, min(1.0, round(score, 3)))
