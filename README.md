# MyTasks — LLM-powered task management

Self-hosted task application (FastAPI + SQLite + React) that turns free-form text into structured tasks — primarily via local rule-based extraction, with an optional Ollama model as fallback.

**Version:** 0.8.6 (Server) · Android-App 1.2.0 (separates Release, siehe unten)

## Requirements

- Debian 13 LXC or VM (2 vCPU, 2 GB RAM, 16 GB disk)
- Python 3.13, Node.js 20
- Ollama (optional — without it, local extraction keeps working)
- Root privileges for installation

## Installation

```bash
# 1. Unzip
unzip MyTasks.zip && cd MyTasks

# 2. Install (with remote Ollama)
sudo ./install.sh --ollama-url http://your-ollama-server:11434

# OR: with local Ollama
sudo ./install.sh --install-ollama

# OR: without LLM (local extraction only; enable LLM later in the app)
sudo ./install.sh

# 3. Open in browser
# http://<server-ip>:5000/
```

The installer creates an admin user interactively.

## Update

```bash
cd MyTasks
sudo ./update.sh
```

Syncs the complete code state (all changes since the last update in one run), rebuilds the frontend, runs DB migrations, creates a database backup beforehand and restarts the services. The version number is maintained via Git; optionally increment with `--bump patch|minor|major`.

## Configuration

All settings live in `/etc/tasks/tasks.env`:

| Variable | Description |
|----------|-------------|
| `TASKS_BIND_PORT` | HTTP port (default: `5000`) |

LLM and email are configured **per user** in the app under **Settings**:

- **AI assistant (LLM):** Ollama base URL + model (offered as a dropdown after connection test). Optional — without configuration, extraction runs fully locally (~1 ms). When local detection is unsure, the LLM is used as fallback.
- **Email sending:** Your own SMTP credentials for test emails and the daily summary. The password is stored encrypted. Without configuration no emails are sent.

### Languages

The web UI is available in German and English. By default the browser language is used; a selection made via the DE/EN switch in the header is stored in a cookie. Email summaries follow the user's language choice.

## Backup & Restore

```bash
# Daily backup runs automatically at 03:00 via cron.
# A rolling backup is also created before every update (last 3 kept).

# Manual backup:
/opt/tasks/deploy/backup.sh

# Restore:
sudo /opt/tasks/deploy/restore.sh /var/lib/tasks/backups/daily/tasks-YYYYMMDD.db
```

## Uninstall

```bash
sudo ./uninstall.sh
# Database is backed up for safety
```

## Android app

A lightweight native WebView wrapper for use behind [Pangolin](https://github.com/fosrl/pangolin) — the web UI, no separate feature set. Two login modes: **Access-Token** (e.g. from a Pangolin share link, sent as `P-Access-Token-Id` / `P-Access-Token` request headers) or **Pangolin-SSO** (one-time login in the app window, session via cookie). Tokens are stored in EncryptedSharedPreferences, HTTPS-only, `allowBackup=false`.

- Current version: **1.2.0** (`versionCode 4`, minSdk 26 / Android 8.0+)
- Download the signed debug APK from [GitHub Releases](https://github.com/bkemmler/MyTasks/releases) (`MyTasks-1.2.0-debug.apk`), uninstall any previous build first if the signature changed, then enter server URL + credentials in the config screen
- Details (auth modes, security, build in Android Studio): [`android/README.md`](android/README.md)

## Architecture

```
Browser / Android WebView → http://server:5000/ (or via Pangolin)
         ├── FastAPI REST API (/api/v1/)
         ├── React SPA + PWA (static files)
         └── SSE (/api/v1/events) — real-time updates

Task pipeline → Local extraction (rule-based, ~1 ms)
              → Ollama HTTP as fallback when confidence is low (optional)

Worker (systemd) → Scheduler (summaries, recurring tasks)
                 → SQLite (WAL)
                 → Per-user SMTP → email delivery
```

## Recurring tasks

Recurring tasks are supported daily/weekly/monthly/yearly:
- Detected from text while capturing ("every monday", "daily", "every 2 weeks", "monthly on the 1st.")
- Editable per task in the detail view via a dropdown
- On completion, the next instance is created automatically

## Database

SQLite with WAL mode. Location: `/var/lib/tasks/tasks.db`. Schema migrations run automatically at startup (`init_db`).

## Logs

```bash
journalctl -u tasks-api -f
journalctl -u tasks-worker -f
```
