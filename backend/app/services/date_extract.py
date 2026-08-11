from __future__ import annotations

import re

_DATE_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\bheute\b", re.IGNORECASE), 5),
    (re.compile(r"\bmorgen\b", re.IGNORECASE), 6),
    (re.compile(r"\bübermorgen\b", re.IGNORECASE), 9),
    (re.compile(r"\b(?:nächste[ns]?|kommende[ns]?|diese[ns]?)\s+woche\b", re.IGNORECASE), 15),
    (re.compile(r"\b(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b", re.IGNORECASE), 9),
    (re.compile(r"\bbis\s+(?:morgen|heute|übermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b", re.IGNORECASE), 15),
    (re.compile(r"\bbis\s+(?:ende\s+(?:der\s+)?woche|ende\s+des\s+monats|quartalsende|jahresende)\b", re.IGNORECASE), 20),
    (re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b", re.IGNORECASE), 12),
    (re.compile(r"\b\d{1,2}\.\d{1,2}\.\b", re.IGNORECASE), 8),
    (re.compile(r"\b\d{1,2}:\d{2}\s*uhr?\b", re.IGNORECASE), 7),
    (re.compile(r"\b\d{1,2}\s*uhr\b", re.IGNORECASE), 5),
    (re.compile(r"\bnächsten\s+(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b", re.IGNORECASE), 18),
    (re.compile(r"\bin\s+\d+\s+(?:tagen?|wochen?|stunden?|minuten?)\b", re.IGNORECASE), 15),
    (re.compile(r"\b(?:januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\b", re.IGNORECASE), 12),
]


def find_date_phrase(text: str) -> tuple[str | None, int]:
    """Sucht im Text nach der ersten Datums-Phrase.

    Returns (phrase, end_index). Gibt (None, -1) zurück, falls nichts gefunden.
    Wählt die längste Phrase bei Mehrfach-Matches auf gleicher Position.
    """
    best_phrase: str | None = None
    best_end = -1

    for pattern, _length in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        phrase = m.group(0)
        end = m.end()
        if end > best_end or (end == best_end and best_phrase and len(phrase) > len(best_phrase)):
            best_phrase = phrase
            best_end = end

    return best_phrase, best_end
