#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# MyTasks — Vollinstallation
#
# Installiert auf einem frischen Debian 13 LXC:
#   - System-Pakete, Python 3.13, Node.js 20
#   - Ollama + LLM-Modell (optional)
#   - Backend (FastAPI) + Python-Dependencies
#   - Frontend (React) + npm-Build → /opt/tasks/static
#   - systemd-Units (api + worker)
#   - Systembenutzer 'tasks', Verzeichnisse, Secret Key
#   - Initiale DB-Migrationen
#
# Aufruf:  sudo ./install.sh
#          sudo ./install.sh --skip-ollama
#          sudo ./install.sh --with-frontend-dev
#
# Voraussetzung: Root-Rechte (sudo), Debian 13, ca. 5 GB freier Speicher.
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

APP_DIR="/opt/tasks"
DATA_DIR="/var/lib/tasks"
BACKUP_DIR="$DATA_DIR/backups"
ETC_DIR="/etc/tasks"
SERVICE_USER="tasks"
SERVICE_GROUP="tasks"

OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="gemma4:e2b"
INSTALL_OLLAMA=false
INSTALL_FRONTEND=true
FORCE_REBUILD=false

# ── Argumente parsen ──────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-ollama)      INSTALL_OLLAMA=true; shift ;;
        --skip-frontend)       INSTALL_FRONTEND=false; shift ;;
        --ollama-url)          OLLAMA_BASE_URL="$2"; shift 2 ;;
        --ollama-model)        OLLAMA_MODEL="$2"; shift 2 ;;
        --force)               FORCE_REBUILD=true; shift ;;
        -h|--help)
            cat <<EOF
MyTasks Installer

Optionen:
  --install-ollama       Ollama lokal installieren (nur wenn kein Remote-Ollama)
  --skip-frontend        Frontend-Build überspringen (nur Backend)
  --ollama-url URL       Ollama-URL (Default: http://localhost:11434, REQUIRED wenn remote)
  --ollama-model NAME    LLM-Modell (Default: gemma4:e2b)
  --force                Komplett neu installieren
  -h, --help             Diese Hilfe

Standardmäßig wird KEIN Ollama installiert. Wenn Ollama auf einem anderen
Server läuft, setze --ollama-url http://anderer-server:11434.
EOF
            exit 0 ;;
        *) echo "Unbekannte Option: $1"; exit 1 ;;
    esac
done

# ── Hilfsfunktionen ──────────────────────────────────────────────────
log()   { printf '\033[1;34m%s\033[0m\n' "$1"; }
ok()    { printf '  \033[32m✅ %s\033[0m\n' "$1"; }
warn()  { printf '  \033[33m⚠  %s\033[0m\n' "$1"; }
fail()  { printf '  \033[31m❌ %s\033[0m\n' "$1"; exit 1; }
hdr()   { printf '\n\033[1;36m=== %s ===\033[0m\n' "$1"; }

trap 'fail "Installation abgebrochen in Zeile $LINENO"' ERR

# ── 0. Vorbereitungen ──────────────────────────────────────────────────
hdr "0. Vorbereitungen"

[[ $EUID -eq 0 ]] || fail "Dieses Skript benötigt root-Rechte. Bitte mit sudo aufrufen."

if [[ ! -f /etc/debian_version ]]; then
    warn "Dieses System ist kein Debian. Abbruch."
    fail "Nur für Debian 13 getestet."
fi

DEBIAN_VERSION=$(cat /etc/debian_version | cut -d. -f1)
if [[ "$DEBIAN_VERSION" != "13" ]]; then
    warn "Debian-Version $DEBIAN_VERSION erkannt, Skript ist für 13 (Trixie) optimiert."
fi

log "Bash: $BASH_VERSION"
log "Projekt-Root: $PROJECT_ROOT"
log "Backend:      $BACKEND_DIR"
log "Frontend:     $FRONTEND_DIR"

# ── 1. System-Pakete ───────────────────────────────────────────────────
hdr "1. System-Pakete installieren"

export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    python3.13 python3.13-venv python3.13-dev python3-pip \
    build-essential libffi-dev libssl-dev \
    curl ca-certificates gnupg lsb-release \
    sqlite3 rsync git \
    nginx-light 2>/dev/null || apt-get install -y -qq --no-install-recommends \
    python3 python3-venv python3-dev python3-pip \
    build-essential libffi-dev libssl-dev \
    curl ca-certificates gnupg lsb-release \
    sqlite3 rsync git

ok "System-Pakete installiert"

PYTHON_BIN=python3
if command -v python3.13 &>/dev/null; then
    PYTHON_BIN=python3.13
fi
PY_VERSION=$($PYTHON_BIN -c "import sys; print(sys.version_info[:2])")
log "Python: $PY_VERSION"

# ── 2. Node.js 20 ──────────────────────────────────────────────────────
hdr "2. Node.js 20 LTS installieren"

if command -v node &>/dev/null; then
    NODE_VERSION=$(node --version | cut -d. -f1 | tr -d 'v')
    if [[ "$NODE_VERSION" -ge 20 ]]; then
        ok "Node.js bereits installiert: $(node --version)"
    else
        warn "Node.js $(node --version) zu alt, installiere v20"
        rm -f /etc/apt/sources.list.d/nodesource.list
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
        apt-get install -y -qq nodejs
    fi
else
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
    apt-get install -y -qq nodejs
    ok "Node.js $(node --version) installiert"
fi

log "npm: $(npm --version)"

# ── 3. Ollama prüfen ──────────────────────────────────────────────────
hdr "3. Ollama prüfen"

if [[ "$INSTALL_OLLAMA" == "true" ]]; then
    if command -v ollama &>/dev/null; then
        ok "Ollama bereits installiert: $(ollama --version 2>/dev/null | head -1 || echo '?')"
    else
        log "Installiere Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh >/dev/null
        ok "Ollama installiert"
    fi

    if ! systemctl is-active --quiet ollama 2>/dev/null; then
        log "Starte Ollama-Service..."
        systemctl enable ollama 2>/dev/null || true
        systemctl start ollama 2>/dev/null || true
        sleep 3
    fi
else
    log "Keine lokale Ollama-Installation (Remote-Ollama wird verwendet)"
fi

# Erreichbarkeit prüfen
if curl -sf "$OLLAMA_BASE_URL/api/tags" >/dev/null 2>&1; then
    ok "Ollama erreichbar: $OLLAMA_BASE_URL"
    # Modell-Pull nur wenn lokales Ollama-Binary vorhanden
    if [[ "$INSTALL_OLLAMA" == "true" ]] && command -v ollama &>/dev/null; then
        if ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
            ok "Modell '$OLLAMA_MODEL' bereits vorhanden"
        else
            log "Lade Modell '$OLLAMA_MODEL' herunter (kann dauern)..."
            ollama pull "$OLLAMA_MODEL" || warn "Pull fehlgeschlagen — manuell nachholen: ollama pull $OLLAMA_MODEL"
        fi
    fi
else
    warn "Ollama nicht erreichbar: $OLLAMA_BASE_URL"
    if [[ "$INSTALL_OLLAMA" != "true" ]]; then
        fail "Remote-Ollama unter $OLLAMA_BASE_URL nicht erreichbar. URL prüfen oder --install-ollama für lokale Installation."
    else
        warn "Lokale Installation aktiv — Service startet möglicherweise noch. Fortsetzung."
    fi
fi

# ── 4. Systembenutzer und Verzeichnisse ────────────────────────────────
hdr "4. Systembenutzer und Verzeichnisse"

if id "$SERVICE_USER" &>/dev/null; then
    ok "Benutzer '$SERVICE_USER' existiert"
else
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    ok "Benutzer '$SERVICE_USER' angelegt"
fi

mkdir -p "$APP_DIR" "$APP_DIR/static"
mkdir -p "$DATA_DIR" "$BACKUP_DIR"
mkdir -p "$ETC_DIR"

# ── 5. Backend installieren ───────────────────────────────────────────
hdr "5. Backend installieren"

# Falls vorhandene kaputte Installation: aufräumen
if [[ -d "$APP_DIR" ]] && [[ -d "$APP_DIR/venv" ]] && [[ ! -f "$APP_DIR/pyproject.toml" ]]; then
    warn "Unvollständige Vorinstallation erkannt — räume auf"
    rm -rf "$APP_DIR"
fi

log "Kopiere Backend-Code nach $APP_DIR/..."
rsync -a --delete "$BACKEND_DIR/app/" "$APP_DIR/app/"
cp -f "$BACKEND_DIR/pyproject.toml" "$APP_DIR/"
cp -f "$BACKEND_DIR/evaluate.py" "$APP_DIR/" 2>/dev/null || true
cp -f "$BACKEND_DIR/eval_set.json" "$APP_DIR/" 2>/dev/null || true
cp -rf "$BACKEND_DIR/alembic" "$APP_DIR/"
cp -f "$BACKEND_DIR/alembic.ini" "$APP_DIR/" 2>/dev/null || true
ok "Code kopiert"

# Tests und dev-Dateien ausschließen
rm -rf "$APP_DIR/tests" "$APP_DIR/.venv" 2>/dev/null || true

log "Erstelle Python venv..."
if [[ -d "$APP_DIR/venv" ]]; then
    rm -rf "$APP_DIR/venv"
fi
$PYTHON_BIN -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip setuptools wheel -q

# Sanity-Check: pyproject.toml muss einen [build-system]-Block haben
if ! grep -q "^\[build-system\]" "$APP_DIR/pyproject.toml"; then
    fail "pyproject.toml fehlt [build-system]-Block. Bitte aktuelle Version kopieren."
fi

log "Installiere Python-Dependencies..."
if ! "$APP_DIR/venv/bin/pip" install -e "$APP_DIR" 2>&1 | tail -20; then
    fail "pip install fehlgeschlagen. Siehe Output oben."
fi
ok "Backend-Dependencies installiert"

# ── 6. Frontend bauen ────────────────────────────────────────────────
hdr "6. Frontend bauen"

if [[ "$INSTALL_FRONTEND" == "true" ]]; then
    if [[ ! -d "$FRONTEND_DIR" ]]; then
        fail "Frontend-Verzeichnis $FRONTEND_DIR existiert nicht"
    fi

    log "Kopiere Frontend-Code..."
    rsync -a --delete "$FRONTEND_DIR/" "$APP_DIR/frontend-build/"
    rm -rf "$APP_DIR/frontend-build/node_modules" "$APP_DIR/frontend-build/dist"

    log "npm install (kann dauern)..."
    cd "$APP_DIR/frontend-build"
    npm install --no-audit --no-fund 2>&1 | tail -3
    ok "npm install OK"

    log "Vite production build..."
    npm run build 2>&1 | tail -10
    ok "Frontend-Build in $APP_DIR/static/"

    # Build-Inputs aufräumen
    rm -rf "$APP_DIR/frontend-build"
    cd "$PROJECT_ROOT"
else
    log "Frontend-Build übersprungen"
    # statisches Verzeichnis leer anlegen falls nicht vorhanden
    mkdir -p "$APP_DIR/static"
    cat > "$APP_DIR/static/index.html" <<EOF
<!doctype html><html><head><meta charset="utf-8"><title>MyTasks</title></head>
<body><h1>MyTasks Backend aktiv</h1>
<p>Frontend wurde nicht installiert. <code>--skip-frontend</code> wurde gesetzt.</p>
<p>API: <a href="/api/v1/health">/api/v1/health</a></p></body></html>
EOF
fi

# ── 7. Konfiguration ──────────────────────────────────────────────────
hdr "7. Konfiguration und Secret Key"

# Secret Key (neu oder behalten)
if [[ -f "$ETC_DIR/secret.key" ]] && [[ "$FORCE_REBUILD" != "true" ]]; then
    ok "Secret Key existiert bereits"
else
    $PYTHON_BIN -c "import secrets; print(secrets.token_urlsafe(64))" > "$ETC_DIR/secret.key"
    chmod 600 "$ETC_DIR/secret.key"
    chown "$SERVICE_USER":"$SERVICE_GROUP" "$ETC_DIR/secret.key"
    ok "Neuer Secret Key generiert"
fi

# Environment-Datei
APP_VERSION=$(python3 -c "
import re, sys
try:
    text = open('$BACKEND_DIR/app/__init__.py').read()
    m = re.search(r'__version__\s*=\s*[\"\\\']([^\"\\\']+)[\"\\\']', text)
    print(m.group(1) if m else '0.0.0')
except Exception:
    print('0.0.0')
" 2>/dev/null || echo "0.0.0")

cat > "$ETC_DIR/tasks.env" <<EOF
TASKS_DATABASE_URL=sqlite+aiosqlite:///$DATA_DIR/tasks.db
TASKS_BIND_HOST=0.0.0.0
TASKS_BIND_PORT=5000
TASKS_LOG_LEVEL=INFO
TASKS_SECRET_KEY_FILE=$ETC_DIR/secret.key
TASKS_OLLAMA_BASE_URL=$OLLAMA_BASE_URL
TASKS_OLLAMA_MODEL=$OLLAMA_MODEL
TASKS_APP_VERSION=$APP_VERSION
TASKS_RATE_LIMIT_ENABLED=true
TASKS_WORKER_ENABLED=true
EOF
chmod 640 "$ETC_DIR/tasks.env"
chown "$SERVICE_USER":"$SERVICE_GROUP" "$ETC_DIR/tasks.env"
ok "Environment-Datei geschrieben: $ETC_DIR/tasks.env"

# ── 8. systemd-Units ─────────────────────────────────────────────────
hdr "8. systemd-Units installieren"

# Bestimmen, ob wir den Worker als separate Unit oder im API-Prozess laufen lassen.
# Da das Konzept zwei Prozesse vorsieht und der Worker im API-Prozess experimentell
# hinzugefügt wurde, behalten wir bei der Standardinstallation den separaten Worker.
cat > /etc/systemd/system/tasks-api.service <<EOF
[Unit]
Description=MyTasks API Server
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5000 --proxy-headers --no-access-log
EnvironmentFile=$ETC_DIR/tasks.env
Restart=on-failure
RestartSec=5

NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=$APP_DIR $DATA_DIR
ReadOnlyPaths=$ETC_DIR

LimitNOFILE=8192

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/tasks-worker.service <<EOF
[Unit]
Description=MyTasks Worker (LLM Jobs + Scheduler)
After=network-online.target tasks-api.service
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python -m app.worker
EnvironmentFile=$ETC_DIR/tasks.env
Restart=on-failure
RestartSec=10

NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=$APP_DIR $DATA_DIR
ReadOnlyPaths=$ETC_DIR

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable tasks-api.service tasks-worker.service
ok "systemd-Units installiert"

# ── 9. Berechtigungen ────────────────────────────────────────────────
hdr "9. Berechtigungen"

# Verzeichnisse dem Service-User übereignen (rekursiv, damit Dateien lesbar sind)
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$APP_DIR"
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$DATA_DIR"
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$ETC_DIR"

# Modi setzen (nach chown, sonst würden chown-rechte überschrieben)
chmod 700 "$ETC_DIR"
chmod 640 "$ETC_DIR/tasks.env"
chmod 600 "$ETC_DIR/secret.key"
ok "Berechtigungen gesetzt"

# ── 10. Datenbank-Migration ──────────────────────────────────────────
hdr "10. Datenbank-Migration"

# Initialen Admin einmalig beim ersten Start erzeugen
# (geschieht unten beim Smoke-Test via init_db)

# ── 11. Dienste starten ──────────────────────────────────────────────
hdr "11. Dienste starten"

systemctl restart tasks-api.service
systemctl restart tasks-worker.service
sleep 3

# ── 12. Smoke-Test ───────────────────────────────────────────────────
hdr "12. Smoke-Test"

if curl -sf http://localhost:5000/api/v1/health >/dev/null 2>&1; then
    ok "API antwortet"
    curl -s http://localhost:5000/api/v1/health | python3 -m json.tool | sed 's/^/    /'
else
    fail "API antwortet nicht. Logs: journalctl -u tasks-api -n 30"
fi

# Prüfe Ollama-Status
HEALTH=$(curl -s http://localhost:5000/api/v1/health 2>/dev/null)
OLLAMA_STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ollama','?'))" 2>/dev/null || echo "?")
log "Ollama-Status laut API: $OLLAMA_STATUS"

# ── 13. Admin-Nutzer anlegen ─────────────────────────────────────────
hdr "13. Admin-Nutzer anlegen"

if [[ -t 0 ]]; then
    echo
    read -rp "Soll ein Admin-Nutzer angelegt werden? [j/N] " CREATE_ADMIN
    if [[ "$CREATE_ADMIN" =~ ^[jJyY]$ ]]; then
        read -rp "  Username [admin]: " ADMIN_USER
        ADMIN_USER=${ADMIN_USER:-admin}
        while :; do
            read -rsp "  Passwort (mind. 12 Zeichen): " ADMIN_PWD
            echo
            if [[ ${#ADMIN_PWD} -ge 12 ]]; then
                break
            else
                echo "  Zu kurz, nochmal."
            fi
        done

        "$APP_DIR/venv/bin/python" - <<PYEOF
import asyncio
from app.core.database import async_session_factory
from app.models.user import User
from app.core.security import hash_password

async def main():
    async with async_session_factory() as db:
        existing = await db.execute(
            User.__table__.select().where(User.username == "$ADMIN_USER")
        )
        if existing.first():
            print(f"  Nutzer '$ADMIN_USER' existiert bereits, überspringe.")
            return
        u = User(
            username="$ADMIN_USER",
            password_hash=hash_password("$ADMIN_PWD"),
            is_admin=True,
            is_active=True,
            display_name="Administrator",
        )
        db.add(u)
        await db.commit()
        print(f"  Admin '$ADMIN_USER' angelegt.")

asyncio.run(main())
PYEOF
    fi
else
    log "Kein TTY — Admin-Setup übersprungen. Manuell anlegen mit:"
    log "  cd $APP_DIR && venv/bin/python -c 'import asyncio; ...'"
fi

# ── 14. Backup-Cronjob ───────────────────────────────────────────────
hdr "14. Backup-Cronjob (täglich 03:00)"

# Backup-Skript in $APP_DIR/deploy/ ablegen
mkdir -p "$APP_DIR/deploy"
cp -f "$BACKEND_DIR/deploy/backup.sh" "$APP_DIR/deploy/"
cp -f "$BACKEND_DIR/deploy/restore.sh" "$APP_DIR/deploy/"
chmod 755 "$APP_DIR/deploy/backup.sh" "$APP_DIR/deploy/restore.sh"
chown "$SERVICE_USER":"$SERVICE_GROUP" "$APP_DIR/deploy/backup.sh" "$APP_DIR/deploy/restore.sh"

# Cron-Eintrag nur anlegen, wenn noch nicht vorhanden
CRON_LINE="0 3 * * * $APP_DIR/deploy/backup.sh >> /var/log/tasks-backup.log 2>&1"
if crontab -l -u "$SERVICE_USER" 2>/dev/null | grep -qF "backup.sh"; then
    ok "Backup-Cronjob existiert bereits"
else
    (crontab -u "$SERVICE_USER" -l 2>/dev/null || true; echo "$CRON_LINE") | crontab -u "$SERVICE_USER" -
    ok "Backup-Cronjob installiert: 0 3 * * *"
fi

# ── 15. Nginx als Reverse-Proxy (optional) ───────────────────────────
hdr "15. Nginx Reverse-Proxy (optional)"

if command -v nginx &>/dev/null; then
    if [[ ! -f /etc/nginx/sites-available/kapture ]]; then
        cat > /etc/nginx/sites-available/kapture <<EOF
server {
    listen 8080 default_server;
    server_name _;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
        ln -sf /etc/nginx/sites-available/kapture /etc/nginx/sites-enabled/kapture
        rm -f /etc/nginx/sites-enabled/default
        nginx -t && systemctl reload nginx
        ok "Nginx konfiguriert (Port 8080)"
    else
        ok "Nginx-Config existiert bereits"
    fi
else
    log "Nginx nicht installiert — übersprungen"
fi

# ── Abschluss ────────────────────────────────────────────────────────
hdr "Installation abgeschlossen"

cat <<EOF

MyTasks läuft jetzt.

  Web-UI:        http://<server>:5000/
  API:            http://<server>:5000/api/v1/
  Health:         http://<server>:5000/api/v1/health
  Via Nginx:      http://<server>:8080/

  Datenbank:      $DATA_DIR/tasks.db
  Backups:        $BACKUP_DIR/
  Konfiguration:  $ETC_DIR/tasks.env
  Secret Key:     $ETC_DIR/secret.key
  Logs:           journalctl -u tasks-api -f
                  journalctl -u tasks-worker -f

  Status:         systemctl status tasks-api tasks-worker
  Neustart:       systemctl restart tasks-api tasks-worker
  Stoppen:        systemctl stop tasks-api tasks-worker

  Update:         cd $PROJECT_ROOT && sudo ./update.sh

EOF
