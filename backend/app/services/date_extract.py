"""Erkennung und Auflösung von Datums-/Zeit-Phrasen in deutschem Text.

Vorgehen:
1. find_date_phrase(): findet die zusammenhängende Datums-Spanne.
   Einzelne Bausteine (Wochentag, "morgen", Uhrzeit, Datum …), die nur
   durch Konnektoren ("am", "um", "bis", …) getrennt sind, werden zu
   einer Phrase gemerged — so geht bei "morgen um 8" nichts verloren.
2. resolve_phrase(): löst die Phrase auf. Bekannte Muster (z. B.
   "nächste Woche Samstag", "Ende des Monats", "in 3 Tagen") werden
   manuell berechnet, der Rest an dateparser delegiert.

Rückgabe ist immer ein naive-UTC-ISO-String plus Flag, ob eine
Uhrzeit in der Phrase stand.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

# ── Bausteine ────────────────────────────────────────────────────────

WEEKDAYS = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonntag": 6,
}

_BLOCK_RES: list[re.Pattern[str]] = [
    # Relativtage
    re.compile(r"übermorgen|morgen|heute", re.IGNORECASE),
    # Wochentag mit optionalem Artikel/Adjektiv davor wird beim Merge behandelt
    re.compile(r"(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)", re.IGNORECASE),
    # Woche + Quantor
    re.compile(r"(?:nächste[nr]?|kommende[nr]?|diese[ns]?)\s+woche", re.IGNORECASE),
    # Ende-Muster
    re.compile(r"ende\s+(?:der\s+woche|des\s+monats|diese[rs]\s+woche)", re.IGNORECASE),
    # Datum
    re.compile(r"\d{1,2}\.\d{1,2}\.(?:\d{2,4})?", re.IGNORECASE),
    # Monat mit optionalem Tag
    re.compile(r"(?:\d{1,2}\.\s*)?(?:januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)(?:\s+\d{4})?", re.IGNORECASE),
    # In N Einheiten
    re.compile(r"in\s+\d+\s+(?:tagen?|wochen?|stunden?|minuten?)", re.IGNORECASE),
    # Uhrzeit: "8 uhr", "14:30", "9.30 uhr", "um 8"
    re.compile(r"\d{1,2}(?:[:.]\d{2})?\s*(?:uhr)?", re.IGNORECASE),
]

# Konnektoren zwischen zwei Bausteinen (werden Teil der Phrase)
_CONNECTOR_RE = re.compile(
    r"^[\s,]*(?:am|um|ab|bis|zur|zum|der|den|dem|die|das|des|"
    r"nächste[nr]?|kommende[nr]?|diese[ns]?|früh|vormittags|mittags|nachmittags|abends)?[\s,.]*",
    re.IGNORECASE,
)

_TIME_RE = re.compile(
    # Reihenfolge wichtig: spezifische Formate zuerst; "um 9" nicht bei
    # "um 9:30" greifen lassen (sonst verschluckt es die Minuten).
    r"\b(\d{1,2}):(\d{2})\b"
    r"|\b(\d{1,2})(?:\.(\d{2}))?\s*uhr\b"
    r"|\bum\s+(\d{1,2})(?![:.]\d)",
    re.IGNORECASE,
)

_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}


def _block_at(text: str, pos: int) -> tuple[int, int] | None:
    """Findet einen Datums-Baustein ab Position pos. Returns (start, end)."""
    best: tuple[int, int] | None = None
    for pattern in _BLOCK_RES:
        m = pattern.match(text, pos)
        if m and (best is None or m.end() > best[1]):
            best = (pos, m.end())
    return best


def _is_time_block(text: str, start: int, end: int) -> bool:
    """True, wenn der Block eine Uhrzeit ist (Zahl + 'uhr' oder H:MM)."""
    block = text[start:end]
    return bool(re.fullmatch(r"\d{1,2}([:.]\d{2})?\s*(uhr)?", block.strip(), re.IGNORECASE)) and (
        "uhr" in block.lower() or ":" in block or "." in block
    )


def find_date_phrase(text: str) -> tuple[str | None, int]:
    """Findet die längste zusammenhängende Datums-Spanne.

    Returns (phrase, end_index) oder (None, -1).
    """
    best_phrase: str | None = None
    best_end = -1

    for m in re.finditer(r"\S+", text):
        start = m.start()
        if start < best_end:
            continue  # liegt in bereits überdeckter Spanne

        block = _block_at(text, start)
        if not block:
            continue

        cur_start, cur_end = block
        # Nachbarn links/rechts über Konnektoren mergen
        while True:
            merged = False
            # nach rechts
            rest = text[cur_end:]
            cm = _CONNECTOR_RE.match(rest)
            if cm:
                nxt_pos = cur_end + cm.end()
                nb = _block_at(text, nxt_pos)
                if nb:
                    cur_end = nb[1]
                    merged = True
            # nach links (z. B. "nächsten Freitag")
            before = text[:cur_start].rstrip()
            wm = re.search(r"(\b(?:am|um|ab|bis|zur|zum)\s+)?$",
                           before, re.IGNORECASE)
            lm = re.search(
                r"\b(?:nächste[nr]?|kommende[nr]?|diese[ns]?)\s*$", before, re.IGNORECASE
            )
            if lm:
                cur_start = lm.start()
                merged = True
            elif wm and wm.group(1):
                pb = _block_at(text, wm.start(1))
                if pb:
                    cur_start = pb[0]
                    merged = True
            if not merged:
                break

        phrase = text[cur_start:cur_end].strip()
        if cur_end > best_end:
            best_phrase = phrase
            best_end = cur_end

    return best_phrase, best_end


def has_time(phrase: str) -> bool:
    """True, wenn die Phrase eine explizite Uhrzeit enthält."""
    return bool(_TIME_RE.search(phrase))


def parse_time(phrase: str) -> tuple[int, int] | None:
    """Extrahiert (Stunde, Minute) aus der Phrase oder None."""
    m = _TIME_RE.search(phrase)
    if not m:
        return None
    hour = int(m.group(1) or m.group(3) or m.group(5))
    minute = int(m.group(2) or m.group(4) or 0)
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def resolve_phrase(
    phrase: str, now: datetime, default_time: str = "17:00"
) -> tuple[datetime | None, bool]:
    """Löst eine Datums-Phrase zu einem naive datetime auf.

    Returns (dt, has_explicit_time). dt=None wenn nicht auflösbar.
    """
    p = phrase.lower().strip()

    t = parse_time(p)
    explicit_time = t is not None
    hh, mm = t if t else _default_hh_mm(default_time)

    def with_time(base: datetime) -> datetime:
        return base.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # "in N tagen/wochen/stunden/minuten"
    m = re.search(r"in\s+(\d+)\s+(tagen?|wochen?|stunden?|minuten?)", p)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("tag"):
            delta = timedelta(days=amount)
        elif unit.startswith("woche"):
            delta = timedelta(weeks=amount)
        elif unit.startswith("stund"):
            delta = timedelta(hours=amount)
        else:  # minuten
            delta = timedelta(minutes=amount)
        base = now + delta
        if unit.startswith("stund") or unit.startswith("minut"):
            return base.replace(second=0, microsecond=0), True
        return with_time(base), explicit_time

    # "nächste/kommende woche <wochentag>"
    m = re.search(r"(?:nächste[nr]?|kommende[nr]?)\s+woche\s+(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)", p)
    if m:
        target = WEEKDAYS[m.group(1)]
        days_ahead = target - now.weekday() + 7
        if days_ahead <= 7:
            days_ahead += 7
        base = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0)
        return with_time(base), explicit_time

    # "<adjektiv> <wochentag>" — nächster/kommender passender Tag
    m = re.search(r"(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)", p)
    if m and ("nächste" in p or "kommende" in p or "am" in p or len(p.split()) <= 4):
        target = WEEKDAYS[m.group(1)]
        days_ahead = (target - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        base = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0)
        return with_time(base), explicit_time

    # "ende des monats"
    if re.search(r"ende\s+des\s+monats|monatsende", p):
        if now.month == 12:
            base = now.replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            base = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
        return with_time(base), explicit_time

    # "ende der/dieser woche" → Freitag
    if re.search(r"ende\s+(?:der|dieser)\s+woche", p):
        days_ahead = (4 - now.weekday()) % 7
        base = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0)
        return with_time(base), explicit_time

    # "übermorgen / morgen / heute"
    if "übermorgen" in p:
        return with_time(now + timedelta(days=2)), explicit_time
    if re.search(r"\bmorgen\b", p):
        return with_time(now + timedelta(days=1)), explicit_time
    if re.search(r"\bheute\b", p):
        return with_time(now), explicit_time

    # "<tag>.<monat>[.<jahr>]"
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})?", p)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = now.year
        if m.group(3):
            year = int(m.group(3))
            if year < 100:
                year += 2000
        try:
            base = now.replace(year=year, month=month, day=day, hour=0, minute=0)
            if not m.group(3) and base < now.replace(hour=0, minute=0):
                base = base.replace(year=year + 1)
            return with_time(base), explicit_time
        except ValueError:
            pass

    # "<tag>. <monatname>[ jahr]" bzw. "<monatname>"
    m = re.search(r"(?:(\d{1,2})\.\s*)?(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)(?:\s+(\d{4}))?", p)
    if m and m.group(2):
        day = int(m.group(1)) if m.group(1) else 1
        month = _MONTHS[m.group(2)]
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            base = now.replace(year=year, month=month, day=day, hour=0, minute=0)
            if not m.group(3) and base < now.replace(hour=0, minute=0):
                base = base.replace(year=year + 1)
            return with_time(base), explicit_time
        except ValueError:
            pass

    # Reine Uhrzeit ohne Tagesbezug → heute (oder morgen, falls schon vorbei)
    if explicit_time and re.fullmatch(r"[\d:.\s,uhr]+", p):
        base = with_time(now)
        if base <= now:
            base = with_time(now + timedelta(days=1))
        return base, True

    # Fallback: dateparser
    import dateparser

    parsed = dateparser.parse(
        phrase,
        languages=["de"],
        settings={
            "RELATIVE_BASE": now,
            "PREFER_DATES_FROM": "future",
            "PREFER_DAY_OF_MONTH": "first",
            "TIMEZONE": "UTC",
        },
    )
    if not parsed:
        return None, False
    return with_time(parsed), explicit_time


def _default_hh_mm(default_time: str) -> tuple[int, int]:
    try:
        hh, mm = default_time.split(":")
        return int(hh), int(mm)
    except Exception:
        return 17, 0
