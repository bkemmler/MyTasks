# MyTasks — LLM-gestützte Task-Verwaltung

Selbst gehostete Task-Anwendung (FastAPI + SQLite + React), bei der ein lokales Ollama-Modell freien Text in strukturierte Tasks übersetzt.

**Version:** 0.4.9

## Voraussetzungen

- Debian 13 LXC oder VM (2 vCPU, 2 GB RAM, 16 GB Disk)
- Python 3.13, Node.js 20
- Ollama (lokal oder auf einem anderen Server im LAN)
- Root-Rechte für die Installation

## Installation

```bash
# 1. ZIP entpacken
unzip MyTasks.zip && cd MyTasks

# 2. Installieren (mit Remote-Ollama)
sudo ./install-kapture.sh --ollama-url http://dein-ollama-server:11434

# ODER: Mit lokalem Ollama
sudo ./install-kapture.sh --install-ollama

# 3. Im Browser öffnen
# http://<server-ip>:5000/
```

Der Installer legt einen Admin-Nutzer interaktiv an.

## Update

```bash
cd MyTasks
sudo ./update-kapture.sh
```

Erhöht automatisch die Version (Patch-Increment), baut Frontend neu, führt DB-Migrationen aus, startet Dienste neu.

## Konfiguration

Alle Einstellungen in `/etc/tasks/tasks.env`:

| Variable | Beschreibung |
|----------|-------------|
| `TASKS_OLLAMA_BASE_URL` | Ollama-URL (Default: `http://localhost:11434`) |
| `TASKS_OLLAMA_MODEL` | LLM-Modell (Default: `gemma4:e2b`) |
| `TASKS_SMTP_HOST` | SMTP-Server für tägliche E-Mail-Zusammenfassung |
| `TASKS_BIND_PORT` | HTTP-Port (Default: `5000`) |

## Backup & Restore

```bash
# Tägliches Backup läuft automatisch um 03:00 via Cron.

# Manuelles Backup:
/opt/tasks/deploy/backup.sh

# Restore:
sudo /opt/tasks/deploy/restore-kapture.sh /var/lib/tasks/backups/daily/tasks-YYYYMMDD.db
```

## Deinstallation

```bash
sudo ./uninstall-kapture.sh
# Datenbank wird nach /root/kapture-backup-<datum>/ gesichert
```

## Architektur

```
Browser → http://server:5000/
         ├── FastAPI REST API (/api/v1/)
         ├── React SPA (static files)
         └── SSE (/api/v1/events) — Echtzeit-Updates

Worker (systemd) → Ollama HTTP → LLM Extraktion
                 → SQLite (WAL) → Datenbank
                 → SMTP → Tägliche E-Mail-Zusammenfassung
```

## Datenbank

SQLite mit WAL-Modus. Ort: `/var/lib/tasks/tasks.db`

## Logs

```bash
journalctl -u tasks-api -f
journalctl -u tasks-worker -f
```
