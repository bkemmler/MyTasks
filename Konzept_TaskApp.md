# Konzept: LLM-gestützte Task-Anwendung

**Arbeitstitel:** *Kapture* (Platzhalter)
**Dokumentversion:** 1.0 · Entwurf zur Abstimmung
**Zweck:** Vorlage zur Implementierung. Technische Entscheidungen sind begründet, Alternativen benannt, offene Punkte in Kapitel 16 gesammelt.

---

## TL;DR

Eine selbst gehostete Task-Anwendung (FastAPI + SQLite + React im Debian-13-LXC, Port 5000), bei der ein lokales Ollama-Modell freien Text in strukturierte Tasks übersetzt. Der entscheidende Hebel für „einfacher als bisherige Apps" liegt nicht in der Feature-Liste, sondern in drei Designentscheidungen: **eine einzige Eingabezeile statt Formular**, **das LLM blockiert nie die Erfassung**, und **Korrekturen des Nutzers fließen als Few-Shot-Beispiele zurück in den Prompt**. Entwicklung in 8 Phasen, Android zuletzt, weil sie eine stabile API voraussetzt.

---

## 1. Zielbild und Leitprinzipien

### 1.1 Das eigentliche Problem

Bestehende Task-Apps (Todoist, MS To Do, Things, Obsidian Tasks) scheitern selten an fehlenden Features. Sie scheitern an der **Erfassungsreibung**: Wer einen Gedanken hat, muss ein Formular ausfüllen — Titel, Datum, Projekt, Priorität. Das kostet 15–30 Sekunden und mentale Umschaltung. Ergebnis: Tasks werden nicht erfasst, oder sie werden als unstrukturierte Titel-Fragmente erfasst („Müller wegen Angebot") und sind später wertlos.

Das LLM löst genau diese eine Reibung. Alles andere ist Beiwerk.

### 1.2 Fünf Leitprinzipien

Diese Prinzipien haben Vorrang vor Feature-Wünschen. Bei Zielkonflikten in der Implementierung entscheiden sie.

| # | Prinzip | Konsequenz in der Umsetzung |
|---|---------|------------------------------|
| **P1** | **Ein Feld, kein Formular.** Der Standardweg zur Task-Erstellung ist Text tippen + Enter. | Das manuelle Formular existiert, ist aber sekundär (hinter „Details"). |
| **P2** | **Das LLM blockiert nie.** Der Task erscheint sofort, die Felder füllen sich nach. | Asynchrone Verarbeitung mit optimistischem UI. Kein Spinner über der Liste. |
| **P3** | **Eingaben gehen nie verloren.** Fällt das LLM aus, bleibt der Rohtext als Task erhalten. | `source_text` ist Pflichtfeld, LLM-Fehler degradieren zu „Task mit Rohtext als Titel". |
| **P4** | **Raten ist erlaubt, Verstecken nicht.** Unsichere Extraktionen werden markiert, nicht stillschweigend gesetzt. | `needs_review`-Flag + sichtbare Kennzeichnung im UI, Ein-Klick-Bestätigung. |
| **P5** | **Das System lernt aus Korrekturen.** Jede Nutzerkorrektur ist Trainingssignal für den Prompt. | `llm_corrections`-Tabelle, Few-Shot-Injektion der letzten N Korrekturen. |

**P5 ist der Punkt, der diese App langfristig von generischen LLM-Wrappern unterscheidet.** Ein Prompt, der nach vier Wochen weiß, dass „MQC" die Kategorie „Mighty Quinn Consulting" bedeutet und dass „kurz anrufen" Priorität 3 heißt, ist deutlich mehr wert als ein besseres Basismodell.

### 1.3 Bewusste Nicht-Ziele (v1)

Explizit außerhalb des Umfangs, um Scope Creep zu vermeiden:

- Team-Funktionen: Tasks teilen, delegieren, kommentieren
- Dateianhänge
- Bidirektionale Kalender-Synchronisation (ICS-Export read-only ist Stretch Goal)
- iOS-App
- Zeiterfassung / Time Tracking
- Gantt, Kanban-Boards, Projektplanung

Diese sind nicht „schlecht", sondern verschoben. Das Datenmodell (Kapitel 5) hält Erweiterungspunkte offen, wo es billig ist.

---

## 2. Systemarchitektur

### 2.1 Komponentenübersicht

```
                    ┌───────────────────────────────┐
   Internet         │  VPS: Pangolin + Traefik      │
  ──────────────────►  TLS-Terminierung             │
                    │  Resource-Auth (SSO/PIN/Token)│
                    └──────────────┬────────────────┘
                                   │ WireGuard (Newt)
                    ┌──────────────▼────────────────┐
                    │  Heim-LAN / DMZ               │
                    │                               │
                    │  ┌─────────────────────────┐  │
                    │  │ LXC "tasks" (Debian 13) │  │
                    │  │  ├─ uvicorn :5000       │  │
                    │  │  │   ├─ REST API /api/v1│  │
                    │  │  │   ├─ SSE /events     │  │
                    │  │  │   └─ Static (React)  │  │
                    │  │  ├─ worker (systemd)    │  │
                    │  │  │   ├─ LLM-Jobs        │  │
                    │  │  │   └─ Scheduler/Mail  │  │
                    │  │  └─ SQLite (WAL) + FTS5 │  │
                    │  └───────────┬─────────────┘  │
                    │              │ HTTP           │
                    │  ┌───────────▼─────────────┐  │
                    │  │ LXC/VM "ollama" :11434  │  │
                    │  └─────────────────────────┘  │
                    │                               │
                    │  SMTP-Relay (extern/intern)   │
                    └───────────────────────────────┘

   Clients:  Browser (Desktop)  ·  Android 15 App
```

### 2.2 Prozesstrennung im LXC

Zwei getrennte systemd-Units, ein gemeinsames Verzeichnis und eine gemeinsame Datenbank:

| Unit | Aufgabe | Warum getrennt |
|------|---------|----------------|
| `tasks-api.service` | ASGI-Server, beantwortet HTTP-Requests | Muss immer schnell antworten |
| `tasks-worker.service` | LLM-Jobs, tägliche Mails, Wiederholungs-Tasks, Aufräumen | Lange Laufzeiten dürfen die API nicht blockieren; überlebt API-Neustarts |

Die Kopplung läuft über eine Job-Tabelle in SQLite (Polling im Sekundentakt), **nicht** über Redis/Celery. Begründung: Bei erwarteten 1–10 Nutzern ist externe Queue-Infrastruktur reiner Betriebsaufwand. Die Job-Tabelle ist zudem crash-sicher — ein LLM-Job überlebt einen Neustart, ein `BackgroundTask` im Prozess nicht.

**Konsequenz, die man kennen muss:** Die API läuft mit **einem** Worker-Prozess (async, kein Gunicorn-Prefork). Bei 1–10 Nutzern ist das um Größenordnungen ausreichend. Wer später horizontal skalieren will, muss auf PostgreSQL + echte Queue wechseln — das ist ein bewusst akzeptierter Umbau, kein Versehen.

---

## 3. Technologieentscheidungen

| Bereich | Empfehlung | Begründung | Alternative |
|---------|-----------|------------|-------------|
| **Backend** | Python 3.13 + FastAPI | Pydantic validiert LLM-JSON gegen dasselbe Schema, das Ollama als Grammatik bekommt — ein Schema, zwei Verwendungen. OpenAPI-Spec fällt automatisch an und erzeugt den Android-Client. | Node/NestJS (gleichwertig, aber Doppelnutzen des Schemas fehlt) |
| **ORM / Migration** | SQLAlchemy 2.x + Alembic | Migrationspfad zu PostgreSQL bleibt offen | Raw SQL (schneller, aber Migrationen von Hand) |
| **Datenbank** | SQLite (WAL) + FTS5 | FTS5 löst „Suche über alle Felder" nativ und exzellent. Backup = eine Datei. Bei dieser Nutzerzahl kein Nachteil. | PostgreSQL — nötig ab ca. 50 Nutzern oder bei mehreren API-Prozessen |
| **Frontend** | React 19 + TypeScript + Vite + Tailwind | Build erzeugt statische Dateien, die FastAPI ausliefert → **eine Origin, kein CORS, kein zweiter Reverse-Proxy** | SvelteKit, Vue |
| **State/Data** | TanStack Query | Optimistische Updates und Cache-Invalidierung sind hier der Kern (P2) | Redux Toolkit Query |
| **Auth** | Argon2id + JWT (Access) + rotierendes Refresh-Token | Siehe Kapitel 8 | Sessions in DB (einfacher, aber schlechter für Android) |
| **LLM** | Ollama, Structured Outputs via `format` (JSON Schema) | Erzwingt syntaktisch valides JSON auf Grammatikebene — eliminiert die häufigste Fehlerklasse vollständig | llama.cpp direkt, vLLM |
| **Android** | Kotlin + Jetpack Compose, minSdk 29, targetSdk 35 | Offline-Fähigkeit, lokale Erinnerungen, Biometrie brauchen nativen Zugriff | **PWA** — siehe Abwägung unten |
| **Android HTTP** | Ktor Client oder Retrofit + kotlinx.serialization | Beide unproblematisch | — |
| **Android lokal** | Room (Cache) + DataStore (Settings) + EncryptedSharedPreferences (Credentials) | Standard-Stack | — |
| **Scheduler** | APScheduler im Worker, Jobstore in SQLite | Pro-Nutzer-Sendezeiten mit Zeitzonen; überlebt Neustart | systemd-Timer (einfacher, aber unflexibel bei Nutzerzeitzonen) |

### 3.1 Abwägung: Native Android-App vs. PWA

Ehrliche Einordnung, weil hier der größte Aufwandsposten liegt: **Die native App kostet realistisch 40–60 % des Gesamtaufwands.** Eine PWA (installierbar, Web Push, Service-Worker-Cache) deckt etwa 80 % des Nutzens zu etwa 15 % des Aufwands ab.

Was die native App wirklich zusätzlich liefert:

- Zuverlässige lokale Erinnerungen via `AlarmManager` (Web-Notifications sind unter Android bei geschlossener App unzuverlässig)
- Biometrische Entsperrung
- Share-Target aus beliebigen Apps („Text teilen → Task") — funktioniert bei PWA eingeschränkt
- Robustes Offline-Verhalten mit Outbox
- Sprachaufnahme mit lokaler Transkription (siehe Kapitel 6.6)

**Empfehlung:** Native App, aber **erst nach Phase 6** und erst, wenn die PWA im Alltag getestet ist. Wenn sich zeigt, dass die PWA reicht, spart das mehrere Wochen. Der Server ist in beiden Fällen identisch — die Entscheidung lässt sich also verzögern, ohne etwas zu blockieren.

---

## 4. Ablauf: Vom Text zum Task

```
 [Nutzer tippt]  "Angebot Fa. Müller bis Freitag 16 Uhr fertigstellen,
                  vorher noch Rücksprache mit Sabine, wichtig"
        │
        │  POST /api/v1/tasks/capture   {text: "..."}
        ▼
 ┌──────────────────────────────────────────────────┐
 │ API (< 50 ms)                                     │
 │  1. Task anlegen: title = erste 80 Zeichen        │
 │     source_text = Rohtext, llm_state = "pending"  │
 │  2. Job in llm_jobs einreihen                     │
 │  3. Task-Objekt zurückgeben  ← Nutzer sieht ihn   │
 └───────────────────┬──────────────────────────────┘
                     │
                     ▼
 ┌──────────────────────────────────────────────────┐
 │ Worker (2–15 s)                                   │
 │  4. Prompt bauen: Template + Kontext + Few-Shots  │
 │  5. Ollama /api/chat mit format=<JSON Schema>     │
 │  6. Pydantic-Validierung                          │
 │     └─ Fehler → 1× Repair-Retry mit Fehlertext    │
 │  7. Normalisierung (Datum, Kategorie, Priorität)  │
 │  8. Plausibilitätsprüfung → needs_review?         │
 │  9. Task aktualisieren, llm_state = "done"        │
 │ 10. SSE-Event an verbundene Clients               │
 └───────────────────┬──────────────────────────────┘
                     │
                     ▼
        [Task in der Liste füllt sich sichtbar auf]
        Titel: "Angebot Fa. Müller fertigstellen"
        Fällig: Fr, 14.08.2026 16:00
        Kategorie: Müller GmbH · Priorität: P1
        Subtask: "Rücksprache mit Sabine"  ⚠ zur Prüfung
```

**Wichtig bei Schritt 8:** Die Prüfung ist kein Blocker. Der Task ist gespeichert und nutzbar; `needs_review` erzeugt lediglich einen dezenten Marker mit Ein-Klick-Bestätigung.

---

## 5. Datenmodell

### 5.1 Bewertung der gewünschten Felder

Zu den angefragten Feldern zwei Anmerkungen, bevor das Schema kommt:

**`% abgeschlossen` — kritisch zu sehen.** Dieses Feld ist in der Praxis fast immer totes Gewicht. Niemand pflegt „37 %". Es wird beim Anlegen auf 0 gesetzt und beim Erledigen auf 100 gesprungen. Empfehlung: Feld behalten, aber **automatisch aus dem Subtask-Fortschritt berechnen**, wenn Subtasks existieren, und nur bei Tasks ohne Subtasks manuell editierbar machen. Damit hat es zum ersten Mal einen echten Informationswert.

**`Status` — zwei Werte fehlen.** „offen / in Bearbeitung / erledigt" verliert zwei praktisch wichtige Zustände: `wartend` (auf Zulieferung Dritter — sehr häufig im Consulting und der Grund, warum Tasks „hängen") und `abgebrochen` (unterscheidet sich statistisch fundamental von „erledigt"). Beide sind billig aufzunehmen und später teuer nachzurüsten.

### 5.2 Ergänzungsvorschläge

| Feld | Warum | Priorität |
|------|-------|-----------|
| `source_text` | Rohtext der Eingabe. Ermöglicht Reprocessing bei besserem Prompt, Debugging, und rettet Daten bei LLM-Fehlern (P3). | **Pflicht** |
| `updated_at`, `deleted_at` | Ohne beide ist Android-Delta-Sync unmöglich. `deleted_at` = Tombstone. | **Pflicht** |
| `completed_at` | Reports, Statistiken, „was habe ich diese Woche geschafft" | **Pflicht** |
| `needs_review`, `llm_confidence` | Trägt P4. Ohne das rät das LLM still und falsch. | **Pflicht** |
| `subtasks` (Tabelle) | Größter LLM-Mehrwert nach der Extraktion: „Präsentation vorbereiten" → 5 Schritte. Speist `progress_percent`. | Hoch |
| `tags` (n:m) | Orthogonal zur Kategorie. LLM extrahiert sie gut, Filterung wird mächtig. | Hoch |
| `recurrence_rule` (RFC 5545) | „jeden Montag Statusbericht" — LLM parst das zuverlässig, spart viel manuelle Arbeit | Hoch |
| `start_at` (Defer-Datum) | GTD-Prinzip: Task erst ab Datum X anzeigen. Hält die Liste kurz — direkter Beitrag zu „einfacher". | Hoch |
| `estimated_minutes` | LLM schätzt grob; ermöglicht Tagesplanung („heute 4 h Tasks bei 6 h Zeit") | Mittel |
| `waiting_for` | Freitext-Person bei Status `wartend`. Grundlage für „woran hängt es?"-Report. | Mittel |
| `reminders` (Tabelle) | Mehrere Erinnerungen pro Task; Basis für Android-Benachrichtigungen | Mittel |
| `url`, `location` | Häufig im Quelltext enthalten, billig zu extrahieren | Niedrig |
| `parent_task_id` | Hierarchie über Subtasks hinaus | Niedrig |
| `sort_order` | Manuelle Reihenfolge innerhalb einer Ansicht | Niedrig |
| `prompt_version`, `llm_model` | Pro Task speichern. Ohne das kann man Prompt-Änderungen nicht bewerten. | Mittel |

### 5.3 Schema (SQLite-DDL, gekürzt auf das Wesentliche)

```sql
-- ── Nutzer & Rechte ───────────────────────────────────────────────
CREATE TABLE users (
    id                INTEGER PRIMARY KEY,
    username          TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    email             TEXT,                       -- für tägliche Zusammenfassung
    display_name      TEXT,
    password_hash     TEXT    NOT NULL,           -- Argon2id
    is_admin          INTEGER NOT NULL DEFAULT 0,
    is_active         INTEGER NOT NULL DEFAULT 1,
    timezone          TEXT    NOT NULL DEFAULT 'Europe/Berlin',
    locale            TEXT    NOT NULL DEFAULT 'de-DE',
    daily_summary_enabled INTEGER NOT NULL DEFAULT 0,
    daily_summary_time    TEXT DEFAULT '07:00',   -- lokale Zeit des Nutzers
    default_due_time      TEXT DEFAULT '17:00',   -- wenn LLM Datum ohne Uhrzeit liefert
    must_change_password  INTEGER NOT NULL DEFAULT 0,
    failed_login_count    INTEGER NOT NULL DEFAULT 0,
    locked_until      TEXT,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);

CREATE TABLE refresh_tokens (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash    TEXT    NOT NULL UNIQUE,   -- SHA-256, nie Klartext
    device_label  TEXT,                      -- "Pixel 9", "Firefox Desktop"
    issued_at     TEXT    NOT NULL,
    expires_at    TEXT    NOT NULL,
    revoked_at    TEXT,
    replaced_by   INTEGER REFERENCES refresh_tokens(id)  -- Rotationskette
);

-- ── Kategorien (pro Nutzer verwaltet, verhindert Kategorie-Wildwuchs) ──
CREATE TABLE categories (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    color       TEXT,                        -- Hex, UI-Akzent
    aliases     TEXT,                        -- JSON-Array: ["MQC","Mighty Quinn"]
    is_default  INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, name)
);

-- ── Tasks ─────────────────────────────────────────────────────────
CREATE TABLE tasks (
    id                INTEGER PRIMARY KEY,
    uuid              TEXT    NOT NULL UNIQUE,   -- clientseitig erzeugbar → Offline-Anlage
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    title             TEXT    NOT NULL,
    description       TEXT,
    source_text       TEXT,                      -- Original-Eingabe (P3)

    due_at            TEXT,                      -- ISO 8601 UTC
    due_is_all_day    INTEGER NOT NULL DEFAULT 0,
    start_at          TEXT,                      -- Defer-Datum
    completed_at      TEXT,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    deleted_at        TEXT,                      -- Soft Delete / Tombstone

    category_id       INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    priority          INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 4),
    status            TEXT    NOT NULL DEFAULT 'offen'
                        CHECK (status IN ('offen','in_bearbeitung','wartend',
                                          'erledigt','abgebrochen')),
    progress_percent  INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),

    estimated_minutes INTEGER,
    waiting_for       TEXT,
    location          TEXT,
    url               TEXT,
    recurrence_rule   TEXT,                      -- RFC 5545 RRULE
    recurrence_parent_id INTEGER REFERENCES tasks(id),
    parent_task_id    INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    sort_order        REAL    NOT NULL DEFAULT 0,

    -- LLM-Metadaten
    llm_state         TEXT    NOT NULL DEFAULT 'none'
                        CHECK (llm_state IN ('none','pending','done','failed')),
    llm_confidence    REAL,
    llm_model         TEXT,
    prompt_version    INTEGER,
    needs_review      INTEGER NOT NULL DEFAULT 0,
    review_notes      TEXT                       -- JSON-Array der Mehrdeutigkeiten
);

CREATE INDEX idx_tasks_user_active   ON tasks(user_id, status, due_at)
                                     WHERE deleted_at IS NULL;
CREATE INDEX idx_tasks_user_updated  ON tasks(user_id, updated_at);  -- Delta-Sync
CREATE INDEX idx_tasks_user_category ON tasks(user_id, category_id);

CREATE TABLE subtasks (
    id           INTEGER PRIMARY KEY,
    task_id      INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    title        TEXT    NOT NULL,
    is_done      INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT
);

CREATE TABLE tags (
    id      INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name    TEXT    NOT NULL,
    UNIQUE(user_id, name)
);
CREATE TABLE task_tags (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
);

CREATE TABLE reminders (
    id         INTEGER PRIMARY KEY,
    task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    remind_at  TEXT    NOT NULL,
    sent_at    TEXT,
    channel    TEXT    NOT NULL DEFAULT 'push'   -- push | email
);

-- ── Volltextsuche über alle relevanten Felder ─────────────────────
CREATE VIRTUAL TABLE tasks_fts USING fts5(
    title, description, source_text, waiting_for, location,
    content='tasks', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
-- + Trigger AFTER INSERT/UPDATE/DELETE ON tasks zur Synchronisation

-- ── LLM-Infrastruktur ─────────────────────────────────────────────
CREATE TABLE llm_jobs (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id       INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    job_type      TEXT    NOT NULL,   -- capture | reparse | daily_summary | subtask_gen
    payload       TEXT    NOT NULL,   -- JSON
    state         TEXT    NOT NULL DEFAULT 'queued'
                    CHECK (state IN ('queued','running','done','failed')),
    attempts      INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    created_at    TEXT    NOT NULL,
    started_at    TEXT,
    finished_at   TEXT,
    duration_ms   INTEGER
);
CREATE INDEX idx_llm_jobs_queue ON llm_jobs(state, created_at);

-- Trägt P5: das Lernsignal
CREATE TABLE llm_corrections (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id       INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    source_text   TEXT    NOT NULL,
    llm_output    TEXT    NOT NULL,   -- JSON, was das LLM lieferte
    corrected     TEXT    NOT NULL,   -- JSON, was der Nutzer daraus machte
    changed_fields TEXT   NOT NULL,   -- JSON-Array: ["due_at","category"]
    use_as_example INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL
);

CREATE TABLE prompts (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,     -- capture | daily_summary | subtask_gen
    version     INTEGER NOT NULL,
    template    TEXT    NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 0,
    notes       TEXT,
    created_at  TEXT    NOT NULL,
    created_by  INTEGER REFERENCES users(id),
    UNIQUE(name, version)
);

CREATE TABLE app_config (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    is_secret   INTEGER NOT NULL DEFAULT 0,  -- verschlüsselt abgelegt
    updated_at  TEXT NOT NULL,
    updated_by  INTEGER REFERENCES users(id)
);

CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY,
    ts          TEXT    NOT NULL,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor_ip    TEXT,
    action      TEXT    NOT NULL,   -- login.success, user.create, config.update, ...
    target      TEXT,
    detail      TEXT                -- JSON, ohne Secrets
);
```

### 5.4 Mandantentrennung — die Regel, die nicht verhandelbar ist

„Jeder Nutzer sieht nur seine Daten" ist die Anforderung, bei der ein einziger vergessener Filter zum Datenschutzvorfall wird. Rein disziplinbasiert ist das nicht haltbar.

**Technische Absicherung, dreistufig:**

1. **Repository-Layer:** Jede Datenzugriffsfunktion nimmt `user_id` als **ersten Positionsparameter** — nicht als optionales Keyword. Vergisst man ihn, schlägt der Aufruf fehl, nicht die Prüfung.
2. **Kein direkter Session-Zugriff aus Routern.** Router bekommen ein `UserScopedRepository`, das im Konstruktor bereits an den authentifizierten Nutzer gebunden ist.
3. **Automatisierter Test:** Ein Test, der für jeden schreibenden und lesenden Endpunkt prüft, dass Nutzer B mit gültigem Token nicht auf Ressourcen von Nutzer A zugreifen kann (erwartet: **404**, nicht 403 — 403 verrät die Existenz der Ressource). Dieser Test wird generisch über die OpenAPI-Route-Liste gebaut, damit neue Endpunkte automatisch mit abgedeckt sind.

---

## 6. Die LLM-Pipeline

Dies ist der technisch anspruchsvollste und risikoreichste Teil. Er gehört deshalb früh in die Entwicklung (Phase 2), nicht ans Ende.

### 6.1 Strukturierte Ausgabe erzwingen

Ollama unterstützt seit Version 0.5 den Parameter `format` mit einem JSON Schema. Das Schema wird in eine Grammatik übersetzt, die der Decoder **erzwingt** — syntaktisch ungültiges JSON ist damit unmöglich. Das eliminiert die mit Abstand häufigste Fehlerklasse.

```python
response = await client.post("/api/chat", json={
    "model": config.ollama_model,
    "messages": [
        {"role": "system", "content": rendered_system_prompt},
        {"role": "user",   "content": user_text},
    ],
    "format": TaskExtraction.model_json_schema(),  # Pydantic → JSON Schema
    "stream": False,
    "keep_alive": "30m",        # Modell im RAM halten → 5–10 s Latenz gespart
    "options": {
        "temperature": 0.1,     # Extraktion, keine Kreativität
        "num_ctx": 8192,
        "num_predict": 1024,
    },
})
```

**Zwei Fallstricke, die viel Zeit kosten können:**

- **Alle Felder gehören in `required`.** Grammatik-constrained Decoding ist bei optionalen Properties deutlich unzuverlässiger. Optionalität wird stattdessen über Union-Typen abgebildet: `"type": ["string", "null"]`. Also nicht `Optional[str]` weglassen, sondern explizit `str | None` mit Eintrag in `required`.
- **`keep_alive` setzen.** Ohne das entlädt Ollama das Modell nach 5 Minuten Inaktivität und der nächste Task wartet 5–15 Sekunden auf das Nachladen. Das zerstört den Eindruck von Geschwindigkeit.

### 6.2 Extraktionsschema

```python
class TaskExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title:              str          # prägnant, Imperativ, max. 80 Zeichen
    description:        str | None   # nur wenn substanziell mehr als der Titel
    due_at:             str | None   # ISO 8601 mit Offset
    due_source_phrase:  str | None   # exakter Textteil, aus dem due_at abgeleitet wurde
    due_is_all_day:     bool
    start_at:           str | None
    category:           str | None   # aus vorgegebener Liste ODER null
    category_suggestion: str | None  # nur wenn nichts passt
    priority:           int          # 1 (dringend) … 4 (irgendwann)
    status:             Literal["offen","in_bearbeitung","wartend","erledigt"]
    waiting_for:        str | None
    tags:               list[str]         # max. 5
    subtasks:           list[str]         # max. 8, nur bei klarer Mehrschrittigkeit
    estimated_minutes:  int | None
    location:           str | None
    url:                str | None
    recurrence_rule:    str | None   # RFC 5545 RRULE
    confidence:         float        # 0.0–1.0, Selbsteinschätzung
    ambiguities:        list[str]    # was unklar war, in Nutzersprache
```

Das Feld **`due_source_phrase` ist der wichtigste Einzelbaustein** dieses Schemas. Es macht die Datumsableitung überprüfbar (siehe 6.4).

### 6.3 Prompt-Template

Der Prompt ist gemäß Anforderung konfigurierbar. Er wird als Jinja2-Template in der `prompts`-Tabelle gehalten und versioniert. Platzhalter:

| Platzhalter | Inhalt |
|-------------|--------|
| `{{ now_iso }}` | `2026-08-08T14:32:00+02:00` |
| `{{ weekday }}` | `Samstag` |
| `{{ timezone }}` | `Europe/Berlin` |
| `{{ categories }}` | Kategorien des Nutzers inkl. Aliase |
| `{{ default_due_time }}` | `17:00` |
| `{{ examples }}` | Letzte N Korrekturen als Few-Shot-Paare (P5) |
| `{{ user_context }}` | Freier Kontexttext pro Nutzer (z. B. „arbeitet bei MQC, Kunden: …") |

Ausgangsversion des Templates siehe Anhang A.

### 6.4 Datumsauflösung — der kritische Punkt

**LLMs rechnen schlecht mit Kalendern.** „Nächsten Dienstag" produziert selbst bei starken Modellen regelmäßig Datumsfehler, besonders über Monatsgrenzen und in Wochen mit Feiertagen. Das ist keine Prompt-Schwäche, sondern eine bekannte strukturelle Schwäche.

**Zweistufiges Verfahren:**

1. **LLM liefert beides:** das berechnete `due_at` **und** die zugrunde liegende Textphrase `due_source_phrase` (z. B. `"bis Freitag 16 Uhr"`).
2. **Server prüft deterministisch nach:** Die Phrase wird zusätzlich mit einem regelbasierten Parser (`dateparser` mit `languages=['de']`, `RELATIVE_BASE=now`, `PREFER_DATES_FROM='future'`) aufgelöst.

Entscheidungsregeln:

| Fall | Verhalten |
|------|-----------|
| Beide Ergebnisse stimmen überein (± 1 h) | Übernehmen, `needs_review = 0` |
| Abweichung > 1 Tag | **Parser-Ergebnis** übernehmen, `needs_review = 1` |
| Parser liefert nichts, LLM schon | LLM-Wert übernehmen, `needs_review = 1` |
| Datum liegt in der Vergangenheit | Übernehmen, `needs_review = 1` (kann legitim sein: „hätte gestern fertig sein müssen") |
| Datum > 2 Jahre in der Zukunft | `needs_review = 1` — typisches Jahreszahl-Halluzinationsmuster |

**Uhrzeit-Default:** Wenn ein Datum ohne Uhrzeit erkannt wird, setzt der Server `default_due_time` des Nutzers und `due_is_all_day = 1`. Das LLM soll hier **nicht** raten, sondern `null` liefern.

Der Aufwand für diese zweite Stufe ist überschaubar (ca. ein Tag) und verhindert die Fehlerklasse, die das Vertrauen in die App am schnellsten zerstört: Termine, die stillschweigend auf dem falschen Tag landen.

### 6.5 Validierung, Reparatur, Fallback

```
Ollama-Antwort
   ├─ Pydantic-Validierung
   │    ├─ OK   → Normalisierung
   │    └─ Fehler → 1× Retry mit angehängtem Fehlertext (max. 2 Versuche gesamt)
   │                 └─ weiterhin Fehler → llm_state='failed'
   │                                        Task behält Rohtext-Titel (P3)
   │                                        needs_review = 1
   └─ Normalisierung
        ├─ Kategorie-Matching (exakt → Alias → fuzzy ≥ 0.85 → null + Vorschlag)
        ├─ Datumsauflösung (6.4)
        ├─ Priorität clampen auf 1–4
        ├─ Tags: lowercase, trimmen, deduplizieren, max. 5
        ├─ Titel: max. 200 Zeichen, Rest → description
        └─ RRULE gegen dateutil.rrule validieren, sonst verwerfen
```

**Timeouts:** Ollama-Request 90 s hart. Bei Timeout → `failed`, Task bleibt mit Rohtext bestehen. Ein Wiederholen-Button im UI setzt einen neuen Job ab.

### 6.6 Weitere LLM-Funktionen (nach Nutzen sortiert)

| Funktion | Nutzen | Aufwand | Phase |
|----------|--------|---------|-------|
| **Task aus Freitext** | Kernfunktion | — | 2 |
| **Mehrere Tasks aus einem Text** | Meeting-Notizen einfügen → 5 Tasks. Sehr hoher Alltagsnutzen. Schema wird zu `{tasks: [...]}`, Erkennung über Heuristik (> 200 Zeichen oder Aufzählungszeichen) oder Nutzer-Umschalter. | Klein | 2 |
| **Tägliche Zusammenfassung** | Nicht nur Liste, sondern Priorisierungsvorschlag in Prosa („Freitag ist eng — Angebot Müller zuerst") | Klein | 4 |
| **Subtask-Generierung auf Abruf** | Button „Aufschlüsseln" bei vagen Tasks | Klein | 7 |
| **Task-Update per Sprache/Text** | „Müller-Angebot auf Montag schieben" → PATCH. Bestehende Tasks als Kontext, Ausgabe `{task_uuid, changes}`. | Mittel | 7 |
| **Duplikatserkennung** | Vor dem Anlegen die 20 ähnlichsten offenen Tasks prüfen; bei Treffer „Meintest du…?" | Mittel | 7 |
| **Spracherfassung** | Aufnahme → `faster-whisper` (small/medium, lokal) → Text → normale Pipeline. **Für mobile Erfassung der mit Abstand größte UX-Sprung.** Braucht zusätzliche Ressourcen. | Mittel | Optional |
| **Semantische Suche** | Embeddings (`nomic-embed-text`) + sqlite-vec neben FTS5 | Mittel | Optional |

### 6.7 Modellwahl und Evaluation

Für deutschsprachige Extraktion mit erzwungenem JSON sind Modelle ab etwa 7–8 B Parametern brauchbar, ab 14 B deutlich zuverlässiger — besonders bei der Kategoriezuordnung und beim Erkennen von Mehrdeutigkeiten. Konkrete Modellempfehlungen spare ich mir bewusst: die Landschaft ändert sich zu schnell, und die Antwort hängt stark von der verfügbaren Hardware ab (siehe offene Frage F1).

**Stattdessen der wichtigere Rat: Bauen Sie ein Eval-Set, bevor Sie ein Modell auswählen.**

- 40–60 deutsche Beispielsätze aus dem eigenen Alltag, mit handgeschriebenem Soll-JSON
- Abdeckung: relative Daten, Wochentage, Uhrzeiten, Kategorien mit Abkürzungen, mehrere Tasks pro Text, Wiederholungen, bewusst mehrdeutige Fälle
- Metriken pro Feld: Exact Match bei `category`/`priority`/`status`, Datumsabweichung in Minuten bei `due_at`, manuelle 1–5-Bewertung bei `title`
- CLI-Skript `evaluate.py --model X --prompt-version Y`, Ergebnisse als CSV

Das kostet einen Tag und macht sowohl Modell- als auch Promptvergleiche objektiv statt gefühlt. Ohne Eval-Set optimiert man den Prompt im Blindflug — man merkt Verschlechterungen erst Wochen später im Alltag.

---

## 7. API-Spezifikation

Basis: `/api/v1`. Alle Antworten JSON. Fehler nach RFC 7807 (`application/problem+json`).

### 7.1 Endpunkte

**Authentifizierung**

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| POST | `/auth/login` | `{username, password, device_label?}` → Access + Refresh |
| POST | `/auth/refresh` | Rotation: altes Token wird invalidiert |
| POST | `/auth/logout` | Refresh-Token widerrufen |
| GET | `/auth/me` | Eigenes Profil inkl. Rechten |
| PATCH | `/auth/me` | Zeitzone, Standard-Fälligkeitszeit, Mail-Einstellungen |
| POST | `/auth/me/password` | Eigenes Passwort ändern (alt + neu) |

**Tasks**

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| GET | `/tasks` | Filter: `status`, `category_id`, `priority`, `due_before`, `due_after`, `tag`, `needs_review`, `include_completed`; Sortierung: `sort=due_at,-priority`; Cursor-Pagination |
| POST | `/tasks` | Manuelle Anlage (ohne LLM) |
| **POST** | **`/tasks/capture`** | **`{text, mode: "single"\|"auto"}` → Task(s) sofort mit `llm_state="pending"`** |
| GET | `/tasks/{uuid}` | Einzelabruf |
| PATCH | `/tasks/{uuid}` | Teilaktualisierung; protokolliert Korrektur in `llm_corrections`, wenn LLM-Werte geändert werden |
| DELETE | `/tasks/{uuid}` | Soft Delete |
| POST | `/tasks/{uuid}/complete` | Erledigen; erzeugt bei RRULE die nächste Instanz |
| POST | `/tasks/{uuid}/reparse` | Erneute LLM-Verarbeitung des `source_text` |
| POST | `/tasks/{uuid}/confirm-review` | `needs_review = 0` |
| POST | `/tasks/{uuid}/subtasks` | Subtask anlegen |
| POST | `/tasks/{uuid}/generate-subtasks` | LLM-Aufschlüsselung |
| GET | `/tasks/search?q=` | FTS5 über alle Felder, mit Snippet-Highlighting |
| GET | `/tasks/export?format=csv\|json` | Datenexport (DSGVO-Portabilität) |

**Stammdaten & Meta**

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| GET/POST/PATCH/DELETE | `/categories` | Kategorien inkl. Aliase |
| GET | `/tags` | Tags mit Nutzungshäufigkeit |
| GET | `/views` | Gespeicherte Ansichten |
| GET | `/stats` | Kennzahlen für Reports |
| GET | `/version` | `{app, api, db_schema, git_sha, built_at, min_android}` |
| GET | `/health` | Liveness/Readiness inkl. Ollama- und SMTP-Status |
| GET | `/events` | **SSE-Stream**: `task.updated`, `task.created`, `llm.done`, `llm.failed` |

**Synchronisation (Android)**

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| GET | `/sync?since=<ISO>&limit=500` | Delta: geänderte Tasks + Tombstones + Server-Zeitstempel |
| POST | `/sync` | Batch-Upsert aus der Outbox; pro Eintrag `{uuid, updated_at, fields}` |

**Administration** (nur `is_admin`)

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| GET/POST/PATCH/DELETE | `/admin/users` | Nutzerverwaltung; DELETE mit `?hard=true` für echte Löschung |
| POST | `/admin/users/{id}/reset-password` | Setzt `must_change_password` |
| GET/PUT | `/admin/config` | Ollama-URL, Modell, SMTP, globale Defaults |
| POST | `/admin/config/llm/test` | Verbindungstest + Modellliste von Ollama |
| POST | `/admin/config/smtp/test` | Testmail an angegebene Adresse |
| GET/POST | `/admin/prompts` | Prompt-Versionen; POST erzeugt neue Version |
| POST | `/admin/prompts/{id}/activate` | Aktivschaltung |
| **POST** | **`/admin/prompts/{id}/test`** | **`{text}` → gerenderter Prompt + rohes LLM-JSON, ohne Task anzulegen** |
| GET | `/admin/jobs` | LLM-Job-Historie mit Laufzeiten und Fehlern |
| GET | `/admin/audit` | Audit-Log |

Der Prompt-Test-Endpunkt ist beim Prompt-Tuning das wichtigste Werkzeug — er erlaubt eine Iterationsschleife von Sekunden statt Minuten.

### 7.2 Fehlerkonvention

```json
{
  "type": "https://tasks.example.com/errors/validation",
  "title": "Ungültige Eingabe",
  "status": 422,
  "detail": "due_at liegt vor created_at",
  "errors": { "due_at": ["muss in der Zukunft liegen"] }
}
```

Zugriff auf fremde Ressourcen liefert **404**, nicht 403 — 403 wäre ein Existenz-Orakel.

---

## 8. Authentifizierung und Autorisierung

### 8.1 Zwei-Schichten-Modell

Es gibt zwei unabhängige Auth-Ebenen, die nicht verwechselt werden dürfen:

- **Ebene 1 — Pangolin (Perimeter):** Entscheidet, ob ein Request überhaupt den LXC erreicht. Kennt die Anwendungsnutzer nicht.
- **Ebene 2 — Anwendung:** Entscheidet, *wer* der Nutzer ist und welche Daten er sieht.

Die Anwendung **darf sich niemals auf Ebene 1 verlassen**. Sie muss auch dann sicher sein, wenn jemand direkt im LAN auf Port 5000 zugreift. Ebene 1 ist Tiefenverteidigung, kein Ersatz.

### 8.2 Anwendungsauth

- **Passwörter:** Argon2id (`argon2-cffi`), Parameter: `time_cost=3`, `memory_cost=65536` (64 MiB), `parallelism=4`. Mindestlänge 12 Zeichen, Abgleich gegen eine Liste häufiger Passwörter.
- **Access-Token:** JWT, 15 Minuten Gültigkeit, HS256 mit Server-Secret. Claims: `sub`, `is_admin`, `exp`, `jti`.
- **Refresh-Token:** 256 Bit Zufall, **nur als SHA-256-Hash gespeichert**, 30 Tage, **rotierend**. Wird ein bereits ersetztes Token erneut vorgelegt, deutet das auf Diebstahl hin → gesamte Token-Familie des Nutzers widerrufen.
- **Ablage im Browser:** Access-Token nur im JS-Speicher (nicht `localStorage`), Refresh-Token in einem `httpOnly; Secure; SameSite=Strict`-Cookie. Damit ist ein XSS-Fund nicht automatisch ein dauerhafter Kontoverlust.
- **Ablage in Android:** Refresh-Token in `EncryptedSharedPreferences` (Keystore-gebunden), optional zusätzlich hinter `BiometricPrompt`.
- **Rate Limiting:** 5 Login-Versuche pro Minute und IP, 10 pro Stunde und Konto; danach exponentielles Backoff und Sperre über `locked_until`. Antwortzeit bei Fehlschlag konstant halten (kein User-Enumeration-Orakel).
- **Keine Selbstregistrierung.** Nutzer entstehen ausschließlich über `/admin/users`.

### 8.3 Pangolin-Integration

Für den Browser ist die Sache unkompliziert: Resource mit Pincode- oder SSO-Schutz, der Nutzer authentifiziert sich einmal bei Pangolin, danach greift die App-Anmeldung.

Für die Android-App ist es das nicht — und dies ist der Punkt, der bei der Planung am ehesten unterschätzt wird. Pangolin bietet mehrere Verfahren zum Ressourcenschutz. <cite index="15-1">Resources können mit einem gemeinsamen Passwort oder mit einem numerischen PIN-Code geschützt werden, wobei beide Verfahren eine ressourcenspezifische Session unabhängig von der Nutzerauthentifizierung erzeugen; zusätzlich unterstützen Resources programmatischen Zugriff über Access Tokens, die per HTTP-Header oder Query-Parameter übergeben werden können.</cite> Der PIN-Flow ist browserzentriert: Er erwartet ein HTML-Formular und setzt anschließend ein Session-Cookie. Ein nativer REST-Client kann das nicht ohne WebView nachbilden.

**Drei Optionen, bewertet:**

| Option | Verfahren | Bewertung |
|--------|-----------|-----------|
| **A — Access-Token-Header** *(Empfehlung)* | Die App sendet bei jedem Request die Header `P-Access-Token-Id` und `P-Access-Token` aus einem Pangolin-Share-Link. | Etabliertes Muster; wird von der Community genau für diesen Fall (native Apps hinter Pangolin, z. B. Immich) eingesetzt. <cite index="4-1">Pangolin 1.21 ergänzt zudem optionale Session-Persistenz für Access Tokens, sodass diese nicht bei jedem Request mitgesendet werden müssen, sowie die Möglichkeit, ein Access Token einem bestimmten Nutzerkonto zuzuordnen.</cite> |
| **B — Bypass-Rule für `/api/*`** | Pfadregel, die den API-Pfad an der Pangolin-Auth vorbeiführt; Schutz allein durch JWT. | Funktional am einfachsten, aber Ebene 1 entfällt für genau den Pfad, der die Daten führt. Zudem <cite index="11-1">gibt es einen dokumentierten Fehlerbericht, wonach pfadbasierte Bypass-Regeln bei geschützten Resources für unauthentifizierte Nutzer nicht wie erwartet greifen — angemeldete Nutzer mit gültiger Session sind davon nicht betroffen.</cite> Vor Einsatz zwingend gegen die eingesetzte Version testen. |
| **C — WebView-Vorschaltung** | App öffnet WebView, Nutzer gibt PIN ein, Cookie wird in den OkHttp-CookieJar übernommen. | Entspricht der Anforderung „Passcode über Pangolin" am wörtlichsten, ist aber die fragilste Variante: Cookie-Ablauf mitten in einer Sync-Operation ist schwer sauber zu behandeln. |

**Empfehlung: Option A**, kombiniert mit einem PIN-geschützten Zugang für den Browser. Der Passcode-Aspekt der ursprünglichen Anforderung wird dann in der App als **lokale App-PIN oder Biometrie** umgesetzt (Entsperren beim Start), was funktional dasselbe Sicherheitsziel erfüllt und deutlich robuster ist.

> **Vorbehalt:** Pangolin entwickelt sich schnell und die Dokumentation weist selbst auf mögliche Breaking Changes zwischen Versionen hin. Diese Empfehlung sollte in Phase 5 in einem 1–2-stündigen Praxistest gegen die tatsächlich eingesetzte Version verifiziert werden, **bevor** die Android-Entwicklung beginnt. Ein Fehlschlag hier ändert nur die Client-Konfiguration, nicht die Architektur.

### 8.4 Weitere Härtung

- Security-Header: `Content-Security-Policy` (strikt, keine Inline-Skripte), `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy`. HSTS setzt Traefik/Pangolin.
- Längenbegrenzung auf `capture`-Eingaben (z. B. 5000 Zeichen) — begrenzt LLM-Laufzeit und Missbrauch.
- Prompt-Injection: Der `source_text` ist grundsätzlich nicht vertrauenswürdig. Die Angriffsfläche ist hier aber klein, weil die Modellausgabe ausschließlich in ein festes Schema fließt und keinerlei Code oder Kommandos auslöst. Beim Rendering im UI gilt normale Escaping-Disziplin (React tut das per Default; `dangerouslySetInnerHTML` ist verboten).
- Audit-Log für: Anmeldeversuche, Nutzeranlage/-löschung, Konfigurationsänderungen, Prompt-Aktivierung.

### 8.5 Geheimnisse im Ruhezustand

SMTP-Passwort und ggf. Ollama-Credentials werden mit Fernet (`cryptography`) verschlüsselt in `app_config` abgelegt. Schlüssel in `/etc/tasks/secret.key`, Rechte `0600`, Eigentümer der Service-User, **außerhalb** von Datenbank und Backup-Pfad.

**Ehrliche Einordnung:** Das schützt gegen ein abhandengekommenes Datenbank-Backup — der realistische Vorfall. Gegen root-Zugriff auf dem Host schützt es nicht und soll es nicht. Wer ein höheres Schutzniveau braucht, muss zu einem externen Secret Store greifen; für diesen Anwendungsfall wäre das unverhältnismäßig.

---

## 9. Web-Frontend

### 9.1 Bildschirmaufbau

```
┌──────────────────────────────────────────────────────────────┐
│  Kapture              🔍 Suche…            [BK ▾]  ⚙  v1.2.0 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────┐              │
│  │ Was ist zu tun?                            │  [Erstellen] │
│  │                                            │              │
│  └────────────────────────────────────────────┘              │
│    Strg+Enter · ⌘K fokussiert · 🎤 · ⚙ Details               │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  Heute (4) │ Diese Woche │ Überfällig (2) │ Eingang │ Alle    │
│  ─────────                                                   │
│  [Kategorie ▾] [Priorität ▾] [Sortierung: Fällig ▾]  ⚠ 1     │
├──────────────────────────────────────────────────────────────┤
│  ○  Angebot Fa. Müller fertigstellen           P1  ⚠         │
│     Müller GmbH · heute 16:00 · 2/3 Subtasks                 │
│     ────────────────────────────────────────  67 %           │
│                                                              │
│  ◐  Kalkulation Projekt Nord prüfen            P2            │
│     MQC · morgen · in Bearbeitung                            │
│                                                              │
│  ⏸  Rückmeldung Fa. Schmitt                    P3            │
│     wartet auf: Hr. Schmitt · seit 4 Tagen                   │
│                                                              │
│  ✦  Reisekosten Q3 einreichen                                │
│     wird verarbeitet…                                        │
└──────────────────────────────────────────────────────────────┘
```

### 9.2 Ansichten statt Filterbaukasten

Die Anforderung lautet „Sortierung und Filter einfach durchzuführen". Der übliche Fehler ist ein generischer Filter-Builder — mächtig, aber genau die Komplexität, die vermieden werden soll.

**Stattdessen: feste Ansichten als Reiter, ergänzt durch zwei Dropdowns.**

| Ansicht | Inhalt |
|---------|--------|
| **Heute** | Fällig heute + überfällig + `start_at` ≤ heute, ohne Erledigte |
| **Diese Woche** | Fällig bis Sonntag |
| **Überfällig** | `due_at < now`, nicht erledigt |
| **Eingang** | Ohne Fälligkeitsdatum — die Aufräum-Ansicht |
| **Zur Prüfung** | `needs_review = 1` — erscheint nur bei Bedarf |
| **Alle offenen** | Alles außer erledigt/abgebrochen |
| **Erledigt** | Letzte 30 Tage, nach `completed_at` |

Gespeicherte eigene Ansichten (Filter + Sortierung unter Namen sichern) kommen in Phase 7.

### 9.3 Interaktionsdetails, die den Unterschied machen

- **Erledigte Tasks ausblenden** ist Default (Anforderung). Beim Abhaken bleibt die Zeile 4 Sekunden mit Durchstreichung und „Rückgängig" stehen, dann verschwindet sie — kein sofortiges Wegspringen.
- **Inline-Bearbeitung:** Klick auf Datum/Priorität/Kategorie öffnet ein Popover, keine Detailseite. Detailseite nur für Beschreibung und Subtasks.
- **Tastaturbedienung:** `⌘K`/`Strg+K` fokussiert die Eingabe, `/` die Suche, `j`/`k` navigieren, `x` erledigt, `e` bearbeitet, `1`–`4` setzt Priorität, `t` verschiebt auf morgen. Auf dem Desktop ist das der schnellste Weg und ein spürbarer Vorteil gegenüber mausorientierten Apps.
- **Live-Aktualisierung:** SSE-Verbindung auf `/api/v1/events`; abgeschlossene LLM-Jobs aktualisieren die Zeile ohne Reload.
- **`needs_review`:** dezentes ⚠ mit Tooltip aus `review_notes` („Fälligkeitsdatum aus ‚Freitag' abgeleitet — bitte prüfen"). Ein Klick bestätigt.

### 9.4 Reports

| Report | Inhalt |
|--------|--------|
| **Aktuelle Tasks** | Tabellenansicht, dichter als die Listenansicht, **inline editierbar** (Anforderung), Spalten wählbar, CSV-Export |
| **Abgeschlossene Tasks** | Zeitraumfilter, Gruppierung nach Kategorie/Woche |
| **Volltextsuche** | FTS5 über Titel, Beschreibung, Rohtext, `waiting_for`, Ort; Treffer-Snippets mit Hervorhebung; Filter auf Zeitraum und Status |
| **Wochenrückblick** *(Phase 7)* | Erledigt vs. neu angelegt, Durchlaufzeiten, überfällige Dauerbrenner, häufigste Kategorien |

---

## 10. Android-App

### 10.1 Umfang

| Bereich | Inhalt |
|---------|--------|
| **Einstellungen** | Server-URL, Nutzername/Passwort, Pangolin-Access-Token (Token-ID + Token), App-PIN/Biometrie, Sync-Intervall, Benachrichtigungen |
| **Erfassung** | Große Eingabefläche als Startbildschirm; Spracheingabe über System-STT oder Server-Whisper |
| **Liste** | Dieselben Ansichten wie im Web, Wischgesten (rechts = erledigt, links = morgen) |
| **Detail** | Alle Felder editierbar, Subtasks abhakbar |
| **Suche** | Serverseitig; offline auf den lokalen Cache begrenzt |
| **Widget** | Homescreen-Widget „Heute" + Direktzugriff auf die Erfassung |
| **Share-Target** | Text aus beliebiger App teilen → Task. Sehr hoher Alltagsnutzen, geringer Aufwand. |
| **Versionsanzeige** | App-Version + verbundene Serverversion; Warnung bei Inkompatibilität |

### 10.2 Offline und Synchronisation

- **Lokaler Cache:** Room; Tasks werden clientseitig mit UUID angelegt und funktionieren offline.
- **Outbox:** Ausstehende Änderungen als Queue; `WorkManager` mit `NetworkType.CONNECTED` überträgt sie.
- **Delta-Pull:** `GET /sync?since=<letzter Servertimestamp>`. **Wichtig: den vom Server gelieferten Zeitstempel verwenden, nicht die Gerätezeit** — sonst gehen bei Uhrenabweichung Änderungen verloren.
- **Konfliktstrategie:** Last-Write-Wins auf Datensatzebene über `updated_at`, Server ist maßgeblich. Bei Konflikt wird die verworfene Fassung 7 Tage lokal aufbewahrt und dem Nutzer als Hinweis angezeigt.

  *Ehrliche Einschränkung:* LWW auf Datensatzebene kann eine parallele Änderung an einem anderen Feld überschreiben. Feldweises Merging wäre korrekter, aber deutlich aufwendiger. Bei Einzelnutzung mit zwei Geräten ist das Risiko klein; bei häufiger Parallelnutzung sollte man feldweises Merging nachrüsten.

- **Offline-Erfassung mit LLM:** Ohne Verbindung wird der Rohtext gespeichert und der LLM-Job beim nächsten Sync serverseitig nachgeholt. Der Task ist zwischenzeitlich mit Rohtext-Titel nutzbar (P3).

### 10.3 Benachrichtigungen

Firebase Cloud Messaging widerspricht dem Self-Hosting-Ansatz (Google-Abhängigkeit, Metadatenabfluss). Empfehlung:

1. **Primär: lokale Alarme.** Nach jedem Sync werden für alle bekannten `reminders` `AlarmManager`-Einträge gesetzt. Funktioniert offline, ohne Fremdinfrastruktur, zuverlässig. Deckt den Hauptanwendungsfall (Fälligkeitserinnerung) vollständig ab.
2. **Optional: UnifiedPush/ntfy** für serverseitig ausgelöste Ereignisse. Nur nötig, wenn der Server unabhängig vom Gerät etwas mitteilen soll.

Zu beachten: Android 15 verlangt für exakte Alarme die `SCHEDULE_EXACT_ALARM`-Berechtigung mit Nutzerbestätigung. Für Task-Erinnerungen genügt in der Regel `setWindow()` mit ±15 Minuten Toleranz — das vermeidet den Berechtigungsdialog.

---

## 11. Tägliche Zusammenfassung per E-Mail

### 11.1 Ablauf

Der Scheduler im Worker prüft minütlich, für welche Nutzer die lokale `daily_summary_time` erreicht ist (Zeitzone pro Nutzer!), stellt die Daten zusammen und versendet.

**Inhalt:**

1. **Überfällig** — zuerst, mit Anzahl der Tage
2. **Heute fällig** — nach Priorität
3. **In Bearbeitung** — angefangen, aber nicht fällig
4. **Wartend** — mit Wartedauer und Person („seit 4 Tagen auf Hr. Schmitt")
5. **Diese Woche** — Ausblick, kompakt
6. **Kurzeinordnung vom LLM** — 2–3 Sätze Prosa mit Priorisierungsvorschlag

Punkt 6 ist der eigentliche Mehrwert gegenüber einer schlichten Liste: „Heute sind vier Tasks fällig, davon zwei mit P1. Das Müller-Angebot hängt an der Rücksprache mit Sabine — das zuerst, sonst wird 16 Uhr knapp." Kosten: ein LLM-Aufruf pro Nutzer und Tag.

**Versand als `multipart/alternative`** (Plaintext + HTML mit Inline-CSS, tabellenbasiertes Layout wegen Outlook). Fehlgeschlagene Versendungen werden protokolliert und zweimal mit Backoff wiederholt.

### 11.2 SMTP-Konfiguration

Verwaltbar über `/admin/config`: Host, Port, Verschlüsselung (`none` / `starttls` / `ssl`), Nutzer, Passwort (verschlüsselt), Absenderadresse, Absendername, Antwortadresse. Plus **Testversand-Button** — ohne den ist SMTP-Fehlersuche unnötig mühsam.

---

## 12. Konfiguration und Administration

### 12.1 Ebenen

| Ebene | Ort | Inhalt |
|-------|-----|--------|
| **Umgebung** | `/etc/tasks/tasks.env` | `DATABASE_URL`, `SECRET_KEY`, `SECRET_KEY_FILE`, `BIND_HOST`, `BIND_PORT=5000`, `LOG_LEVEL` — alles, was zum Start nötig ist |
| **Global** | `app_config` (DB, Admin-UI) | Ollama-URL/Modell/Timeout, SMTP, Standardwerte, Aufbewahrungsfristen |
| **Prompts** | `prompts` (DB, versioniert) | Prompt-Templates mit Aktiv-Kennzeichnung |
| **Pro Nutzer** | `users` (Admin- oder Selbstverwaltung) | Zeitzone, Standard-Fälligkeitszeit, Mailadresse, Sendezeit, Kontexttext |

### 12.2 Admin-Oberfläche

- **Nutzer:** Liste, anlegen (mit Initialpasswort und Änderungszwang), bearbeiten, deaktivieren, löschen (weich/hart), Sitzungen widerrufen
- **LLM:** URL, Modellauswahl per Dropdown aus der Ollama-Modellliste, Timeout, Temperatur, `keep_alive`, Verbindungstest mit Latenzanzeige
- **Prompts:** Editor mit Platzhalter-Hilfe, Versionshistorie, **Testfeld** (Text eingeben → gerenderter Prompt + rohes JSON), Aktivieren, Zurückrollen
- **SMTP:** Konfiguration + Testversand
- **Jobs:** letzte 200 LLM-Jobs mit Dauer, Modell, Fehlern — die zentrale Diagnoseansicht
- **System:** Versionen, DB-Größe, Task-Zahlen, Ollama-Erreichbarkeit, letzte Backups

### 12.3 Versionierung

**SemVer** (`MAJOR.MINOR.PATCH`) für Server und App getrennt.

- Server liefert unter `/api/v1/version`: App-Version, API-Version, DB-Schema-Revision (Alembic), Git-SHA, Build-Datum, `min_android_version`
- Web-UI zeigt die Version in der Kopfzeile
- Android zeigt eigene Version + Serverversion; ist die eigene Version älter als `min_android_version`, erscheint ein blockierender Hinweis
- Bei API-Brüchen wird `/api/v2` eingeführt, `/api/v1` bleibt mindestens eine Minor-Version lang bestehen

---

## 13. Deployment

### 13.1 LXC

```
Container:  unprivileged, Debian 13 (Trixie)
Ressourcen: 2 vCPU, 2 GB RAM, 16 GB Disk
            (Ollama läuft getrennt — dort liegt der Ressourcenbedarf)
Netz:       statische IP, Port 5000 nur aus dem LAN erreichbar
Nesting:    nicht erforderlich
```

```
/opt/tasks/
  ├── app/            Backend-Code
  ├── static/         React-Build (vom Build-Rechner deployt)
  ├── venv/
  └── alembic/
/var/lib/tasks/
  ├── tasks.db        SQLite (WAL)
  └── backups/
/etc/tasks/
  ├── tasks.env       0640, Gruppe tasks
  └── secret.key      0600, Nutzer tasks
```

Systembenutzer `tasks` ohne Login-Shell. systemd-Härtung in beiden Units: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `ReadWritePaths=/var/lib/tasks`.

**Node.js wird im LXC nicht benötigt** — das Frontend wird auf dem Entwicklungsrechner oder in der CI gebaut und als statisches Verzeichnis ausgeliefert.

### 13.2 Backup

- **Nächtlich:** `VACUUM INTO '/var/lib/tasks/backups/tasks-YYYYMMDD.db'` — im WAL-Modus die einzige konsistente Methode. Ein einfaches `cp` der Datei ist **nicht** zuverlässig.
- Aufbewahrung: 14 Tagesstände, 8 Wochenstände
- Zusätzlich Proxmox-Backup des gesamten Containers
- **Restore mindestens einmal testen.** Ein Backup, dessen Wiederherstellung nie geprüft wurde, ist eine Annahme, kein Backup.

### 13.3 Betrieb

- Logging strukturiert (JSON) nach journald; `journalctl -u tasks-api -f`
- `/api/v1/health` liefert Ollama-Erreichbarkeit, DB-Schreibbarkeit, Queue-Länge, ältester wartender Job
- Optionaler Uptime-Kuma-Check auf `/health`

---

## 14. Datenschutz

Relevant, sobald geschäftliche Task-Inhalte verarbeitet werden — Task-Texte enthalten fast zwangsläufig Kundennamen und Vorgangsdetails.

| Anforderung | Umsetzung |
|-------------|-----------|
| **Datenminimierung** | Lokales LLM, keine Übertragung an Dritte. Das ist der zentrale Vorteil dieser Architektur. |
| **Zweckbindung** | Kein Tracking, keine Analytics, keine Telemetrie |
| **Auskunft & Portabilität** | `/tasks/export?format=json\|csv` liefert alle Daten des Nutzers |
| **Löschung** | Soft Delete mit 30 Tagen Karenz, danach automatisch hart. Admin-Löschung eines Nutzers kaskadiert über alle Tabellen inkl. `llm_corrections`. |
| **Aufbewahrung** | Konfigurierbar: erledigte Tasks nach X Monaten archivieren oder löschen |
| **Nachweisbarkeit** | Audit-Log für Anmeldungen, Nutzer- und Konfigurationsänderungen |
| **Verarbeitungsverzeichnis** | Bei geschäftlicher Nutzung: kurzer Eintrag mit Zweck, Datenkategorien, Empfängern (keine), Fristen, TOMs |

---

## 15. Entwicklungsreihenfolge

Die Reihenfolge folgt zwei Regeln: **Risiken zuerst** und **Abhängigkeiten respektieren**. Die LLM-Pipeline steht deshalb früh (Phase 2) — sie birgt das größte technische Risiko und bestimmt Teile des Datenmodells. Android steht zuletzt, weil eine instabile API dort den doppelten Aufwand erzeugt.

Zeitangaben sind grobe Schätzungen für eine Person mit einschlägiger Erfahrung und dienen der Reihenfolgeplanung, nicht der Terminzusage.

### Phase 0 — Fundament (2–3 Tage)

- Entscheidungen aus Kapitel 16 klären (mindestens F1–F4)
- LXC bereitstellen, Python 3.13, Systembenutzer, Verzeichnisse
- Ollama-Erreichbarkeit prüfen, Kandidatenmodelle laden
- Repository, Struktur, Linting (`ruff`), Formatierung, `pytest`, pre-commit
- `/health` und `/version` als erster laufender Endpunkt

**Fertig, wenn:** `curl http://lxc:5000/api/v1/health` antwortet und `ollama list` vom LXC aus funktioniert.

### Phase 1 — Backend-Kern (5–8 Tage)

- Vollständiges Datenmodell + Alembic-Initialmigration
- Argon2-Passwörter, Login, Refresh-Rotation, Admin-Rolle
- Nutzerverwaltung (`/admin/users`)
- Task-CRUD mit strikter Mandantentrennung, Kategorien, Subtasks, Tags
- FTS5 + Trigger, Suchendpunkt
- Fehlerkonvention, Rate Limiting, Audit-Log-Grundgerüst
- **Isolationstest** (Kapitel 5.4) — dieser Test ist Teil des Phasenabschlusses, nicht optional

**Fertig, wenn:** Alle CRUD-Operationen per `httpx`-Test durchlaufen und der Isolationstest über alle Routen grün ist.

### Phase 2 — LLM-Pipeline (5–8 Tage) · *höchstes Risiko*

- Eval-Set mit 40–60 deutschen Beispielen + Soll-JSON **zuerst**
- Ollama-Client mit `format`, Timeouts, `keep_alive`
- Pydantic-Schema, Repair-Retry, Normalisierung
- Zweistufige Datumsauflösung mit `dateparser`
- Prompt-Tabelle, Jinja2-Rendering, Versionierung
- Job-Tabelle + Worker-Prozess
- `/tasks/capture` + SSE-Events
- Few-Shot-Injektion aus `llm_corrections`
- `evaluate.py`, Modellvergleich, Prompt v1 fixieren

**Fertig, wenn:** Das Eval-Set mit dem gewählten Modell ≥ 85 % Feldgenauigkeit erreicht und die mittlere Verarbeitungszeit unter 15 Sekunden liegt. *Wird die Schwelle nicht erreicht: größeres Modell, Hardware prüfen oder Prompt überarbeiten — nicht weitergehen.* Ein schwaches Fundament hier macht die gesamte App wertlos.

### Phase 3 — Web-Frontend (8–12 Tage)

- Vite-Projekt, Tailwind, TanStack Query, Router
- Login, Token-Handling, automatischer Refresh
- Erfassungsfeld mit optimistischem UI und SSE-Aktualisierung
- Task-Liste, Ansichten-Reiter, Filter, Sortierung
- Inline-Bearbeitung, Popovers, Subtasks
- Tastaturkürzel
- Admin-Oberfläche (Nutzer, LLM, Prompts mit Testfeld)
- Responsive — dient gleichzeitig als PWA-Vorstufe

**Fertig, wenn:** Ein kompletter Arbeitstag ausschließlich über die Web-Oberfläche abgewickelt werden kann.

### Phase 4 — Reports und E-Mail (3–5 Tage)

- Tabellenreport mit Inline-Bearbeitung
- Report „Abgeschlossene Tasks", Suchoberfläche
- CSV-/JSON-Export
- SMTP-Client, Konfiguration, Testversand
- Scheduler mit Zeitzonen, Zusammenfassungs-Template, LLM-Einordnung
- Wiederholungs-Tasks (RRULE-Auswertung beim Erledigen)

**Fertig, wenn:** Die tägliche Zusammenfassung an zwei Testnutzern in verschiedenen Zeitzonen korrekt ankommt.

### Phase 5 — Deployment und Pangolin (2–4 Tage)

- systemd-Units mit Härtung, Deployment-Skript
- Backup-Job + **getesteter Restore**
- Pangolin-Resource, Newt-Tunnel, TLS
- **Praxistest der Pangolin-Client-Authentifizierung** (Kapitel 8.3) — mit `curl` und den Access-Token-Headern, bevor eine Zeile Kotlin geschrieben wird
- Sicherheitsdurchsicht: Header, Rate Limits, Isolationstest gegen die produktive Instanz

**Fertig, wenn:** Die Anwendung von extern über Pangolin nutzbar ist und ein `curl`-Aufruf mit Access-Token-Headern die API erreicht.

### Phase 6 — PWA und Alltagstest (2–3 Tage + 1–2 Wochen Nutzung)

- Manifest, Service Worker, Icons, Installierbarkeit
- Mobile Layout-Feinschliff
- **Zwei Wochen echte Nutzung im Alltag**

Diese Phase ist bewusst eingeplant. Sie beantwortet zwei teure Fragen empirisch statt spekulativ: Reicht die PWA? Und welche Prompt- und UI-Schwächen zeigen sich erst unter realer Nutzung? Zwei Wochen Verzögerung sind hier deutlich billiger als eine native App, die am falschen Problem gebaut wurde.

### Phase 7 — Android-App (15–25 Tage) · *nur bei Bedarf nach Phase 6*

1. Projektgerüst, Compose, Navigation, DI (Hilt)
2. Einstellungsbildschirm: Server-URL, Zugangsdaten, Pangolin-Header
3. HTTP-Client mit Token-Refresh-Interceptor und Pangolin-Headern
4. Room-Schema, Repository, erster Read-Only-Sync
5. Task-Liste, Ansichten, Wischgesten
6. Detail- und Bearbeitungsansicht
7. Erfassung + Offline-Outbox
8. Delta-Sync mit WorkManager, Konfliktbehandlung
9. Lokale Erinnerungen, App-PIN/Biometrie
10. Share-Target, Homescreen-Widget
11. Versionsprüfung, Fehlerbehandlung, Signierung

### Phase 8 — Ausbau (fortlaufend)

Nach Nutzen priorisiert: mehrere Tasks aus einem Text (falls in Phase 2 zurückgestellt) → Duplikatserkennung → Task-Update per Freitext → Subtask-Generierung auf Abruf → Wochenrückblick → gespeicherte Ansichten → ICS-Export → Spracherfassung mit Whisper → semantische Suche.

### 15.1 Kritischer Pfad

```
Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → [Entscheidung] → 7
                 ↑                        ↑
        Risiko-Gate:              Entscheidungspunkt:
        Eval-Set ≥ 85 %           PWA ausreichend?
```

Phase 4 kann teilweise parallel zu Phase 3 laufen (Backend-Anteil). Phase 5 ist unabhängig von 3/4 und kann vorgezogen werden, sobald Phase 1 steht — die Pangolin-Verifikation früh zu erledigen, nimmt Unsicherheit aus der Planung.

---

## 16. Offene Fragen

### Blockierend — vor Phase 0 zu klären

**F1 · Welche Hardware steht Ollama zur Verfügung?**
GPU mit wie viel VRAM, oder CPU-Inferenz? Dies bestimmt Modellgröße, Antwortzeit und damit, ob P2 („LLM blockiert nie") überhaupt komfortabel erreichbar ist. Auf reiner CPU-Inferenz mit einem 14-B-Modell sind 30–90 Sekunden pro Task realistisch — dann muss die Asynchronität nicht nur vorhanden, sondern im UI deutlich sichtbarer gestaltet sein.

**F2 · Werden geschäftliche Kundendaten in Tasks verarbeitet?**
Bei Ja: Audit-Log, Löschkonzept und Verarbeitungsverzeichnis rücken von „nice to have" nach Phase 1. Bei rein privater Nutzung kann Kapitel 14 stark abgespeckt werden.

**F3 · Wie viele Nutzer sind realistisch zu erwarten?**
Bis ca. 10: SQLite wie beschrieben. Ab ca. 50 oder bei Bedarf mehrerer API-Prozesse: PostgreSQL von Anfang an — der spätere Wechsel ist zwar möglich, aber lästig.

**F4 · Bleibt es dauerhaft bei strikter Datentrennung?**
Sollen Tasks jemals zwischen Nutzern geteilt oder delegiert werden können? Ein Nachrüsten bedeutet ein neues Berechtigungsmodell quer durch Datenmodell und API — das ist die teuerste denkbare Nachrüstung. Bei auch nur vagem Bedarf sollte jetzt ein `owner_id`/`assignee_id`-Paar statt eines einzelnen `user_id` vorgesehen werden. Kosten heute: gering.

### Wichtig — vor Phase 2 bzw. 3 zu klären

**F5 · Kategorien: gepflegte Liste oder frei durch das LLM?**
Empfehlung: gepflegte Liste mit Aliasen, das LLM wählt daraus. Freie Kategorien führen binnen Wochen zu „MQC", „Mighty Quinn", „mqc.one" und „Firma" als vier Kategorien. Nachteil: einmalige Pflege beim Anlegen.

**F6 · Wie soll bei mehrdeutigen Eingaben verfahren werden?**
Zwei Modelle: (a) Task wird angelegt und `needs_review` markiert — schneller Fluss, gelegentliche Nacharbeit. (b) Vorschau-Dialog vor dem Speichern — mehr Kontrolle, aber verstößt gegen P1. Empfehlung: (a) als Standard, (b) als abschaltbare Option pro Nutzer.

**F7 · Werden Wiederholungen wirklich gebraucht?**
Wiederholende Tasks sind konzeptionell einfach, in der Implementierung aber überraschend aufwendig (Ausnahmen, „diese Instanz überspringen", nachträgliche Regeländerung). Wenn sie im Alltag keine Rolle spielen, spart das Weglassen mehrere Tage.

**F8 · Wird eine Kalenderanbindung gebraucht?**
Ein read-only ICS-Feed (Tasks mit Fälligkeitsdatum, abonnierbar in Outlook/M365) ist mit etwa einem Tag Aufwand umsetzbar und im Arbeitsalltag oft wertvoller als eine Benachrichtigungsfunktion. Bidirektionale Synchronisation ist eine ganz andere Größenordnung und sollte nicht angefangen werden.

**F9 · Soll E-Mail als Eingangskanal dienen?**
Da SMTP ohnehin konfiguriert wird: Ein IMAP-Postfach abfragen und weitergeleitete Mails zu Tasks verarbeiten wäre naheliegend. Das ist ein ausgesprochen praktischer Erfassungsweg — aber ein eigenständiges Teilprojekt inkl. Absender-Zuordnung und Spam-Schutz. Als Phase-8-Kandidat vormerken.

**F10 · Mehrsprachigkeit?**
Nur Deutsch, oder soll das UI i18n-fähig sein? Nachträgliches Extrahieren aller Texte ist mühsam; von Anfang an mit `react-i18next` zu arbeiten kostet fast nichts.

### Später zu klären

- **F11 ·** Aufbewahrungsfrist für erledigte Tasks — löschen, archivieren, oder unbegrenzt behalten?
- **F12 ·** Soll das LLM Kategorie- und Prioritätsvorschläge auch für bestehende Tasks nachträglich liefern (Massen-Reprocessing nach Prompt-Verbesserung)?
- **F13 ·** Benachrichtigungen: reichen lokale Alarme, oder wird ein serverseitiger Push-Kanal (ntfy/UnifiedPush) benötigt?
- **F14 ·** Zwei-Faktor-Authentifizierung (TOTP) für die Anwendungsanmeldung — zusätzlich zur Pangolin-Ebene sinnvoll oder überflüssig?

---

## Anhang A — Prompt-Template (Ausgangsversion)

```jinja
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
- Imperativ, prägnant, maximal 80 Zeichen ("Angebot Müller fertigstellen").
- Keine Datums- oder Prioritätsangaben im Titel.

BESCHREIBUNG
- Nur wenn der Text substanziell mehr enthält als der Titel. Sonst null.

DATUM
- due_source_phrase: der wörtliche Textabschnitt, aus dem du das Datum ableitest
  (z. B. "bis Freitag 16 Uhr"). Kein Datum genannt → beide Felder null.
- due_at: ISO 8601 mit Offset. Rechne relative Angaben ausgehend von "Jetzt".
- Datum ohne Uhrzeit → Uhrzeit {{ default_due_time }}, due_is_all_day = true.
- Erfinde niemals ein Datum, das im Text nicht angedeutet ist.

PRIORITÄT
- 1 = dringend und wichtig ("sofort", "eilt", "kritisch")
- 2 = wichtig, terminiert ("wichtig", "muss bis …")
- 3 = normal (Standard, wenn nichts darauf hindeutet)
- 4 = irgendwann ("bei Gelegenheit", "wäre schön")

STATUS
- "wartend" nur, wenn der Text auf das Warten auf eine andere Person hinweist.
  Dann waiting_for mit der Person füllen.
- Sonst "offen".

SUBTASKS
- Nur bei erkennbar mehrschrittigen Vorhaben. Maximal 8. Im Zweifel leer.

CONFIDENCE UND AMBIGUITIES
- confidence: deine ehrliche Selbsteinschätzung, 0.0 bis 1.0.
- ambiguities: was unklar war, in Sätzen, die der Nutzer versteht
  (z. B. "Unklar, ob 'Freitag' diese oder nächste Woche gemeint ist").
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
```

## Anhang B — Beispiel

**Eingabe**

> Angebot Fa. Müller bis Freitag 16 Uhr fertigstellen, vorher noch Rücksprache mit Sabine wegen der Stundensätze, ist wichtig

**Erwartete Ausgabe** (Kontext: Samstag, 08.08.2026, Kategorien: `MQC`, `Müller GmbH`, `Privat`)

```json
{
  "title": "Angebot Fa. Müller fertigstellen",
  "description": "Vorab Rücksprache mit Sabine wegen der Stundensätze.",
  "due_at": "2026-08-14T16:00:00+02:00",
  "due_source_phrase": "bis Freitag 16 Uhr",
  "due_is_all_day": false,
  "start_at": null,
  "category": "Müller GmbH",
  "category_suggestion": null,
  "priority": 2,
  "status": "offen",
  "waiting_for": null,
  "tags": ["angebot"],
  "subtasks": ["Rücksprache mit Sabine wegen Stundensätze"],
  "estimated_minutes": 120,
  "location": null,
  "url": null,
  "recurrence_rule": null,
  "confidence": 0.85,
  "ambiguities": [
    "'Freitag' als kommender Freitag (14.08.) interpretiert"
  ]
}
```

**Serverseitige Nachbearbeitung:** `dateparser` löst „bis Freitag 16 Uhr" ebenfalls auf `2026-08-14T16:00` auf → Übereinstimmung → `needs_review = 0`, aber `review_notes` behält den Hinweis für den Tooltip.

---

## Anhang C — Erste Konfigurationsschlüssel

| Schlüssel | Beispiel | Geheim |
|-----------|----------|--------|
| `ollama.base_url` | `http://10.0.0.42:11434` | nein |
| `ollama.model` | *(nach Eval festzulegen)* | nein |
| `ollama.timeout_seconds` | `90` | nein |
| `ollama.keep_alive` | `30m` | nein |
| `ollama.temperature` | `0.1` | nein |
| `smtp.host` | `smtp.example.com` | nein |
| `smtp.port` | `587` | nein |
| `smtp.security` | `starttls` | nein |
| `smtp.username` | `tasks@example.com` | nein |
| `smtp.password` | — | **ja** |
| `smtp.from_address` | `tasks@example.com` | nein |
| `smtp.from_name` | `Kapture` | nein |
| `app.default_due_time` | `17:00` | nein |
| `app.capture_max_chars` | `5000` | nein |
| `app.completed_retention_days` | `365` | nein |
| `app.softdelete_grace_days` | `30` | nein |
| `llm.fewshot_count` | `8` | nein |
| `llm.max_repair_attempts` | `1` | nein |
