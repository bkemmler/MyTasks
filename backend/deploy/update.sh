#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# MyTasks — Update
# Kopiert neuen Code, installiert dependencies, führt DB-Migrationen aus,
# startet Dienste neu.
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_DIR="/opt/tasks"
ETC_DIR="/etc/tasks"
SERVICE_USER="tasks"

DRY_RUN=0
SKIP_MIGRATIONS=0

usage() {
    echo "Usage: $0 [--dry-run] [--skip-migrations]"
    echo
    echo "  --dry-run          Zeigt an, was passieren würde, ohne Änderungen"
    echo "  --skip-migrations  Führt keine DB-Migrationen aus"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=1; shift ;;
        --skip-migrations) SKIP_MIGRATIONS=1; shift ;;
        -h|--help)    usage ;;
        *)            echo "Unbekannte Option: $1"; usage ;;
    esac
done

echo "=== MyTasks Update ==="
if [[ $DRY_RUN -eq 1 ]]; then
    echo "*** DRY RUN — keine Änderungen werden vorgenommen ***"
fi
echo

# ── 1. Root-Prüfung ───────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "FEHLER: Dieses Skript benötigt root-Rechte."
    exit 1
fi

# ── 2. Pre-Update Status ──────────────────────────────────────────────
echo "» Pre-Update Status..."
CURRENT_HEALTH=""
if curl -sf http://localhost:5000/api/v1/health > /dev/null 2>&1; then
    CURRENT_HEALTH=$(curl -s http://localhost:5000/api/v1/health)
    echo "   Aktuell laufende Version: $(echo "$CURRENT_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo '?')"
else
    echo "   ⚠ Health-Endpunkt derzeit nicht erreichbar."
fi

# ── 3. Code aktualisieren ─────────────────────────────────────────────
echo "» Aktualisiere Applikationscode..."
if [[ $DRY_RUN -eq 1 ]]; then
    echo "   [DRY-RUN] rsync -a --delete $PROJECT_ROOT/app/ $APP_DIR/app/"
    echo "   [DRY-RUN] rsync -a --delete $PROJECT_ROOT/pyproject.toml $APP_DIR/"
else
    rsync -a --delete "$PROJECT_ROOT/app/" "$APP_DIR/app/"
    rsync -a "$PROJECT_ROOT/pyproject.toml" "$APP_DIR/"
    echo "   Code aktualisiert."
fi

# ── 4. Dependencies aktualisieren ────────────────────────────────────
echo "» Aktualisiere Python-Dependencies..."
if [[ $DRY_RUN -eq 1 ]]; then
    echo "   [DRY-RUN] $APP_DIR/venv/bin/pip install -e $APP_DIR"
else
    "$APP_DIR/venv/bin/pip" install -e "$APP_DIR" -q 2>&1 | tail -3
    echo "   Dependencies aktualisiert."
fi

# ── 5. Environment prüfen ─────────────────────────────────────────────
echo "» Prüfe Environment..."
if [[ -f "$SCRIPT_DIR/tasks.env" ]]; then
    if ! diff -q "$SCRIPT_DIR/tasks.env" "$ETC_DIR/tasks.env" &>/dev/null; then
        echo "   ⚠ $SCRIPT_DIR/tasks.env weicht von $ETC_DIR/tasks.env ab."
        echo "   Neue Variablen aus $SCRIPT_DIR/tasks.env manuell übernehmen falls nötig."
        if [[ $DRY_RUN -eq 0 ]]; then
            echo
            echo "   --- Neue/geänderte Zeilen in $SCRIPT_DIR/tasks.env ---"
            diff "$ETC_DIR/tasks.env" "$SCRIPT_DIR/tasks.env" || true
        fi
    else
        echo "   Environment-Dateien identisch."
    fi
fi

# ── 6. DB-Migrationen ────────────────────────────────────────────────
echo "» DB-Migrationen..."
if [[ $SKIP_MIGRATIONS -eq 1 ]]; then
    echo "   Übersprungen (--skip-migrations)."
elif [[ $DRY_RUN -eq 1 ]]; then
    echo "   [DRY-RUN] $APP_DIR/venv/bin/alembic -c $APP_DIR/alembic.ini upgrade head"
else
    if [[ -f "$APP_DIR/alembic.ini" ]]; then
        "$APP_DIR/venv/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head
        echo "   Migrationen ausgeführt."
    else
        echo "   Keine alembic.ini gefunden — überspringe."
    fi
fi

# ── 7. Dienste neustarten ─────────────────────────────────────────────
echo "» Dienste neustarten..."
if [[ $DRY_RUN -eq 1 ]]; then
    echo "   [DRY-RUN] systemctl restart tasks-api.service tasks-worker.service"
else
    systemctl restart tasks-api.service
    systemctl restart tasks-worker.service
    sleep 2
    echo "   Dienste neugestartet."
fi

# ── 8. Post-Update Prüfung ────────────────────────────────────────────
echo
echo "» Post-Update Smoke-Test..."
if [[ $DRY_RUN -eq 0 ]]; then
    if curl -sf http://localhost:5000/api/v1/health > /dev/null 2>&1; then
        NEW_HEALTH=$(curl -s http://localhost:5000/api/v1/health)
        echo "   ✅ Health-Endpunkt antwortet."
        echo "   Neue Version: $(echo "$NEW_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo '?')"
    else
        echo "   ❌ Health-Endpunkt antwortet NICHT — Rollback prüfen!"
        echo "   journalctl -u tasks-api -n 30"
        exit 1
    fi
fi

echo
echo "=== Update abgeschlossen ==="
