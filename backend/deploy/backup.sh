#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# MyTasks — Nächtliches Backup der SQLite-Datenbank
# Verwendet VACUUM INTO (konsistent im WAL-Modus, anders als cp).
# Aufbewahrung: 14 Tages- + 8 Wochensicherungen.
# Installieren:  crontab -e  →  0 3 * * * /opt/tasks/deploy/backup.sh
# ──────────────────────────────────────────────────────────────────────

DATA_DIR="/var/lib/tasks"
BACKUP_DIR="$DATA_DIR/backups"
DB="$DATA_DIR/tasks.db"
SERVICE_USER="tasks"
KEEP_DAILY=14
KEEP_WEEKLY=8

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"
chown "$SERVICE_USER":"$SERVICE_USER" "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

DATE=$(date +%Y%m%d)
DOW=$(date +%u)

# Tägliches Backup via VACUUM INTO (konsistent trotz WAL)
DEST="$BACKUP_DIR/daily/tasks-$DATE.db"
sqlite3 "$DB" "VACUUM INTO '$DEST'"
chown "$SERVICE_USER":"$SERVICE_USER" "$DEST"

# Wöchentliches Backup (Sonntag = Tag 7)
if [[ "$DOW" == "7" ]]; then
    cp "$DEST" "$BACKUP_DIR/weekly/tasks-$DATE.db"
    chown "$SERVICE_USER":"$SERVICE_USER" "$BACKUP_DIR/weekly/tasks-$DATE.db"
fi

# Alte Backups aufräumen
find "$BACKUP_DIR/daily" -name "tasks-*.db" -mtime "+$KEEP_DAILY" -delete
find "$BACKUP_DIR/weekly" -name "tasks-*.db" -mtime "+$((KEEP_WEEKLY * 7))" -delete

echo "Backup OK: $DEST"
