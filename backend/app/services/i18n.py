"""Minimale Server-seitige Übersetzung für E-Mail-Texte.

Sprachen: de (Default) und en. Die Nutzer-Sprache kommt aus
user.locale ("de-DE" → "de", alles andere → "en").
"""
from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "de": {
        "summary.subject": "MyTasks — Tageszusammenfassung {date}",
        "summary.greeting": "Hallo {name},",
        "summary.intro": "Hier deine Übersicht für heute:",
        "section.ueberfaellig": "Überfällig",
        "section.heute": "Heute fällig",
        "section.in_bearbeitung": "In Bearbeitung",
        "section.wartend": "Wartend",
        "section.diese_woche": "Diese Woche",
        "section.empfehlung": "Empfehlung",
        "waiting_for": "wartet auf {who}",
        "footer": "MyTasks — LLM-gestützte Task-Verwaltung",
        "test.subject": "[MyTasks] Test-Email",
    },
    "en": {
        "summary.subject": "MyTasks — Daily summary {date}",
        "summary.greeting": "Hello {name},",
        "summary.intro": "Here is your overview for today:",
        "section.ueberfaellig": "Overdue",
        "section.heute": "Due today",
        "section.in_bearbeitung": "In progress",
        "section.wartend": "Waiting",
        "section.diese_woche": "This week",
        "section.empfehlung": "Recommendation",
        "waiting_for": "waiting for {who}",
        "footer": "MyTasks — LLM-powered task management",
        "test.subject": "[MyTasks] Test email",
    },
}

SECTION_KEYS = [
    ("ueberfaellig", "section.ueberfaellig", "#dc2626"),
    ("heute", "section.heute", "#2563eb"),
    ("in_bearbeitung", "section.in_bearbeitung", "#7c3aed"),
    ("wartend", "section.wartend", "#d97706"),
    ("diese_woche", "section.diese_woche", "#0891b2"),
]


def normalize_locale(locale: str | None) -> str:
    if locale and locale.lower().startswith("de"):
        return "de"
    return "en"


def t(locale: str | None, key: str, **kwargs: object) -> str:
    lang = normalize_locale(locale)
    template = TRANSLATIONS.get(lang, {}).get(key) or TRANSLATIONS["de"].get(key) or key
    return template.format(**kwargs) if kwargs else template
