#!/usr/bin/env bash
# ==============================================================================
# OpenOptOut Unified Host & Fleet Installer (CLI/TUI) — Roadmap Item 23
#
# Interactive terminal wizard and scriptable installer for single-node
# and distributed cluster environments (Debian/Ubuntu Linux).
#
# Usage:
#   sudo ./deploy/installer/setup.sh [OPTIONS]
#   curl -fsSL https://raw.githubusercontent.com/rlnunez/OpenOptOut/main/install.sh | sudo bash
#
# Non-Interactive / Scriptable Flags:
#   --role <ROLE>         standalone | control-plane | worker (default: prompt or standalone)
#   --db <ENGINE>         sqlite | postgres | sqlcipher (default: sqlite)
#   --db-url <URL>        Existing PostgreSQL connection string
#   --domain <DOMAIN>     Public hostname or domain (default: localhost)
#   --email <EMAIL>       Admin email for automated Let's Encrypt TLS certificates
#   --tls <MODE>          letsencrypt | none (default: none for localhost, or prompt)
#   --queue <REDIS_URL>   Redis transport URL for worker/distributed control plane
#   --worker-id <ID>      Custom worker node identifier (default: worker-<hostname>)
#   --concurrency <N>     Number of parallel worker execution slots (default: 1)
#   --secret-key <KEY>    Shared cluster secret key for envelope signing
#   --install-dir <PATH>  Target directory (default: /opt/openoptout)
#   --unattended, -y      Skip interactive prompts and use provided or default options
#   --update              Pull code changes and rebuild without altering .env or data
#   --skip-nginx          Skip Nginx reverse proxy configuration
#   --skip-tls            Skip Certbot automated TLS acquisition
#   --staging             Use Let's Encrypt staging ACME environment for testing
#   -h, --help            Show this help reference
# ==============================================================================
set -euo pipefail

# ── Paths and Defaults ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

INSTALL_DIR="/opt/openoptout"
SVC_USER="openoptout"
ROLE=""
DB_ENGINE=""
DB_URL=""
DOMAIN=""
ADMIN_EMAIL=""
TLS_MODE=""
REDIS_URL=""
WORKER_ID=""
WORKER_CONCURRENCY=1
SECRET_KEY=""
UNATTENDED=0
UPDATE=0
SKIP_NGINX=0
SKIP_TLS=0
STAGING=0

# Styling
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── Helper Functions ──────────────────────────────────────────────────────────
die()  { printf "${RED}Error: %s${NC}\n" "$*" >&2; exit 1; }
info() { printf "${GREEN}==>${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}Warning: %s${NC}\n" "$*" >&2; }
head() { printf "\n${BOLD}${BLUE}── %s ──${NC}\n" "$*"; }

gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  else
    head -c 32 /dev/urandom | xxd -p
  fi
}

show_help() {
  sed -n '2,28p' "$0"
  exit 0
}

# ── Parse Arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) ROLE="$2"; shift 2 ;;
    --db) DB_ENGINE="$2"; shift 2 ;;
    --db-url) DB_URL="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --email) ADMIN_EMAIL="$2"; shift 2 ;;
    --tls) TLS_MODE="$2"; shift 2 ;;
    --queue|--redis-url) REDIS_URL="$2"; shift 2 ;;
    --worker-id) WORKER_ID="$2"; shift 2 ;;
    --concurrency) WORKER_CONCURRENCY="$2"; shift 2 ;;
    --secret-key) SECRET_KEY="$2"; shift 2 ;;
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    --unattended|--non-interactive|-y|--yes) UNATTENDED=1; shift ;;
    --update) UPDATE=1; shift ;;
    --skip-nginx) SKIP_NGINX=1; shift ;;
    --skip-tls) SKIP_TLS=1; shift ;;
    --staging) STAGING=1; shift ;;
    -h|--help) show_help ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
done

# Normalize role aliases
if [[ "$ROLE" == "ui" ]]; then ROLE="control-plane"; fi

# Root privilege validation
[ "$(id -u)" = 0 ] || die "This installer requires root privileges. Please re-run with sudo."
[ -f "$REPO_ROOT/backend/main.py" ] || die "Cannot find backend/main.py in $REPO_ROOT. Run from within the OpenOptOut repo."

# ── Interactive TUI Wizard ───────────────────────────────────────────────────
# If standard input is a pipe (e.g. curl | bash), redirect input from /dev/tty if available
if [ ! -t 0 ] && [ -e /dev/tty ]; then
  exec < /dev/tty
fi

# Detect whether we have an interactive terminal
IS_INTERACTIVE=0
if [ "$UNATTENDED" = 0 ] && [ "$UPDATE" = 0 ] && [ -t 0 ]; then
  IS_INTERACTIVE=1
fi

# Try to ensure whiptail is present if running interactively on Debian/Ubuntu
if [ "$IS_INTERACTIVE" = 1 ] && ! command -v whiptail >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq >/dev/null 2>&1 || true
    apt-get install -y -qq whiptail >/dev/null 2>&1 || true
  fi
fi

USE_WHIPTAIL=0
if [ "$IS_INTERACTIVE" = 1 ] && command -v whiptail >/dev/null 2>&1 && [ -n "${TERM:-}" ] && [ "${TERM:-}" != "dumb" ]; then
  USE_WHIPTAIL=1
fi

prompt_ansi() {
  local prompt="$1" def="${2:-}" ans=""
  printf "${BOLD}%s${NC} [%s]: " "$prompt" "$def"
  read -r ans || true
  echo "${ans:-$def}"
}

if [ "$IS_INTERACTIVE" = 1 ]; then
  # 1. Cluster Role Selection
  if [ -z "$ROLE" ]; then
    if [ "$USE_WHIPTAIL" = 1 ]; then
      ROLE=$(whiptail --title "OpenOptOut Installer — Role Selection" \
        --menu "Select the cluster deployment role for this node:" 16 75 3 \
        "standalone" "All-in-one: Web UI, API, DB & local browser automation" \
        "control-plane" "Web UI & API server (Excludes browser/X11, saves >1.5GB)" \
        "worker" "Stateless compute node (Playwright Firefox, no Web UI/Nginx)" \
        3>&1 1>&2 2>&3) || die "Installation cancelled."
    else
      echo -e "\n${BOLD}${CYAN}=== OpenOptOut Cluster Role Selection ===${NC}"
      echo "1) standalone    — All-in-one: Web UI, API, database & local browser automation"
      echo "2) control-plane — Web UI, API, Nginx & Redis dispatcher (No browser/X11; saves >1.5GB)"
      echo "3) worker        — Headless worker daemon & Playwright Firefox (No Web UI/Nginx)"
      read -r -p "Enter choice [1-3, default: 1]: " rchoice
      case "${rchoice:-1}" in
        1|standalone) ROLE="standalone" ;;
        2|control-plane|ui) ROLE="control-plane" ;;
        3|worker) ROLE="worker" ;;
        *) ROLE="standalone" ;;
      esac
    fi
  fi

  # 2. Database Selection (For standalone & control-plane)
  if [[ "$ROLE" != "worker" ]] && [ -z "$DB_ENGINE" ]; then
    if [ "$USE_WHIPTAIL" = 1 ]; then
      DB_ENGINE=$(whiptail --title "OpenOptOut Installer — Database Selection" \
        --menu "Select the database engine for this deployment:" 15 70 3 \
        "sqlite" "SQLite: File-based local storage (Zero configuration)" \
        "postgres" "PostgreSQL: Production relational database" \
        "sqlcipher" "SQLCipher: AES-256 encrypted SQLite at rest" \
        3>&1 1>&2 2>&3) || DB_ENGINE="sqlite"
    else
      echo -e "\n${BOLD}${CYAN}=== Database Engine Selection ===${NC}"
      echo "1) sqlite     — Local SQLite database (default, zero configuration)"
      echo "2) postgres   — PostgreSQL relational database"
      echo "3) sqlcipher  — SQLCipher: AES-256 encrypted SQLite database at rest"
      read -r -p "Enter choice [1-3, default: 1]: " dbchoice
      case "${dbchoice:-1}" in
        1|sqlite) DB_ENGINE="sqlite" ;;
        2|postgres) DB_ENGINE="postgres" ;;
        3|sqlcipher) DB_ENGINE="sqlcipher" ;;
        *) DB_ENGINE="sqlite" ;;
      esac
    fi

    if [[ "$DB_ENGINE" == "postgres" ]] && [ -z "$DB_URL" ]; then
      if [ "$USE_WHIPTAIL" = 1 ]; then
        if whiptail --title "PostgreSQL Setup" --yesno "Would you like this installer to automatically install and provision a local PostgreSQL server with secure credentials?" 10 70; then
          DB_AUTO_PG=1
        else
          DB_URL=$(whiptail --title "PostgreSQL Connection String" --inputbox "Enter the PostgreSQL connection URL:" 10 70 "postgresql://openoptout:password@localhost/openoptout" 3>&1 1>&2 2>&3) || true
        fi
      else
        echo -e "\nProvision local PostgreSQL automatically?"
        read -r -p "Auto-install local PostgreSQL? [Y/n]: " pg_ans
        if [[ "${pg_ans:-y}" =~ ^[Yy] ]]; then
          DB_AUTO_PG=1
        else
          DB_URL=$(prompt_ansi "PostgreSQL Connection URL" "postgresql://openoptout:password@localhost/openoptout")
        fi
      fi
    fi
  fi

  # 3. Domain & Web Server (For standalone & control-plane)
  if [[ "$ROLE" != "worker" ]] && [ -z "$DOMAIN" ]; then
    if [ "$USE_WHIPTAIL" = 1 ]; then
      DOMAIN=$(whiptail --title "Domain Configuration" --inputbox "Enter the domain or IP address for OpenOptOut:" 10 70 "localhost" 3>&1 1>&2 2>&3) || DOMAIN="localhost"
    else
      DOMAIN=$(prompt_ansi "Domain or IP address" "localhost")
    fi

    if [[ "$DOMAIN" != "localhost" ]] && [[ "$DOMAIN" != "127.0.0.1" ]] && [ -z "$TLS_MODE" ]; then
      if [ "$USE_WHIPTAIL" = 1 ]; then
        if whiptail --title "Automated TLS (Let's Encrypt)" --yesno "Provision automated TLS/HTTPS certificate with Let's Encrypt (Certbot)?" 10 70; then
          TLS_MODE="letsencrypt"
          ADMIN_EMAIL=$(whiptail --title "Certbot Notification Email" --inputbox "Enter administrator email for SSL certificate renewal alerts:" 10 70 "admin@$DOMAIN" 3>&1 1>&2 2>&3) || ADMIN_EMAIL=""
        else
          TLS_MODE="none"
        fi
      else
        read -r -p "Provision automated Let's Encrypt SSL/TLS certificate? [y/N]: " tls_ans
        if [[ "${tls_ans:-n}" =~ ^[Yy] ]]; then
          TLS_MODE="letsencrypt"
          ADMIN_EMAIL=$(prompt_ansi "Administrator email for TLS alerts" "admin@$DOMAIN")
        else
          TLS_MODE="none"
        fi
      fi
    fi
  fi

  # 4. Distributed Queue Configuration (For worker or control-plane)
  if [[ "$ROLE" == "worker" ]]; then
    if [ -z "$REDIS_URL" ]; then
      if [ "$USE_WHIPTAIL" = 1 ]; then
        REDIS_URL=$(whiptail --title "Distributed Worker Queue" --inputbox "Enter Redis Queue URL connecting to Control Plane:" 10 70 "redis://localhost:6379/0" 3>&1 1>&2 2>&3) || REDIS_URL="redis://localhost:6379/0"
      else
        REDIS_URL=$(prompt_ansi "Redis Queue URL connecting to Control Plane" "redis://localhost:6379/0")
      fi
    fi
    if [ -z "$WORKER_ID" ]; then
      DEF_WID="worker-$(hostname -s 2>/dev/null || echo "node")"
      if [ "$USE_WHIPTAIL" = 1 ]; then
        WORKER_ID=$(whiptail --title "Worker Identifier" --inputbox "Enter unique worker ID:" 10 70 "$DEF_WID" 3>&1 1>&2 2>&3) || WORKER_ID="$DEF_WID"
      else
        WORKER_ID=$(prompt_ansi "Unique Worker ID" "$DEF_WID")
      fi
    fi
    if [ -z "$SECRET_KEY" ]; then
      if [ "$USE_WHIPTAIL" = 1 ]; then
        SECRET_KEY=$(whiptail --title "Cluster Secret Key" --passwordbox "Enter the cluster SECRET_KEY (must match control plane for signature validation):" 10 70 3>&1 1>&2 2>&3) || true
      else
        read -r -s -p "Enter cluster SECRET_KEY (must match control plane): " SECRET_KEY
        echo ""
      fi
    fi
  fi
fi

# Apply fallbacks
ROLE="${ROLE:-standalone}"
DB_ENGINE="${DB_ENGINE:-sqlite}"
DOMAIN="${DOMAIN:-localhost}"
TLS_MODE="${TLS_MODE:-none}"
REDIS_URL="${REDIS_URL:-}"
WORKER_ID="${WORKER_ID:-worker-$(hostname -s 2>/dev/null || echo "node")}"
WORKER_CONCURRENCY="${WORKER_CONCURRENCY:-1}"

head "Installing OpenOptOut Node"
info "Deployment Role:    $ROLE"
info "Target Directory:   $INSTALL_DIR"
if [[ "$ROLE" != "worker" ]]; then
  info "Database Engine:    $DB_ENGINE"
  info "Domain Name:        $DOMAIN"
  info "TLS Mode:           $TLS_MODE"
else
  info "Worker Node ID:     $WORKER_ID"
  info "Worker Concurrency: $WORKER_CONCURRENCY"
  info "Queue Endpoint:     ${REDIS_URL:-in-process}"
fi

# ── 1. System User & Directory Layout ─────────────────────────────────────────
head "Provisioning System User & Storage Directories"
if ! id "$SVC_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SVC_USER"
  info "Created system user: $SVC_USER"
else
  info "System user $SVC_USER already exists."
fi

mkdir -p "$INSTALL_DIR" \
         "$INSTALL_DIR/data" \
         "$INSTALL_DIR/data/screenshots" \
         "$INSTALL_DIR/data/plugins" \
         "$INSTALL_DIR/data/plugin_storage" \
         "$INSTALL_DIR/data/logo" \
         /var/log/openoptout

# Lock down data directory permissions (Roadmap Item 15/23)
chmod 750 "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR/data"

# ── 2. Role-Specialized OS Package Provisioning ───────────────────────────────
head "Installing Operating System Packages (Role: $ROLE)"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq

  # Base packages common to all nodes
  BASE_PKGS=(
    python3 python3-venv python3-dev
    wget curl ca-certificates rsync gcc build-essential
  )

  # Web and identity packages (Only for standalone and control-plane)
  WEB_PKGS=(
    nginx xmlsec1 libldap2-dev libsasl2-dev
  )

  # Browser automation and sandbox packages (Only for standalone and worker)
  BROWSER_PKGS=(
    bubblewrap libseccomp2 python3-seccomp fonts-liberation
    libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3
    libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3
    libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3
    libxrandr2 libxss1 libxtst6 xdg-utils
  )

  PKGS_TO_INSTALL=("${BASE_PKGS[@]}")

  if [[ "$ROLE" == "standalone" || "$ROLE" == "control-plane" ]]; then
    PKGS_TO_INSTALL+=("${WEB_PKGS[@]}")
  fi

  if [[ "$ROLE" == "standalone" || "$ROLE" == "worker" ]]; then
    PKGS_TO_INSTALL+=("${BROWSER_PKGS[@]}")
  fi

  if [[ "$ROLE" == "control-plane" ]]; then
    info "Control Plane role: excluding Playwright Firefox, Bubblewrap, and X11 packages (>1.5GB savings)."
  fi

  if [[ "$ROLE" == "worker" ]]; then
    info "Worker role: excluding Nginx, Node.js, and web interface packages (Headless compute node)."
  fi

  apt-get install -y --no-install-recommends "${PKGS_TO_INSTALL[@]}"
else
  warn "apt-get package manager not detected. Ensure equivalent packages are installed for your distro."
fi

# ── 3. Automated Database Provisioning ─────────────────────────────────────────
if [[ "$ROLE" != "worker" ]]; then
  head "Configuring Database Layer ($DB_ENGINE)"

  if [[ "$DB_ENGINE" == "postgres" ]]; then
    if [ -n "${DB_AUTO_PG:-}" ]; then
      info "Installing and configuring local PostgreSQL server..."
      if command -v apt-get >/dev/null 2>&1; then
        apt-get install -y postgresql postgresql-contrib
        systemctl enable --now postgresql
        PG_PASS="$(gen_secret)"
        sudo -u postgres psql -c "CREATE USER openoptout WITH ENCRYPTED PASSWORD '$PG_PASS';" >/dev/null 2>&1 || \
          sudo -u postgres psql -c "ALTER USER openoptout WITH ENCRYPTED PASSWORD '$PG_PASS';" >/dev/null 2>&1
        sudo -u postgres psql -c "CREATE DATABASE openoptout OWNER openoptout;" >/dev/null 2>&1 || true
        DB_URL="postgresql://openoptout:$PG_PASS@localhost/openoptout"
        info "Local PostgreSQL database 'openoptout' created."
      else
        warn "Cannot auto-install PostgreSQL without apt-get. Defaulting to SQLite."
        DB_URL="sqlite:////$INSTALL_DIR/data/openoptout.db"
      fi
    elif [ -z "$DB_URL" ]; then
      DB_URL="sqlite:////$INSTALL_DIR/data/openoptout.db"
    fi
  elif [[ "$DB_ENGINE" == "sqlcipher" ]]; then
    SQLCIPHER_KEY="$(gen_secret)"
    DB_URL="sqlite:////$INSTALL_DIR/data/openoptout.db"
    info "Generated SQLCipher 256-bit database encryption key."
  else
    DB_URL="sqlite:////$INSTALL_DIR/data/openoptout.db"
    info "Using local SQLite database: $INSTALL_DIR/data/openoptout.db"
  fi
fi

# ── 4. Deploy Backend Application ─────────────────────────────────────────────
head "Deploying Application Code to $INSTALL_DIR/app"
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '*.db' \
  --exclude 'openoptout_settings.json' --exclude 'privacyshield_settings.json' --exclude 'cert_monitor.json' \
  "$REPO_ROOT/backend/" "$INSTALL_DIR/app/"

touch "$INSTALL_DIR/app/__init__.py"
for d in models routers core; do
  [ -d "$INSTALL_DIR/app/$d" ] && touch "$INSTALL_DIR/app/$d/__init__.py"
done

# ── 5. Python Virtual Environment & Dependencies ──────────────────────────────
head "Setting Up Python Virtual Environment"
if [ ! -d "$INSTALL_DIR/venv" ]; then
  python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q

info "Installing Python dependencies (requirements.txt)..."
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/app/requirements.txt" -q

if [[ "$DB_ENGINE" == "sqlcipher" ]]; then
  if [ -f "$INSTALL_DIR/app/requirements-encryption.txt" ]; then
    info "Installing SQLCipher encryption drivers..."
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/app/requirements-encryption.txt" -q || \
      warn "sqlcipher3 compilation failed. Ensure libsqlcipher-dev is installed."
  fi
fi

# Install Playwright browser ONLY for Standalone and Worker roles
if [[ "$ROLE" == "standalone" || "$ROLE" == "worker" ]]; then
  head "Installing Playwright Firefox Browser"
  if ! "$INSTALL_DIR/venv/bin/playwright" install firefox; then
    warn "Playwright Firefox install failed. Opt-out forms will use DryRunExecutor until retry."
  fi
fi

# Compile plugin gRPC stubs if proto is available
PROTO_DIR="$INSTALL_DIR/app/plugins/proto"
if [[ "$ROLE" != "worker" ]] && [ -f "$PROTO_DIR/plugin.proto" ]; then
  if "$INSTALL_DIR/venv/bin/python" -m grpc_tools.protoc -I"$PROTO_DIR" \
    --python_out="$PROTO_DIR" --grpc_python_out="$PROTO_DIR" "$PROTO_DIR/plugin.proto" >/dev/null 2>&1; then
    sed -i 's/^import plugin_pb2 as/from . import plugin_pb2 as/' "$PROTO_DIR/plugin_pb2_grpc.py" 2>/dev/null || true
    touch "$PROTO_DIR/__init__.py" 2>/dev/null || true
  fi
fi

# ── 6. Frontend Build (Standalone & Control Plane) ─────────────────────────────
if [[ "$ROLE" == "standalone" || "$ROLE" == "control-plane" ]]; then
  head "Building React Web UI"
  if command -v npm >/dev/null 2>&1; then
    ( cd "$REPO_ROOT/frontend" && npm ci --silent --legacy-peer-deps && npm run build )
    mkdir -p "$INSTALL_DIR/frontend"
    rsync -a --delete "$REPO_ROOT/frontend/dist/" "$INSTALL_DIR/frontend/dist/"
    info "Web UI built successfully to $INSTALL_DIR/frontend/dist"
  elif [ -d "$REPO_ROOT/frontend/dist" ]; then
    mkdir -p "$INSTALL_DIR/frontend"
    rsync -a --delete "$REPO_ROOT/frontend/dist/" "$INSTALL_DIR/frontend/dist/"
    info "Copied pre-built frontend distribution."
  else
    warn "npm not found. Please install Node.js/npm and build the frontend, or copy pre-built assets to $INSTALL_DIR/frontend/dist."
  fi
fi

# ── 7. Environment Configuration (.env) ───────────────────────────────────────
head "Generating Node Environment Configuration (.env)"
if [ ! -f "$INSTALL_DIR/.env" ] || [ "$UPDATE" = 0 ]; then
  [ -n "$SECRET_KEY" ] || SECRET_KEY="$(gen_secret)"

  cat <<EOF > "$INSTALL_DIR/.env"
# OpenOptOut Cluster Node Configuration
# Generated by OpenOptOut Installer (Roadmap Item 23)
ROLE=$ROLE
SECRET_KEY=$SECRET_KEY
SETTINGS_FILE=$INSTALL_DIR/data/openoptout_settings.json
LOGO_PATH=$INSTALL_DIR/data/logo
EOF

  if [[ "$ROLE" != "worker" ]]; then
    PROTO="http"
    if [[ "$TLS_MODE" == "letsencrypt" ]]; then PROTO="https"; fi
    {
      echo "FRONTEND_URL=$PROTO://$DOMAIN"
      echo "DATABASE_URL=$DB_URL"
      if [ -n "${SQLCIPHER_KEY:-}" ]; then
        echo "SQLCIPHER_KEY=$SQLCIPHER_KEY"
      fi
    } >> "$INSTALL_DIR/.env"
  fi

  if [ -n "$REDIS_URL" ]; then
    echo "REDIS_URL=$REDIS_URL" >> "$INSTALL_DIR/.env"
  fi

  if [[ "$ROLE" == "worker" ]]; then
    {
      echo "WORKER_ID=$WORKER_ID"
      echo "WORKER_CONCURRENCY=$WORKER_CONCURRENCY"
      echo "HEADLESS=true"
    } >> "$INSTALL_DIR/.env"
  fi

  # Record git commit hash if available
  if [ -d "$REPO_ROOT/.git" ] && command -v git >/dev/null 2>&1; then
    COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || true)"
    [ -n "$COMMIT" ] && echo "GIT_COMMIT=$COMMIT" >> "$INSTALL_DIR/.env"
  fi

  chmod 600 "$INSTALL_DIR/.env"
  chown "$SVC_USER:$SVC_USER" "$INSTALL_DIR/.env"
  info "Created $INSTALL_DIR/.env with strict 0600 permissions."
fi

# Set directory permissions
chown -R "$SVC_USER:$SVC_USER" "$INSTALL_DIR" /var/log/openoptout

# ── 8. Zero-Touch Nginx & Reverse Proxy Automation ───────────────────────────
if [[ "$ROLE" == "standalone" || "$ROLE" == "control-plane" ]] && [ "$SKIP_NGINX" = 0 ]; then
  head "Configuring Nginx Reverse Proxy"
  if command -v nginx >/dev/null 2>&1; then
    NGINX_CONF="/etc/nginx/sites-available/openoptout"

    cat <<EOF > "$NGINX_CONF"
# OpenOptOut — Nginx Reverse Proxy Configuration (Roadmap Item 23)
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    root $INSTALL_DIR/frontend/dist;
    index index.html;

    client_max_body_size 50M;

    # Reverse proxy for FastAPI backend with WebSockets and SSE support
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # Disable proxy buffering for Server-Sent Events (SSE) and live log streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # SPA routing fallback
    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # Security defense-in-depth headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
EOF

    # Symlink to sites-enabled
    mkdir -p /etc/nginx/sites-enabled
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/openoptout

    # Test and reload
    if nginx -t >/dev/null 2>&1; then
      systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
      info "Nginx site configured and active for $DOMAIN."
    else
      warn "Nginx syntax test failed. Check $NGINX_CONF."
    fi
  else
    warn "Nginx is not installed; skipping reverse proxy configuration."
  fi
fi

# ── 9. Automated Let's Encrypt TLS (Certbot) ─────────────────────────────────
if [[ "$ROLE" != "worker" ]] && [[ "$TLS_MODE" == "letsencrypt" ]] && [ "$SKIP_TLS" = 0 ]; then
  head "Automated TLS Provisioning via Let's Encrypt"
  if command -v apt-get >/dev/null 2>&1 && ! command -v certbot >/dev/null 2>&1; then
    apt-get install -y certbot python3-certbot-nginx
  fi

  if command -v certbot >/dev/null 2>&1; then
    CERTBOT_ARGS=(--nginx -d "$DOMAIN" --agree-tos --non-interactive --redirect)
    if [ -z "$ADMIN_EMAIL" ]; then
      CERTBOT_ARGS+=(--register-unsafely-without-email)
    else
      CERTBOT_ARGS+=(-m "$ADMIN_EMAIL")
    fi
    if [ "$STAGING" != 0 ]; then
      CERTBOT_ARGS+=(--staging)
    fi

    if certbot "${CERTBOT_ARGS[@]}"; then
      info "TLS certificate successfully acquired for $DOMAIN!"
      sed -i "s|^FRONTEND_URL=.*|FRONTEND_URL=https://$DOMAIN|" "$INSTALL_DIR/.env"
    else
      warn "Certbot automated acquisition failed. Ensure DNS A record points to this server and ports 80/443 are reachable."
    fi
  fi
fi

# ── 10. Systemd Service Deployment & Pre-Flight Health Handoff ───────────────
head "Configuring Systemd Services"

if [[ "$ROLE" == "standalone" || "$ROLE" == "control-plane" ]]; then
  cp "$REPO_ROOT/deploy/native/openoptout-api.service" /etc/systemd/system/openoptout-api.service
  systemctl daemon-reload
  systemctl enable --now openoptout-api
  info "Enabled and started openoptout-api.service"

  # Pre-flight health check
  info "Performing pre-flight health probe (http://127.0.0.1:8000/api/health)..."
  HEALTH_OK=0
  for _ in $(seq 1 15); do
    if curl -fs "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
      HEALTH_OK=1
      break
    fi
    sleep 1
  done

  echo
  echo -e "${GREEN}========================================================================${NC}"
  echo -e "${BOLD}${GREEN}  OpenOptOut ${ROLE^^} Node Deployed Successfully!${NC}"
  echo -e "${GREEN}========================================================================${NC}"
  if [ "$HEALTH_OK" = 1 ]; then
    echo -e "  Status:         ${GREEN}HEALTHY (API online)${NC}"
  else
    echo -e "  Status:         ${YELLOW}INITIALIZING (Check: sudo journalctl -u openoptout-api -f)${NC}"
  fi
  ACCESS_PROTO="http"
  [[ "$TLS_MODE" == "letsencrypt" ]] && ACCESS_PROTO="https"
  echo -e "  Web Access:     ${BOLD}${CYAN}$ACCESS_PROTO://$DOMAIN${NC}"
  echo -e "  Initial Setup:  The first person to register becomes the Super Admin."
  echo -e "  Service Status: sudo systemctl status openoptout-api"
  echo -e "  Live Logs:      sudo journalctl -u openoptout-api -f"
  echo -e "${GREEN}========================================================================${NC}"
fi

if [[ "$ROLE" == "worker" ]]; then
  cp "$REPO_ROOT/deploy/native/openoptout-worker.service" /etc/systemd/system/openoptout-worker.service
  systemctl daemon-reload
  systemctl enable --now openoptout-worker
  info "Enabled and started openoptout-worker.service"

  sleep 2
  echo
  echo -e "${GREEN}========================================================================${NC}"
  echo -e "${BOLD}${GREEN}  OpenOptOut Worker Fleet Node Online!${NC}"
  echo -e "${GREEN}========================================================================${NC}"
  echo -e "  Worker ID:      ${BOLD}${CYAN}$WORKER_ID${NC}"
  echo -e "  Concurrency:    $WORKER_CONCURRENCY concurrent slot(s)"
  echo -e "  Queue Target:   ${REDIS_URL:-InProcess}"
  echo -e "  Status:         sudo systemctl status openoptout-worker"
  echo -e "  Live Logs:      sudo journalctl -u openoptout-worker -f"
  echo -e "${GREEN}========================================================================${NC}"
fi

exit 0
