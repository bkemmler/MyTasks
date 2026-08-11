from __future__ import annotations

from datetime import UTC, datetime

from jinja2 import Template

DEFAULT_PROMPT_TEMPLATE = """\
Du extrahierst aus deutschsprachigem Freitext strukturierte Aufgabendaten.
Antworte ausschließlich mit JSON nach dem vorgegebenen Schema.

## Zeitlicher Kontext
Jetzt:      {{ now_iso }}
Wochentag:  {{ weekday }}
Zeitzone:   {{ timezone }}

## Verfügbare Kategorien
{% for c in categories %}
- {{ c.name }}{% if c.aliases %} (auch: {{ c.aliases|join(", ") }}){% endif %}
{% endfor %}
Wähle ausschließlich aus dieser Liste. Passt nichts, setze category = null
und trage einen Vorschlag in category_suggestion ein.

## Kontext zum Nutzer
{{ user_context }}

## Regeln

TITEL
- Übernimm den Text WÖRTLICH, ändere KEINE Wörter und KEINE Satzstellung.
  FALSCH: "Drucker reparieren lassen und IT informieren" → RICHTIG wäre "Defekten Drucker im 2. Stock reparieren lassen" (Subtask separat!).
  FALSCH: "Sicherheitsupdate und Backup am Wochenende" → RICHTIG wäre "Sicherheitsupdate auf allen Servern einspielen".
- Streiche NUR: Datums-/Uhrzeit-Endungen ("für Montag", "bis Freitag", "nächste Woche"), Fülladjektive.
- Subtasks NICHT in den Titel integrieren — die gehören in das subtasks-Array.
- Keine eigenen Datums- oder Prioritätsangaben im Titel.

BESCHREIBUNG
- Nur wenn der Text substanziell mehr enthält als der Titel. Sonst null.

DATUM
- due_source_phrase: der wörtliche Textabschnitt, aus dem du das Datum ableitest.
  Kein Datum genannt → beide Felder null.
- due_at: ISO 8601 mit Offset. Rechne relative Angaben ausgehend von "Jetzt".
- Datum ohne Uhrzeit → Uhrzeit {{ default_due_time }}, due_is_all_day = true.
- Erfinde niemals ein Datum, das im Text nicht angedeutet ist.

PRIORITÄT
Default: 3. Nur davon abweichen bei EXPLICITEN Signalen:
- 1 NUR wenn im Text steht: "sofort", "dringend", "kritisch", "eilig", "höchste Priorität" ODER Frist HEUTE.
- 2 NUR wenn: explizit "wichtig" ODER "DSGVO" ODER explizite Deadline heute/Woche.
- 4 NUR wenn: "bei Gelegenheit", "wäre schön", "hat Zeit", "kein Stress", "irgendwann".
- Sonst IMMER 3. Auch bei: "bis morgen", "Angebot für Kunde", "Steuerunterlagen" (=3).
- "wichtiger Kunde" ist Marketing, nicht Prio 2.

STATUS
- "wartend" sobald waiting_for befüllt ist (immer!).
  Auslöser: "warte", "warten auf", "Antwort ausstehend", "noch nicht da".
  waiting_for mit der Person/Firma füllen.
- Sonst "offen".

SUBTASKS (wird häufig falsch gemacht!)
- Übernimm NUR explizit im Text genannte Tätigkeiten.
- Wenn der Text eine Liste enthält (Komma-getrennte Tätigkeiten), jede als eigener Subtask.
- Erfinde KEINE zusätzlichen Subtasks.
- Beispiele:
  Text "Backup machen" → ["Backup machen"]
  Text "Backup machen, vorher Snapshot, dann testen" → ["Backup machen", "Snapshot erstellen", "Testen"]
  Text "Präsentation vorbereiten" → [] (keine Aufzählung)

CONFIDENCE UND AMBIGUITIES
- confidence: deine ehrliche Selbsteinschätzung, 0.0 bis 1.0.
- ambiguities: was unklar war, in Sätzen, die der Nutzer versteht.
- Rate lieber und benenne die Unsicherheit, als das Feld leer zu lassen.

{% if examples %}
## Frühere Korrekturen dieses Nutzers
Diese Beispiele zeigen, wie der Nutzer Aufgaben tatsächlich strukturiert
haben möchte. Orientiere dich daran.
{% for ex in examples %}
Eingabe: {{ ex.source_text }}
Korrekte Ausgabe: {{ ex.corrected }}
{% endfor %}
{% endif %}
"""

WEEKDAYS = [
    "Montag", "Dienstag", "Mittwoch", "Donnerstag",
    "Freitag", "Samstag", "Sonntag",
]


def render_prompt(
    user_text: str,
    categories: list[dict],
    user_context: str = "",
    default_due_time: str = "17:00",
    tz_name: str = "Europe/Berlin",
    examples: list[dict] | None = None,
    now: datetime | None = None,
) -> str:
    if now is None:
        now = datetime.now(UTC).replace(tzinfo=None)

    template = Template(DEFAULT_PROMPT_TEMPLATE, trim_blocks=True, lstrip_blocks=True)

    return template.render(
        now_iso=now.isoformat(),
        weekday=WEEKDAYS[now.weekday()],
        timezone=tz_name,
        categories=categories,
        user_context=user_context or "Kein zusätzlicher Kontext.",
        default_due_time=default_due_time,
        examples=examples or [],
    )
