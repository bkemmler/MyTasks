#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# MyTasks — Datenbank-Wiederherstellung
#
# Stellt die SQLite-Datenbank aus einem VACUUM INTO-Backup wieder her.
# Der tasks-api/tasks-worker werden vorher gestoppt und danach gestartet.
#
# Aufruf:  sudo ./restore.sh <backup-datei.db>
#          sudo ./restore.sh /var/lib/tasks/backups/daily/tasks-20260809.db
#          sudo ./restore.sh --list
# ──────────────────────────────────────────────────────────────────────

APP_DIR="/opt/tasks"
DATA_DIR="/var/lib/tasks"
DB="$DATA_DIR/tasks.db"
BACKUP_DIR="$DATA_DIR/backups"
SERVICE_USER="tasks"

usage() {
    cat <<EOF
Usage: $0 <backup-datei.db>
       $0 --list

  <backup-datei>    Pfad zu einem VACUUM INTO-Backup (.db)
  --list            Vorhandene Backups anzeigen
  -h, --help        Diese Hilfe
EOF
    exit 1
}

[[ $EUID -eq 0 ]] || { echo "FEHLER: root-Rechte benötigt"; exit 1; }

if [[ "${1:-}" == "--list" ]]; then
    echo "Verfügbare Backups:"
    echo ""
    find "$BACKUP_DIR" -name "tasks-*.db" -printf "%T+ %p\n" 2>/dev/null | sort -r | head -30 || echo "Keine Backups gefunden in $BACKUP_DIR"
    exit 0
fi

BACKUP="${1:-}"
[[ -n "$BACKUP" ]] || usage
[[ -f "$BACKUP" ]] || { echo "FEHLER: $BACKUP existiert nicht"; exit 1; }

echo "=== MyTasks Restore ==="
echo "  DB-Pfad:   $DB"
echo "  Backup:    $BACKUP"
echo "  Größe:     $(du -h "$BACKUP" | cut -f1)"
echo ""

# 1. Dienste stoppen
echo "» Stoppe Dienste..."
systemctl stop tasks-api.service tasks-worker.service 2>/dev/null || true
sleep 1

# 2. Aktuelle DB sichern (als precaution)
SAFETY="$DB.safety-$(date +%Y%m%d-%H%M%S)"
if [[ -f "$DB" ]]; then
    echo "» Sichere aktuelle DB nach $SAFETY"
    cp -a "$DB" "$SAFETY"
    cp -a "$DB-wal" "$SAFETY-wal" 2>/dev/null || true
    cp -a "$DB-shm" "$SAFETY-shm" 2>/dev/null || true
fi

# 3. WAL/Journal-Dateien löschen (VACUUM INTO produziert konsistente DB ohne WAL)
rm -f "$DB" "$DB-wal" "$DB-shm"

# 4. Backup wiederherstellen
echo "» Stelle Backup wieder her..."
cp "$BACKUP" "$DB"
chown "$SERVICE_USER":"$SERVICE_USER" "$DB"
chmod 644 "$DB"

# 5. Integrität prüfen
echo "» Prüfe Integrität..."
INTEGRITY=$(sqlite3 "$DB" "PRAGMA integrity_check;" 2>&1)
if [[ "$INTEGRITY" != "ok" ]]; then
    echo "❌ Integritätsprüfung fehlgeschlagen: $INTEGRITY"
    echo "   Stelle alte DB wieder her aus $SAFETY"
    if [[ -f "$SAFETY" ]]; then
        cp -a "$SAFETY" "$DB"
    fi
    exit 1
fi
echo "  ✅ OK"

# 6. WAL reaktivieren
sqlite3 "$DB" "PRAGMA journal_mode=WAL;" >/dev/null

# 7. Dienste starten
echo "» Starte Dienste..."
systemctl start tasks-api.service tasks-worker.service
sleep 3

# 8. Smoke-Test
echo ""
echo "» Smoke-Test..."
if curl -sf http://localhost:5000/api/v1/health >/dev/null 2>&1; then
    echo "  ✅ API antwortet"
    curl -s http://localhost:5000/api/v1/health | python3 -m json.tool 2>/dev/null | sed 's/^/    /'
else
    echo "  ❌ API antwortet nicht — prüfe: journalctl -u tasks-api -n 10"
fi

echo ""
echo "=== Restore abgeschlossen ==="
echo "  Alte DB (safety): $SAFETY"
echo "  (kann gelöscht werden, wenn alles funktioniert: rm $SAFETY*)"
