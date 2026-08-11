#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# MyTasks — Deinstallation
# Entfernt systemd-Units, Verzeichnisse, Systembenutzer, Konfiguration.
# Die SQLite-Datenbank wird als Backup nach /root/kapture-backup-<datum>
# kopiert, falls sie existiert.
# ──────────────────────────────────────────────────────────────────────

APP_DIR="/opt/tasks"
DATA_DIR="/var/lib/tasks"
ETC_DIR="/etc/tasks"
SERVICE_USER="tasks"
BACKUP_ROOT="/root/kapture-backup-$(date +%Y%m%d-%H%M%S)"

[[ $EUID -eq 0 ]] || { echo "FEHLER: root-Rechte benötigt"; exit 1; }

echo "=== MyTasks Deinstallation ==="
echo
echo "  Entfernt:    $APP_DIR"
echo "              $DATA_DIR"
echo "              $ETC_DIR"
echo "              Systembenutzer '$SERVICE_USER'"
echo "              systemd-Units tasks-api, tasks-worker"
echo "              Nginx-Site (falls von Installer angelegt)"
echo

# Datenbank sichern
if [[ -f "$DATA_DIR/tasks.db" ]]; then
    mkdir -p "$BACKUP_ROOT"
    cp -a "$DATA_DIR/tasks.db"* "$BACKUP_ROOT/" 2>/dev/null || true
    echo "  DB-Backup:  $BACKUP_ROOT/"
fi

# Dienste stoppen und deaktivieren
echo "» Stoppe Dienste..."
systemctl stop tasks-api.service tasks-worker.service 2>/dev/null || true
systemctl disable tasks-api.service tasks-worker.service 2>/dev/null || true

# Units entfernen
echo "» Entferne systemd-Units..."
rm -f /etc/systemd/system/tasks-api.service
rm -f /etc/systemd/system/tasks-worker.service
systemctl daemon-reload

# Nginx-Site (falls vorhanden)
if [[ -L /etc/nginx/sites-enabled/kapture ]] || [[ -f /etc/nginx/sites-available/kapture ]]; then
    echo "» Entferne Nginx-Konfiguration..."
    rm -f /etc/nginx/sites-enabled/kapture
    rm -f /etc/nginx/sites-available/kapture
    nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true
fi

# Verzeichnisse entfernen
echo "» Entferne Anwendungsverzeichnisse..."
rm -rf "$APP_DIR"
rm -rf "$DATA_DIR"
rm -rf "$ETC_DIR"

# Systembenutzer entfernen
if id "$SERVICE_USER" &>/dev/null; then
    echo "» Entferne Systembenutzer '$SERVICE_USER'..."
    userdel "$SERVICE_USER" 2>/dev/null || true
fi

# Ollama wird NICHT entfernt (vielleicht für andere Zwecke genutzt)
echo
echo "  Hinweis: Ollama wurde NICHT deinstalliert."
echo "           Bei Bedarf: systemctl stop ollama && apt remove ollama"
echo
echo "=== Deinstallation abgeschlossen ==="
if [[ -d "$BACKUP_ROOT" ]]; then
    echo "  DB-Backup:  $BACKUP_ROOT"
fi
