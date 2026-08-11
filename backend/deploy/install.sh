#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# MyTasks — Installation (Phase 0: Fundament)
# Läuft auf Debian 13 LXC, erwartet root-Rechte via sudo.
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_DIR="/opt/tasks"
DATA_DIR="/var/lib/tasks"
BACKUP_DIR="$DATA_DIR/backups"
ETC_DIR="/etc/tasks"
SERVICE_USER="tasks"
SERVICE_GROUP="tasks"
PYTHON_BIN="python3"

echo "=== MyTasks Installation ==="
echo

# ── 1. Systemvoraussetzungen prüfen ───────────────────────────────────
echo "» Prüfe Systemvoraussetzungen..."
if [[ $EUID -ne 0 ]]; then
    echo "FEHLER: Dieses Skript benötigt root-Rechte. Bitte via sudo ausführen."
    exit 1
fi

if ! command -v "$PYTHON_BIN" &>/dev/null; then
    echo "FEHLER: $PYTHON_BIN nicht gefunden. Bitte Python 3.13 installieren."
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_BIN" -c "import sys; print(sys.version_info[:2])")
if [[ "$PYTHON_VERSION" != "(3, 13)" ]]; then
    echo "WARNUNG: Erwartet Python 3.13, gefunden: $PYTHON_VERSION"
fi

# ── 2. Systembenutzer anlegen ─────────────────────────────────────────
echo "» Lege Systembenutzer '$SERVICE_USER' an..."
if id "$SERVICE_USER" &>/dev/null; then
    echo "   Benutzer '$SERVICE_USER' existiert bereits — überspringe."
else
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    echo "   Benutzer '$SERVICE_USER' angelegt."
fi

# ── 3. Verzeichnisse anlegen ──────────────────────────────────────────
echo "» Erstelle Verzeichnisse..."

mkdir -p "$APP_DIR/app" "$APP_DIR/app/api" "$APP_DIR/app/core" "$APP_DIR/static"
mkdir -p "$DATA_DIR" "$BACKUP_DIR"
mkdir -p "$ETC_DIR"

# Python-Quellen kopieren
echo "» Kopiere Applikationscode nach $APP_DIR/app..."
rsync -a --delete "$PROJECT_ROOT/app/" "$APP_DIR/app/"
rsync -a --delete "$PROJECT_ROOT/pyproject.toml" "$APP_DIR/"

# ── 4. Secret Key generieren ──────────────────────────────────────────
echo "» Generiere Secret Key..."
if [[ -f "$ETC_DIR/secret.key" ]]; then
    echo "   $ETC_DIR/secret.key existiert bereits — überspringe (nicht überschreiben)."
else
    "$PYTHON_BIN" -c "import secrets; print(secrets.token_urlsafe(64))" > "$ETC_DIR/secret.key"
    chmod 600 "$ETC_DIR/secret.key"
    chown "$SERVICE_USER":"$SERVICE_GROUP" "$ETC_DIR/secret.key"
    echo "   Secret Key erstellt."
fi

# ── 5. Environment-Datei ──────────────────────────────────────────────
echo "» Installiere Environment-Datei..."
if [[ -f "$ETC_DIR/tasks.env" ]]; then
    echo "   $ETC_DIR/tasks.env existiert bereits — hole Diff ein."
    if ! diff -q "$SCRIPT_DIR/tasks.env" "$ETC_DIR/tasks.env" &>/dev/null; then
        echo "   ⚠ Unterschiede zwischen $SCRIPT_DIR/tasks.env und $ETC_DIR/tasks.env"
        echo "   Manuell mergen oder mit --force-env überschreiben."
    fi
else
    cp "$SCRIPT_DIR/tasks.env" "$ETC_DIR/tasks.env"
    chmod 640 "$ETC_DIR/tasks.env"
    chown "$SERVICE_USER":"$SERVICE_GROUP" "$ETC_DIR/tasks.env"
    echo "   $ETC_DIR/tasks.env installiert."
fi

# ── 6. Python Virtual Environment ─────────────────────────────────────
echo "» Richte Python Virtual Environment ein..."
if [[ -d "$APP_DIR/venv" ]]; then
    echo "   venv existiert bereits — lösche für Neuinstallation."
    rm -rf "$APP_DIR/venv"
fi
"$PYTHON_BIN" -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install -e "$APP_DIR[dev]" 2>&1 | tail -3
echo "   venv installiert."

# ── 7. Berechtigungen setzen ──────────────────────────────────────────
echo "» Setze Berechtigungen..."
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$APP_DIR"
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$DATA_DIR"
chmod 700 "$ETC_DIR"
chmod 640 "$ETC_DIR/tasks.env"
chmod 600 "$ETC_DIR/secret.key"
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$ETC_DIR"

# ── 8. systemd Units installieren ─────────────────────────────────────
echo "» Installiere systemd Units..."
cp "$SCRIPT_DIR/tasks-api.service" /etc/systemd/system/
cp "$SCRIPT_DIR/tasks-worker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable tasks-api.service
systemctl enable tasks-worker.service

# ── 9. Dienste starten ────────────────────────────────────────────────
echo "» Starte Dienste..."
systemctl restart tasks-api.service
systemctl restart tasks-worker.service

sleep 2

# ── 10. Smoke-Test ────────────────────────────────────────────────────
echo
echo "» Smoke-Test: Prüfe /api/v1/health..."
if curl -sf http://localhost:5000/api/v1/health > /dev/null 2>&1; then
    echo "   ✅ Health-Endpunkt antwortet erfolgreich."
    curl -s http://localhost:5000/api/v1/health | python3 -m json.tool 2>/dev/null || true
else
    echo "   ❌ Health-Endpunkt antwortet nicht."
    echo "   Prüfe: journalctl -u tasks-api -n 50"
fi

echo
echo "=== Installation abgeschlossen ==="
echo "   Status: systemctl status tasks-api tasks-worker"
echo "   Logs:   journalctl -u tasks-api -f"
echo "   Health: curl http://localhost:5000/api/v1/health"
echo "   Config: $ETC_DIR/tasks.env"
