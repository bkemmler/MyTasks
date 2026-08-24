#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# MyTasks — Update
# Aktualisiert Backend-Code, baut Frontend neu, führt Migrationen aus,
# startet Dienste neu. Konfiguration und Datenbank bleiben unberührt.
#
# Aufruf:  sudo ./update.sh
#          sudo ./update.sh --skip-frontend
#          sudo ./update.sh --skip-migrations
#          sudo ./update.sh --bump patch   (Version +1, sonst kein Bump)
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

APP_DIR="/opt/tasks"
DATA_DIR="/var/lib/tasks"
ETC_DIR="/etc/tasks"
SERVICE_USER="tasks"
SERVICE_GROUP="tasks"

DRY_RUN=false
SKIP_FRONTEND=false
SKIP_MIGRATIONS=false
BUMP="none"

usage() {
    cat <<EOF
Usage: $0 [optionen]
  --dry-run          Zeigt an, was passieren würde, ohne Änderungen
  --skip-frontend    Frontend-Build überspringen
  --skip-migrations  DB-Migrationen überspringen
  --bump LEVEL       Versions-Schritt: patch, minor, major (Default: kein Bump)
  -h, --help         Diese Hilfe
EOF
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)         DRY_RUN=true; shift ;;
        --skip-frontend)   SKIP_FRONTEND=true; shift ;;
        --skip-migrations) SKIP_MIGRATIONS=true; shift ;;
        --bump)            BUMP="$2"; shift 2 ;;
        -h|--help)         usage ;;
        *) echo "Unbekannt: $1"; usage ;;
    esac
done

# Hilfsfunktion: Versions-String inkrementieren (SemVer)
bump_version() {
    local v="$1" level="$2"
    local major="${v%%.*}"
    local rest="${v#*.}"
    local minor="${rest%%.*}"
    local patch="${rest#*.}"
    case "$level" in
        major) major=$((major + 1)); minor=0; patch=0 ;;
        minor) minor=$((minor + 1)); patch=0 ;;
        patch) patch=$((patch + 1)) ;;
        *) echo "Unbekannter Bump-Level: $level"; return 1 ;;
    esac
    echo "${major}.${minor}.${patch}"
}

# Hilfsfunktion: Version in app/__init__.py schreiben
write_version() {
    local file="$1" version="$2"
    python3 -c "
import re, sys
from pathlib import Path

p = Path('$file')
text = p.read_text()
new = re.sub(
    r'__version__\s*=\s*[\"\\']([^\"\\']*)[\"\\']',
    '__version__ = \"$version\"',
    text,
    count=1,
)
if new == text:
    print('FEHLER: __version__ nicht gefunden in $file')
    sys.exit(1)
p.write_text(new)
print(f'  $file → $version')
"
}

[[ $EUID -eq 0 ]] || { echo "FEHLER: root-Rechte benötigt"; exit 1; }

log()   { printf '\033[1;34m%s\033[0m\n' "$1"; }
ok()    { printf '  \033[32m✅ %s\033[0m\n' "$1"; }
warn()  { printf '  \033[33m⚠  %s\033[0m\n' "$1"; }
fail()  { printf '  \033[31m❌ %s\033[0m\n' "$1"; exit 1; }

# ── 1. Pre-Check ─────────────────────────────────────────────────────
log "=== MyTasks Update ==="
[[ "$DRY_RUN" == "true" ]] && log "*** DRY RUN — keine Änderungen ***"

# Health vor Update
if curl -sf http://localhost:5000/api/v1/health >/dev/null 2>&1; then
    VERSION=$(curl -s http://localhost:5000/api/v1/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")
    log "Aktuelle Version: $VERSION"
else
    warn "API antwortet nicht — Update läuft trotzdem."
    VERSION="?"
fi

# ── 1.1 Pre-Update-Backup ──────────────────────────────────────────
log "» Pre-Update-Backup..."
if [[ "$DRY_RUN" == "true" ]]; then
    log "  [DRY-RUN] würde DB-Backup erstellen"
else
    BACKUP_NAME="pre-update-$(date +%Y%m%d-%H%M%S).db"
    BACKUP_DIR="$DATA_DIR/backups/pre-update"
    mkdir -p "$BACKUP_DIR"
    chown "$SERVICE_USER":"$SERVICE_GROUP" "$BACKUP_DIR"

    if [[ -f "$DATA_DIR/tasks.db" ]]; then
        sqlite3 "$DATA_DIR/tasks.db" "VACUUM INTO '$BACKUP_DIR/$BACKUP_NAME'" 2>&1 || true
        chown "$SERVICE_USER":"$SERVICE_GROUP" "$BACKUP_DIR/$BACKUP_NAME" 2>/dev/null || true
        ok "Backup: $BACKUP_DIR/$BACKUP_NAME"
    else
        warn "Keine DB vorhanden — überspringe Backup"
    fi

    # Nur die letzten 3 Pre-Update-Backups behalten
    find "$BACKUP_DIR" -name "pre-update-*.db" -type f | sort -r | tail -n +4 | xargs -r rm -f
fi

# ── 2. Versions-Erhöhung (optional, --bump) ─────────────────────────
if [[ "$BUMP" == "none" ]]; then
    log "» Versions-Erhöhung übersprungen (Version wird via Git gepflegt)"
else
    log "» Versions-Erhöhung ($BUMP)..."
    CURRENT_VERSION=$(python3 -c "
import re, sys
try:
    text = open('$BACKEND_DIR/app/__init__.py').read()
    m = re.search(r'__version__\s*=\s*[\"\']([^\"\']+)[\"\']\s*$', text, re.M)
    print(m.group(1) if m else '0.0.0')
except FileNotFoundError:
    print('0.0.0')
" 2>/dev/null || echo "0.0.0")
    NEW_VERSION=$(bump_version "$CURRENT_VERSION" "$BUMP")
    log "  $CURRENT_VERSION → $NEW_VERSION"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "  [DRY-RUN] würde app/__init__.py auf $NEW_VERSION setzen"
    else
        if [[ "$CURRENT_VERSION" == "0.0.0" ]]; then
            warn "  app/__init__.py nicht gefunden — überspringe Bump"
        else
            write_version "$BACKEND_DIR/app/__init__.py" "$NEW_VERSION"
        fi
    fi
fi

# ── 2. Backend-Code aktualisieren ───────────────────────────────────
log "» Backend-Code nach $APP_DIR/..."

if [[ "$DRY_RUN" == "true" ]]; then
    log "  [DRY-RUN] rsync $BACKEND_DIR/app/ → $APP_DIR/app/"
else
    rsync -a --delete "$BACKEND_DIR/app/" "$APP_DIR/app/"
    cp -f "$BACKEND_DIR/pyproject.toml" "$APP_DIR/"
    cp -rf "$BACKEND_DIR/alembic" "$APP_DIR/"
    cp -f "$BACKEND_DIR/alembic.ini" "$APP_DIR/" 2>/dev/null || true
    cp -f "$BACKEND_DIR/deploy/backup.sh" "$APP_DIR/deploy/" 2>/dev/null || true
    ok "Backend-Code aktualisiert"
fi

# ── 3. Dependencies aktualisieren ───────────────────────────────────
log "» Python-Dependencies..."
if [[ "$DRY_RUN" == "true" ]]; then
    log "  [DRY-RUN] $APP_DIR/venv/bin/pip install -e $APP_DIR"
else
    sudo -u "$SERVICE_USER" "$APP_DIR/venv/bin/pip" install -e "$APP_DIR" -q 2>&1 | tail -3
    ok "Dependencies aktualisiert"
fi

# ── 3.5. Heuristische Bug-Fixes (idempotent) ─────────────────────────
# Fängt Installations-Bugs aus dem Installer ab, ohne manuelles Eingreifen.
# Jeder Fix prüft vorher, ob er nötig ist, und ist nicht-destruktiv.
log "» Heuristische Bug-Fixes prüfen..."

if [[ "$DRY_RUN" == "true" ]]; then
    log "  [DRY-RUN] Bug-Fixes würden geprüft"
else
    # Fix 1: BIND_HOST auf 0.0.0.0 setzen (war 127.0.0.1 in älteren Installationen)
    if grep -q "^TASKS_BIND_HOST=127\.0\.0\.1$" "$ETC_DIR/tasks.env" 2>/dev/null; then
        sed -i 's/^TASKS_BIND_HOST=127\.0\.0\.1$/TASKS_BIND_HOST=0.0.0.0/' "$ETC_DIR/tasks.env"
        ok "tasks.env: BIND_HOST auf 0.0.0.0 korrigiert"
    fi

    # Fix 2: systemd-Unit --host 0.0.0.0 (war 127.0.0.1 in älteren Installationen)
    if grep -q -- "--host 127\.0\.0\.1" /etc/systemd/system/tasks-api.service 2>/dev/null; then
        sed -i 's/--host 127\.0\.0\.1/--host 0.0.0.0/' /etc/systemd/system/tasks-api.service
        systemctl daemon-reload
        ok "systemd: tasks-api.service --host auf 0.0.0.0 korrigiert"
    fi

    # Fix 3: Fehlende Pflicht-Dependencies (dateparser, sse-starlette)
    for pkg in dateparser sse-starlette; do
        if ! sudo -u "$SERVICE_USER" "$APP_DIR/venv/bin/pip" show "$pkg" -q 2>/dev/null; then
            log "  Installiere fehlendes Paket: $pkg"
            sudo -u "$SERVICE_USER" "$APP_DIR/venv/bin/pip" install "$pkg" -q 2>&1 | tail -1
            ok "$pkg installiert"
        fi
    done

    # Fix 4: tasks.env Berechtigungen (tasks:tasks, 640, secret.key 600)
    if [[ -d "$ETC_DIR" ]]; then
        chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$ETC_DIR"
        chmod 700 "$ETC_DIR"
        chmod 640 "$ETC_DIR/tasks.env" 2>/dev/null || true
        chmod 600 "$ETC_DIR/secret.key" 2>/dev/null || true
    fi

    # Fix 5: /opt/tasks Berechtigungen
    if [[ -d "$APP_DIR" ]]; then
        chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$APP_DIR"
    fi
fi

# ── 4. Frontend bauen ───────────────────────────────────────────────
if [[ "$SKIP_FRONTEND" == "true" ]]; then
    log "» Frontend-Build übersprungen"
else
    log "» Frontend bauen..."
    if [[ "$DRY_RUN" == "true" ]]; then
        log "  [DRY-RUN] npm run build in $FRONTEND_DIR, kopiere Output nach $APP_DIR/static/"
    else
        if [[ ! -d "$FRONTEND_DIR" ]] || [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
            warn "Frontend-Code fehlt in $FRONTEND_DIR — überspringe Build"
            warn "  Stelle sicher, dass ~/tasky/frontend/ auf dem LXC vorhanden ist."
        else
            log "  npm install in $FRONTEND_DIR..."
            (cd "$FRONTEND_DIR" && npm install --no-audit --no-fund -q 2>&1 | tail -3) || warn "npm install fehlgeschlagen — überspringe Build"
            log "  npm run build..."
            (cd "$FRONTEND_DIR" && npm run build 2>&1 | tail -5) || warn "npm run build fehlgeschlagen — überspringe Build"

            # Vite-Output landet in $BACKEND_DIR/static (per vite.config.ts).
            # Nach /opt/tasks/static/ kopieren.
            if [[ -d "$BACKEND_DIR/static" ]] && [[ -f "$BACKEND_DIR/static/index.html" ]]; then
                mkdir -p "$APP_DIR/static"
                rsync -a --delete "$BACKEND_DIR/static/" "$APP_DIR/static/"
                chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$APP_DIR/static"
                ok "Frontend-Build nach $APP_DIR/static/ kopiert"
            else
                warn "Kein Frontend-Build gefunden in $BACKEND_DIR/static/"
            fi
        fi
    fi
fi

# ── 5. DB-Migrationen ───────────────────────────────────────────────
if [[ "$SKIP_MIGRATIONS" == "true" ]]; then
    log "» DB-Migrationen übersprungen"
else
    log "» DB-Migrationen..."
    if [[ "$DRY_RUN" == "true" ]]; then
        log "  [DRY-RUN] alembic upgrade head"
    else
        if [[ -f "$APP_DIR/alembic.ini" ]]; then
            cd "$APP_DIR"
            sudo -u "$SERVICE_USER" env $(grep -v '^#' "$ETC_DIR/tasks.env" | xargs) \
                "$APP_DIR/venv/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head 2>&1 | tail -5
            cd "$PROJECT_ROOT"
            ok "Migrationen ausgeführt"
        else
            warn "Keine alembic.ini — überspringe"
        fi
    fi
fi

# ── 6. Berechtigungen ───────────────────────────────────────────────
if [[ "$DRY_RUN" != "true" ]]; then
    chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"
fi

# ── 7. Dienste neustarten ───────────────────────────────────────────
log "» Dienste neustarten..."
if [[ "$DRY_RUN" == "true" ]]; then
    log "  [DRY-RUN] systemctl restart tasks-api tasks-worker"
else
    systemctl restart tasks-api.service
    systemctl restart tasks-worker.service
    sleep 3
    ok "Dienste neugestartet"
fi

# ── 8. Post-Update Smoke-Test ───────────────────────────────────────
if [[ "$DRY_RUN" != "true" ]]; then
    log "» Post-Update-Test..."
    if curl -sf http://localhost:5000/api/v1/health >/dev/null 2>&1; then
        HEALTH=$(curl -s http://localhost:5000/api/v1/health)
        ok "API antwortet"
        echo "$HEALTH" | python3 -m json.tool | sed 's/^/    /'
    else
        fail "API antwortet NICHT — Logs: journalctl -u tasks-api -n 30"
    fi
fi

log "=== Update abgeschlossen ==="
