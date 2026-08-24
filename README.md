# MyTasks — LLM-gestützte Task-Verwaltung

Selbst gehostete Task-Anwendung (FastAPI + SQLite + React), bei der freier Text in strukturierte Tasks übersetzt wird — primär über eine lokale regelbasierte Extraktion, optional mit Ollama-Modell als Fallback.

**Version:** 0.6.0

## Voraussetzungen

- Debian 13 LXC oder VM (2 vCPU, 2 GB RAM, 16 GB Disk)
- Python 3.13, Node.js 20
- Ollama (optional — ohne LLM läuft die lokale Extraktion weiter)
- Root-Rechte für die Installation

## Installation

```bash
# 1. ZIP entpacken
unzip MyTasks.zip && cd MyTasks

# 2. Installieren (mit Remote-Ollama)
sudo ./install.sh --ollama-url http://dein-ollama-server:11434

# ODER: Mit lokalem Ollama
sudo ./install.sh --install-ollama

# ODER: Ohne LLM (nur lokale Extraktion)
sudo ./install.sh

# 3. Im Browser öffnen
# http://<server-ip>:5000/
```

Der Installer legt einen Admin-Nutzer interaktiv an.

## Update

```bash
cd MyTasks
sudo ./update.sh
```

Synchronisiert den kompletten Code-Stand (alle Änderungen seit dem letzten Update in einem Lauf), baut Frontend neu, führt DB-Migrationen aus, erstellt vorher ein Datenbank-Backup und startet die Dienste neu. Die Versionsnummer wird via Git gepflegt; optional mit `--bump patch|minor|major` erhöhen.

## Konfiguration

Alle Einstellungen in `/etc/tasks/tasks.env`:

| Variable | Beschreibung |
|----------|-------------|
| `TASKS_OLLAMA_BASE_URL` | Ollama-URL (Default: `http://localhost:11434`) |
| `TASKS_OLLAMA_MODEL` | LLM-Modell; **leer = nur lokale Extraktion** (Default: leer) |
| `TASKS_BIND_PORT` | HTTP-Port (Default: `5000`) |

### E-Mail-Versand (pro Nutzer)

SMTP-Zugangsdaten werden **pro Nutzer** in der App unter **Einstellungen** hinterlegt (Host, Port, STARTTLS/SSL, Benutzername, Passwort, Absenderadresse). Das Passwort wird verschlüsselt gespeichert. Ohne eigene Mail-Konfiguration versendet die App für diesen Nutzer keine E-Mails — es gibt keinen globalen SMTP-Fallback.

Jeder Nutzer konfiguriert außerdem sein Profil (E-Mail, Anzeigename, Zeitzone) und die tägliche Zusammenfassung (Aktiv/Uhrzeit) unter **Einstellungen**.

## Backup & Restore

```bash
# Tägliches Backup läuft automatisch um 03:00 via Cron.
# Vor jedem Update wird zusätzlich ein Rolling-Backup erstellt (letzte 3).

# Manuelles Backup:
/opt/tasks/deploy/backup.sh

# Restore:
sudo /opt/tasks/deploy/restore.sh /var/lib/tasks/backups/daily/tasks-YYYYMMDD.db
```

## Deinstallation

```bash
sudo ./uninstall.sh
# Datenbank wird zur Sicherheit gesichert
```

## Architektur

```
Browser → http://server:5000/
         ├── FastAPI REST API (/api/v1/)
         ├── React SPA + PWA (static files)
         └── SSE (/api/v1/events) — Echtzeit-Updates

Task-Pipeline → Lokale Extraktion (regelbasiert, ~1 ms)
              → Ollama HTTP als Fallback bei niedriger Confidence (optional)

Worker (systemd) → Scheduler (Zusammenfassungen, Wiederholungen)
                 → SQLite (WAL)
                 → Pro-Nutzer-SMTP → E-Mail-Versand
```

## Datenbank

SQLite mit WAL-Modus. Ort: `/var/lib/tasks/tasks.db`. Schema-Migrationen laufen beim Start automatisch (`init_db`).

## Logs

```bash
journalctl -u tasks-api -f
journalctl -u tasks-worker -f
```
