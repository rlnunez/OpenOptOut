#!/usr/bin/env python3
"""
Restores and validates all files for Roadmap Item 23 and version 0.7.1.
Run this script to guarantee all files are cleanly written to disk.
"""

import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

FILES = {}

# 1. VERSION
FILES["VERSION"] = "0.7.1\n"

# 2. backend/VERSION
FILES["backend/VERSION"] = "0.7.1\n"

# 3. deploy/native/privacyshield-worker.service
FILES["deploy/native/privacyshield-worker.service"] = """# PrivacyShield Stateless Worker Daemon — systemd unit (native install, no Docker).
#
# Install:
#   sudo cp deploy/native/privacyshield-worker.service /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now privacyshield-worker
#
# Runs the PrivacyShield stateless worker daemon in a distributed fleet (Roadmap Item 7.3 & 23).
# Consumes jobs from REDIS_URL using Playwright browser automation in a hardened Bubblewrap sandbox.

[Unit]
Description=PrivacyShield Stateless Worker Daemon
After=network.target
Wants=network.target

[Service]
Type=simple
User=privacyshield
Group=privacyshield
WorkingDirectory=/opt/privacyshield
EnvironmentFile=/opt/privacyshield/.env
ExecStart=/opt/privacyshield/venv/bin/python -m app.worker
Restart=always
RestartSec=5

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/privacyshield/data /var/log/privacyshield

[Install]
WantedBy=multi-user.target
"""

# 4. deploy/native/install.sh
FILES["deploy/native/install.sh"] = """#!/usr/bin/env bash
# ==============================================================================
# Native (no Docker) install/update for PrivacyShield, on Debian/Ubuntu Linux.
#
#   sudo ./deploy/native/install.sh                # first install (interactive wizard or flags)
#   sudo ./deploy/native/install.sh --update        # pull code changes back in
#
# Seamlessly hands off to the unified interactive host & fleet installer (Roadmap Item 23):
#   deploy/installer/setup.sh
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/../installer/setup.sh" "$@"
"""

# 5. install.sh
FILES["install.sh"] = """#!/bin/sh
# ==============================================================================
# PrivacyShield one-line installer (Roadmap Item 23).
#
#   curl -fsSL https://raw.githubusercontent.com/rlnunez/Privacy-Shield/main/install.sh | sudo bash
#   curl -fsSL https://raw.githubusercontent.com/rlnunez/Privacy-Shield/main/install.sh | sudo bash -s -- --role worker --queue redis://...
#   curl -fsSL https://raw.githubusercontent.com/rlnunez/Privacy-Shield/main/install.sh | sh -s -- --docker
#
# What it does: clones or updates PrivacyShield, then picks a deployment path:
#   - Docker requested (--docker) -> docker compose up -d
#   - Native / Fleet installer requested (--native or --role or Linux root) ->
#     launches the interactive TUI / CLI host & fleet installer
#     (deploy/installer/setup.sh) supporting standalone, control-plane, and worker roles.
#
# Installer Flags:
#   --role <ROLE>         standalone | control-plane | worker (default: interactive prompt)
#   --db <ENGINE>         sqlite | postgres | sqlcipher (default: sqlite)
#   --domain <DOMAIN>     public hostname/domain (default: localhost)
#   --queue <REDIS_URL>   Redis transport URL for worker or control plane
#   --unattended, -y      run non-interactively with defaults or passed flags
#   --docker              force the Docker container path
#   --native              force the native systemd path
#   --dir PATH            where to put the checkout (default: auto)
#   --ref BRANCH          git branch/tag to check out (default: main)
#   --repo URL            git URL to clone (default: this project's repo)
#   -h / --help           show this help
# ==============================================================================
set -e

REPO_URL="https://github.com/rlnunez/Privacy-Shield.git"
REF="main"
MODE=""
DIR=""

die()  { printf 'Error: %s\\n' "$1" >&2; exit 1; }
info() { printf '%s\\n' "$1"; }
warn() { printf 'Warning: %s\\n' "$1" >&2; }

show_help() {
  sed -n '2,27p' "$0" 2>/dev/null || true
  if [ ! -f "$0" ]; then
    printf '%s\\n' "Flags: --role <ROLE> | --db <ENGINE> | --domain <DOMAIN> | --queue <REDIS_URL> | --unattended | --docker | --native | --dir PATH | -h"
  fi
}

# Scan arguments to detect mode and checkout directory
for arg in "$@"; do
  case "$arg" in
    --docker) MODE="docker" ;;
    --native|--role|--db|--domain|--queue|--worker-id|--concurrency|--unattended|-y|--yes|--skip-nginx|--skip-tls)
      [ -n "$MODE" ] || MODE="native"
      ;;
  esac
done

# Check for dir / ref / repo overrides
skip_next=0
for arg in "$@"; do
  if [ "$skip_next" = 1 ]; then
    skip_next=0
    continue
  fi
  case "$arg" in
    --dir) skip_next=1 ;;
    --ref) skip_next=1 ;;
    --repo) skip_next=1 ;;
    -h|--help) show_help; exit 0 ;;
  esac
done

# If --dir was passed, extract its value
prev=""
for arg in "$@"; do
  if [ "$prev" = "--dir" ]; then
    DIR="$arg"
    break
  fi
  prev="$arg"
done

# If --ref was passed, extract its value
prev=""
for arg in "$@"; do
  if [ "$prev" = "--ref" ]; then
    REF="$arg"
    break
  fi
  prev="$arg"
done

# If --repo was passed, extract its value
prev=""
for arg in "$@"; do
  if [ "$prev" = "--repo" ]; then
    REPO_URL="$arg"
    break
  fi
  prev="$arg"
done

command -v git >/dev/null 2>&1 || {
  if command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
    info "git not found — installing it (apt-get)…"
    apt-get update -qq && apt-get install -y -qq git
  fi
}
command -v git >/dev/null 2>&1 || die "git not found. Install it first, then re-run this script."

# ── clone or update a checkout at $1 ─────────────────────────────────────────
checkout() {
  target="$1"
  if [ -d "$target/.git" ]; then
    info "Found an existing checkout at $target — updating it."
    ( cd "$target" && git fetch --quiet origin "$REF" \\
        && git checkout --quiet "$REF" \\
        && git merge --quiet --ff-only "origin/$REF" ) \\
      || warn "Could not update $target automatically (local changes?) — continuing with what's there."
  elif [ -e "$target" ]; then
    die "$target already exists and doesn't look like a git checkout. Remove it, or pass --dir to pick another location."
  else
    info "Cloning $REPO_URL ($REF) into $target…"
    git clone --quiet --branch "$REF" "$REPO_URL" "$target"
  fi
}

gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  else
    die "Neither openssl nor python3 is available to generate a SECRET_KEY."
  fi
}

docker_usable() {
  command -v docker >/dev/null 2>&1 || return 1
  docker info >/dev/null 2>&1 || return 1
  docker compose version >/dev/null 2>&1 || return 1
  return 0
}

if [ -z "$MODE" ]; then
  if docker_usable; then
    MODE="docker"
  elif [ "$(uname -s)" = "Linux" ] && command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
    MODE="native"
  else
    if command -v docker >/dev/null 2>&1; then
      die "Docker is installed but not usable right now (daemon not running, Compose v2 missing, or needs sudo). Fix that and re-run, or pass --native if this is meant to be a native install."
    fi
    die "Docker isn't installed, and this doesn't look like a Debian/Ubuntu host running as root (needed for the automated native path). Either install Docker (https://get.docker.com) and re-run, or see docs/NATIVE_INSTALL.md to install natively."
  fi
fi

# ── Docker path ───────────────────────────────────────────────────────────────
if [ "$MODE" = "docker" ]; then
  command -v docker >/dev/null 2>&1 || die "docker not found. Install it first (https://get.docker.com), then re-run this script."

  if [ -z "$DIR" ]; then
    if [ -f "./docker-compose.yml" ] && [ -f "./backend/main.py" ]; then
      DIR="$PWD"
    else
      DIR="$PWD/privacyshield"
    fi
  fi
  [ "$DIR" = "$PWD" ] || checkout "$DIR"
  cd "$DIR"

  if [ ! -f ".env" ]; then
    cp .env.example .env
    secret="$(gen_secret)"
    sed "s/^SECRET_KEY=.*/SECRET_KEY=$secret/" .env > .env.tmp && mv .env.tmp .env
    info "Created .env with a generated SECRET_KEY."
  fi

  if [ -d ".git" ] && command -v git >/dev/null 2>&1; then
    commit="$(git rev-parse --short HEAD 2>/dev/null || true)"
    if [ -n "$commit" ]; then
      if grep -q "^GIT_COMMIT=" .env 2>/dev/null; then
        sed "s/^GIT_COMMIT=.*/GIT_COMMIT=$commit/" .env > .env.tmp && mv .env.tmp .env
      else
        echo "GIT_COMMIT=$commit" >> .env
      fi
    fi
  fi

  info "Starting PrivacyShield (docker compose up -d)…"
  docker compose up -d

  info ""
  info "PrivacyShield is starting. Open http://localhost (or this server's"
  info "address) in a browser — the first person to register becomes the"
  info "super admin. It's running in: $DIR"
  info ""
  info "Before real people use this, turn on HTTPS:"
  info "  cd $DIR && ./scripts/enable-https.sh    (see docs/HTTPS.md)"
  exit 0
fi

# ── Native / Fleet Installer Path ─────────────────────────────────────────────
if [ "$MODE" = "native" ]; then
  [ "$(id -u)" = 0 ] || die "The native install needs root (it creates a system user and installs OS packages). Re-run with sudo."
  command -v bash >/dev/null 2>&1 || die "deploy/installer/setup.sh needs bash, which wasn't found. Install it first."

  if [ -z "$DIR" ]; then
    if [ -f "./backend/main.py" ] && [ -f "./deploy/installer/setup.sh" ]; then
      DIR="$PWD"
    else
      DIR="/opt/privacyshield-src"
    fi
  fi
  [ "$DIR" = "$PWD" ] || checkout "$DIR"

  info "Launching PrivacyShield Unified Host & Fleet Installer…"
  exec bash "$DIR/deploy/installer/setup.sh" "$@"
fi

die "Internal error: unknown mode '$MODE'."
"""

# 6. backend/core/installer_config.py
FILES["backend/core/installer_config.py"] = """\"\"\"
PrivacyShield Unified Host & Fleet Installer Configuration Engine (Roadmap Item 23).

Defines cluster role profiles, system dependency matrices, Nginx site configuration
templates, systemd unit templates, and environment file generation for standalone,
control-plane, and worker fleet nodes.
\"\"\"

import os
import secrets
from typing import Dict, List, Optional, Set, Tuple


class Role:
    STANDALONE = "standalone"
    CONTROL_PLANE = "control-plane"
    WORKER = "worker"
    ALL = (STANDALONE, CONTROL_PLANE, WORKER)


class DatabaseEngine:
    SQLITE = "sqlite"
    POSTGRESQL = "postgres"
    SQLCIPHER = "sqlcipher"
    ALL = (SQLITE, POSTGRESQL, SQLCIPHER)


# Base operating system packages required across all native installations
BASE_OS_PACKAGES = [
    "python3",
    "python3-venv",
    "python3-dev",
    "wget",
    "curl",
    "ca-certificates",
    "rsync",
    "gcc",
    "build-essential",
]

# Browser automation & sandboxing packages (for Standalone and Worker roles)
BROWSER_AND_SANDBOX_PACKAGES = [
    "bubblewrap",
    "libseccomp2",
    "python3-seccomp",
    "fonts-liberation",
    "libatk-bridge2.0-0",
    "libatk1.0-0",
    "libcups2",
    "libdbus-1-3",
    "libdrm2",
    "libgbm1",
    "libgtk-3-0",
    "libnspr4",
    "libnss3",
    "libx11-xcb1",
    "libxcomposite1",
    "libxdamage1",
    "libxfixes3",
    "libxrandr2",
    "libxss1",
    "libxtst6",
    "xdg-utils",
]

# Web server & identity protocol headers (for Standalone and Control Plane roles)
WEB_AND_IDENTITY_PACKAGES = [
    "nginx",
    "xmlsec1",
    "libldap2-dev",
    "libsasl2-dev",
]


def get_packages_for_role(role: str) -> List[str]:
    \"\"\"
    Returns the distinct list of required Debian/Ubuntu OS packages for a given role.

    Role characteristics:
    - standalone: installs all base, browser/sandbox, and web/identity packages.
    - control-plane: installs base and web/identity packages. EXCLUDES Playwright,
      Firefox, Bubblewrap, and X11 graphics packages (>1.5GB savings).
    - worker: installs base and browser/sandbox packages. EXCLUDES Nginx, Node.js,
      frontend build tools, and web identity packages.
    \"\"\"
    role = role.lower()
    if role not in Role.ALL:
        raise ValueError(f"Unknown role: {role}. Must be one of {Role.ALL}")

    pkgs = list(BASE_OS_PACKAGES)

    if role in (Role.STANDALONE, Role.CONTROL_PLANE):
        pkgs.extend(WEB_AND_IDENTITY_PACKAGES)

    if role in (Role.STANDALONE, Role.WORKER):
        pkgs.extend(BROWSER_AND_SANDBOX_PACKAGES)

    # Return deduplicated while preserving order
    seen: Set[str] = set()
    result: List[str] = []
    for pkg in pkgs:
        if pkg not in seen:
            seen.add(pkg)
            result.append(pkg)
    return result


def requires_frontend_build(role: str) -> bool:
    \"\"\"Returns True if the role requires building and serving the React frontend.\"\"\"
    return role in (Role.STANDALONE, Role.CONTROL_PLANE)


def requires_nginx(role: str) -> bool:
    \"\"\"Returns True if the role requires Nginx reverse proxy configuration.\"\"\"
    return role in (Role.STANDALONE, Role.CONTROL_PLANE)


def requires_playwright_browsers(role: str) -> bool:
    \"\"\"Returns True if the role requires Playwright browser binaries (Firefox).\"\"\"
    return role in (Role.STANDALONE, Role.WORKER)


def generate_nginx_config(
    domain: str,
    frontend_root: str = "/opt/privacyshield/frontend/dist",
    api_host: str = "127.0.0.1",
    api_port: int = 8000,
    client_max_body_size: str = "50M",
) -> str:
    \"\"\"
    Generates an optimized Nginx server block configuration for PrivacyShield.
    Includes SPA routing, API reverse proxying, WebSocket upgrade headers,
    SSE streaming settings, and standard security headers.
    \"\"\"
    domain = domain.strip() if domain else "localhost"
    return f\"\"\"# PrivacyShield — Nginx Reverse Proxy Configuration (Roadmap Item 23)
server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    root {frontend_root};
    index index.html;

    client_max_body_size {client_max_body_size};

    # Reverse proxy for FastAPI backend with WebSockets and SSE support
    location /api/ {{
        proxy_pass http://{api_host}:{api_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Disable proxy buffering for Server-Sent Events (SSE) and live log streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }}

    # Single Page Application (SPA) routing fallback
    location / {{
        try_files $uri $uri/ /index.html;
    }}

    # Security defense-in-depth headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}}
\"\"\"


def generate_systemd_api_service(
    install_dir: str = "/opt/privacyshield",
    user: str = "privacyshield",
    workers: int = 2,
    port: int = 8000,
) -> str:
    \"\"\"Generates the systemd unit definition for the API web service.\"\"\"
    return f\"\"\"[Unit]
Description=PrivacyShield API
After=network.target
Wants=network.target

[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={install_dir}
EnvironmentFile={install_dir}/.env
ExecStart={install_dir}/venv/bin/uvicorn app.main:app \\\\
    --host 127.0.0.1 --port {port} --workers {workers}
Restart=on-failure
RestartSec=5

# Service hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={install_dir}/data /var/log/privacyshield

[Install]
WantedBy=multi-user.target
\"\"\"


def generate_systemd_worker_service(
    install_dir: str = "/opt/privacyshield",
    user: str = "privacyshield",
) -> str:
    \"\"\"Generates the systemd unit definition for the headless worker daemon.\"\"\"
    return f\"\"\"[Unit]
Description=PrivacyShield Stateless Worker Daemon
After=network.target
Wants=network.target

[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={install_dir}
EnvironmentFile={install_dir}/.env
ExecStart={install_dir}/venv/bin/python -m app.worker
Restart=always
RestartSec=5

# Service hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={install_dir}/data /var/log/privacyshield

[Install]
WantedBy=multi-user.target
\"\"\"


def generate_env_config(
    role: str,
    secret_key: Optional[str] = None,
    database_url: Optional[str] = None,
    redis_url: Optional[str] = None,
    worker_id: Optional[str] = None,
    worker_concurrency: int = 1,
    domain: Optional[str] = None,
    install_dir: str = "/opt/privacyshield",
    sqlcipher_key: Optional[str] = None,
) -> Dict[str, str]:
    \"\"\"
    Generates key-value configuration pairs for the .env file tailored to the node's cluster role.
    \"\"\"
    role = role.lower()
    if role not in Role.ALL:
        raise ValueError(f"Unknown role: {role}")

    secret = secret_key or secrets.token_hex(32)
    env: Dict[str, str] = {
        "ROLE": role,
        "SECRET_KEY": secret,
    }

    # Storage paths
    env["SETTINGS_FILE"] = f"{install_dir}/data/privacyshield_settings.json"
    env["LOGO_PATH"] = f"{install_dir}/data/logo"

    # Frontend URL & Domain
    dom = domain.strip() if domain else "localhost"
    proto = "http" if dom in ("localhost", "127.0.0.1") else "https"
    env["FRONTEND_URL"] = f"{proto}://{dom}"

    # Database configuration (Standalone & Control Plane require DB; Worker is stateless)
    if role in (Role.STANDALONE, Role.CONTROL_PLANE):
        if database_url:
            env["DATABASE_URL"] = database_url
        else:
            env["DATABASE_URL"] = f"sqlite:////{install_dir}/data/privacyshield.db"

        if sqlcipher_key:
            env["SQLCIPHER_KEY"] = sqlcipher_key

    # Distributed queue & worker settings
    if redis_url:
        env["REDIS_URL"] = redis_url

    if role == Role.WORKER:
        env["WORKER_ID"] = worker_id or f"worker-{secrets.token_hex(4)}"
        env["WORKER_CONCURRENCY"] = str(worker_concurrency)
        # Workers operate in headless mode by default
        env["HEADLESS"] = "true"

    return env


def format_env_file(config: Dict[str, str]) -> str:
    \"\"\"Formats a dictionary of key-value pairs into a standard .env file string.\"\"\"
    lines = ["# PrivacyShield Environment Configuration", "# Generated by PrivacyShield Installer (Item 23)", ""]
    for k, v in sorted(config.items()):
        # Escape any double quotes if value contains spaces
        if " " in v and not v.startswith('"'):
            val = f'"{v}"'
        else:
            val = v
        lines.append(f"{k}={val}")
    lines.append("")
    return "\\n".join(lines)
"""

# 7. deploy/installer/setup.sh
FILES["deploy/installer/setup.sh"] = """#!/usr/bin/env bash
# ==============================================================================
# PrivacyShield Unified Host & Fleet Installer (CLI/TUI) — Roadmap Item 23
#
# Interactive terminal wizard and scriptable installer for single-node
# and distributed cluster environments (Debian/Ubuntu Linux).
#
# Usage:
#   sudo ./deploy/installer/setup.sh [OPTIONS]
#   curl -fsSL https://raw.githubusercontent.com/rlnunez/Privacy-Shield/main/install.sh | sudo bash
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
#   --install-dir <PATH>  Target directory (default: /opt/privacyshield)
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

INSTALL_DIR="/opt/privacyshield"
SVC_USER="privacyshield"
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
BOLD='\\033[1m'
GREEN='\\033[0;32m'
BLUE='\\033[0;34m'
YELLOW='\\033[1;33m'
RED='\\033[0;31m'
CYAN='\\033[0;36m'
NC='\\033[0m' # No Color

# ── Helper Functions ──────────────────────────────────────────────────────────
die()  { printf "${RED}Error: %s${NC}\\n" "$*" >&2; exit 1; }
info() { printf "${GREEN}==>${NC} %s\\n" "$*"; }
warn() { printf "${YELLOW}Warning: %s${NC}\\n" "$*" >&2; }
head() { printf "\\n${BOLD}${BLUE}── %s ──${NC}\\n" "$*"; }

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
[ -f "$REPO_ROOT/backend/main.py" ] || die "Cannot find backend/main.py in $REPO_ROOT. Run from within the PrivacyShield repo."

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
      ROLE=$(whiptail --title "PrivacyShield Installer — Role Selection" \\
        --menu "Select the cluster deployment role for this node:" 16 75 3 \\
        "standalone" "All-in-one: Web UI, API, DB & local browser automation" \\
        "control-plane" "Web UI & API server (Excludes browser/X11, saves >1.5GB)" \\
        "worker" "Stateless compute node (Playwright Firefox, no Web UI/Nginx)" \\
        3>&1 1>&2 2>&3) || die "Installation cancelled."
    else
      echo -e "\\n${BOLD}${CYAN}=== PrivacyShield Cluster Role Selection ===${NC}"
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
      DB_ENGINE=$(whiptail --title "PrivacyShield Installer — Database Selection" \\
        --menu "Select the database engine for this deployment:" 15 70 3 \\
        "sqlite" "SQLite: File-based local storage (Zero configuration)" \\
        "postgres" "PostgreSQL: Production relational database" \\
        "sqlcipher" "SQLCipher: AES-256 encrypted SQLite at rest" \\
        3>&1 1>&2 2>&3) || DB_ENGINE="sqlite"
    else
      echo -e "\\n${BOLD}${CYAN}=== Database Engine Selection ===${NC}"
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
          DB_URL=$(whiptail --title "PostgreSQL Connection String" --inputbox "Enter the PostgreSQL connection URL:" 10 70 "postgresql://privacyshield:password@localhost/privacyshield" 3>&1 1>&2 2>&3) || true
        fi
      else
        echo -e "\\nProvision local PostgreSQL automatically?"
        read -r -p "Auto-install local PostgreSQL? [Y/n]: " pg_ans
        if [[ "${pg_ans:-y}" =~ ^[Yy] ]]; then
          DB_AUTO_PG=1
        else
          DB_URL=$(prompt_ansi "PostgreSQL Connection URL" "postgresql://privacyshield:password@localhost/privacyshield")
        fi
      fi
    fi
  fi

  # 3. Domain & Web Server (For standalone & control-plane)
  if [[ "$ROLE" != "worker" ]] && [ -z "$DOMAIN" ]; then
    if [ "$USE_WHIPTAIL" = 1 ]; then
      DOMAIN=$(whiptail --title "Domain Configuration" --inputbox "Enter the domain or IP address for PrivacyShield:" 10 70 "localhost" 3>&1 1>&2 2>&3) || DOMAIN="localhost"
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

head "Installing PrivacyShield Node"
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

mkdir -p "$INSTALL_DIR" \\
         "$INSTALL_DIR/data" \\
         "$INSTALL_DIR/data/screenshots" \\
         "$INSTALL_DIR/data/plugins" \\
         "$INSTALL_DIR/data/plugin_storage" \\
         "$INSTALL_DIR/data/logo" \\
         /var/log/privacyshield

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
        sudo -u postgres psql -c "CREATE USER privacyshield WITH ENCRYPTED PASSWORD '$PG_PASS';" >/dev/null 2>&1 || \\
          sudo -u postgres psql -c "ALTER USER privacyshield WITH ENCRYPTED PASSWORD '$PG_PASS';" >/dev/null 2>&1
        sudo -u postgres psql -c "CREATE DATABASE privacyshield OWNER privacyshield;" >/dev/null 2>&1 || true
        DB_URL="postgresql://privacyshield:$PG_PASS@localhost/privacyshield"
        info "Local PostgreSQL database 'privacyshield' created."
      else
        warn "Cannot auto-install PostgreSQL without apt-get. Defaulting to SQLite."
        DB_URL="sqlite:////$INSTALL_DIR/data/privacyshield.db"
      fi
    elif [ -z "$DB_URL" ]; then
      DB_URL="sqlite:////$INSTALL_DIR/data/privacyshield.db"
    fi
  elif [[ "$DB_ENGINE" == "sqlcipher" ]]; then
    SQLCIPHER_KEY="$(gen_secret)"
    DB_URL="sqlite:////$INSTALL_DIR/data/privacyshield.db"
    info "Generated SQLCipher 256-bit database encryption key."
  else
    DB_URL="sqlite:////$INSTALL_DIR/data/privacyshield.db"
    info "Using local SQLite database: $INSTALL_DIR/data/privacyshield.db"
  fi
fi

# ── 4. Deploy Backend Application ─────────────────────────────────────────────
head "Deploying Application Code to $INSTALL_DIR/app"
rsync -a --delete \\
  --exclude '__pycache__' --exclude '*.pyc' --exclude '*.db' \\
  --exclude 'privacyshield_settings.json' --exclude 'cert_monitor.json' \\
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
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/app/requirements-encryption.txt" -q || \\
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
  "$INSTALL_DIR/venv/bin/python" -m grpc_tools.protoc -I"$PROTO_DIR" \\
    --python_out="$PROTO_DIR" --grpc_python_out="$PROTO_DIR" "$PROTO_DIR/plugin.proto" >/dev/null 2>&1 \\
    && sed -i 's/^import plugin_pb2 as/from . import plugin_pb2 as/' "$PROTO_DIR/plugin_pb2_grpc.py" 2>/dev/null \\
    && touch "$PROTO_DIR/__init__.py" || true
fi

# ── 6. Frontend Build (Standalone & Control Plane) ─────────────────────────────
if [[ "$ROLE" == "standalone" || "$ROLE" == "control-plane" ]]; then
  head "Building React Web UI"
  if command -v npm >/dev/null 2>&1; then
    ( cd "$REPO_ROOT/frontend" && npm install --silent && npm run build )
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
# PrivacyShield Cluster Node Configuration
# Generated by PrivacyShield Installer (Roadmap Item 23)
ROLE=$ROLE
SECRET_KEY=$SECRET_KEY
SETTINGS_FILE=$INSTALL_DIR/data/privacyshield_settings.json
LOGO_PATH=$INSTALL_DIR/data/logo
EOF

  if [[ "$ROLE" != "worker" ]]; then
    PROTO="http"
    if [[ "$TLS_MODE" == "letsencrypt" ]]; then PROTO="https"; fi
    echo "FRONTEND_URL=$PROTO://$DOMAIN" >> "$INSTALL_DIR/.env"
    echo "DATABASE_URL=$DB_URL" >> "$INSTALL_DIR/.env"
    [ -z "${SQLCIPHER_KEY:-}" ] || echo "SQLCIPHER_KEY=$SQLCIPHER_KEY" >> "$INSTALL_DIR/.env"
  fi

  if [ -n "$REDIS_URL" ]; then
    echo "REDIS_URL=$REDIS_URL" >> "$INSTALL_DIR/.env"
  fi

  if [[ "$ROLE" == "worker" ]]; then
    echo "WORKER_ID=$WORKER_ID" >> "$INSTALL_DIR/.env"
    echo "WORKER_CONCURRENCY=$WORKER_CONCURRENCY" >> "$INSTALL_DIR/.env"
    echo "HEADLESS=true" >> "$INSTALL_DIR/.env"
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
chown -R "$SVC_USER:$SVC_USER" "$INSTALL_DIR" /var/log/privacyshield

# ── 8. Zero-Touch Nginx & Reverse Proxy Automation ───────────────────────────
if [[ "$ROLE" == "standalone" || "$ROLE" == "control-plane" ]] && [ "$SKIP_NGINX" = 0 ]; then
  head "Configuring Nginx Reverse Proxy"
  if command -v nginx >/dev/null 2>&1; then
    NGINX_CONF="/etc/nginx/sites-available/privacyshield"

    cat <<EOF > "$NGINX_CONF"
# PrivacyShield — Nginx Reverse Proxy Configuration (Roadmap Item 23)
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
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/privacyshield

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
    [ -z "$ADMIN_EMAIL" ] && CERTBOT_ARGS+=(--register-unsafely-without-email) || CERTBOT_ARGS+=(-m "$ADMIN_EMAIL")
    [ "$STAGING" = 0 ] || CERTBOT_ARGS+=(--staging)

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
  cp "$REPO_ROOT/deploy/native/privacyshield-api.service" /etc/systemd/system/privacyshield-api.service
  systemctl daemon-reload
  systemctl enable --now privacyshield-api
  info "Enabled and started privacyshield-api.service"

  # Pre-flight health check
  info "Performing pre-flight health probe (http://127.0.0.1:8000/api/health)..."
  HEALTH_OK=0
  for i in $(seq 1 15); do
    if curl -fs "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
      HEALTH_OK=1
      break
    fi
    sleep 1
  done

  echo
  echo -e "${GREEN}========================================================================${NC}"
  echo -e "${BOLD}${GREEN}  PrivacyShield ${ROLE^^} Node Deployed Successfully!${NC}"
  echo -e "${GREEN}========================================================================${NC}"
  if [ "$HEALTH_OK" = 1 ]; then
    echo -e "  Status:         ${GREEN}HEALTHY (API online)${NC}"
  else
    echo -e "  Status:         ${YELLOW}INITIALIZING (Check: sudo journalctl -u privacyshield-api -f)${NC}"
  fi
  ACCESS_PROTO="http"
  [[ "$TLS_MODE" == "letsencrypt" ]] && ACCESS_PROTO="https"
  echo -e "  Web Access:     ${BOLD}${CYAN}$ACCESS_PROTO://$DOMAIN${NC}"
  echo -e "  Initial Setup:  The first person to register becomes the Super Admin."
  echo -e "  Service Status: sudo systemctl status privacyshield-api"
  echo -e "  Live Logs:      sudo journalctl -u privacyshield-api -f"
  echo -e "${GREEN}========================================================================${NC}"
fi

if [[ "$ROLE" == "worker" ]]; then
  cp "$REPO_ROOT/deploy/native/privacyshield-worker.service" /etc/systemd/system/privacyshield-worker.service
  systemctl daemon-reload
  systemctl enable --now privacyshield-worker
  info "Enabled and started privacyshield-worker.service"

  sleep 2
  echo
  echo -e "${GREEN}========================================================================${NC}"
  echo -e "${BOLD}${GREEN}  PrivacyShield Worker Fleet Node Online!${NC}"
  echo -e "${GREEN}========================================================================${NC}"
  echo -e "  Worker ID:      ${BOLD}${CYAN}$WORKER_ID${NC}"
  echo -e "  Concurrency:    $WORKER_CONCURRENCY concurrent slot(s)"
  echo -e "  Queue Target:   ${REDIS_URL:-InProcess}"
  echo -e "  Status:         sudo systemctl status privacyshield-worker"
  echo -e "  Live Logs:      sudo journalctl -u privacyshield-worker -f"
  echo -e "${GREEN}========================================================================${NC}"
fi

exit 0
"""


def main():
    errors = 0
    print("==> Restoring and validating files...")
    for rel_path, content in FILES.items():
        full_path = os.path.join(BASE_DIR, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        size = os.path.getsize(full_path)
        if size == 0:
            print(f"ERROR: {rel_path} is empty (0 bytes)!")
            errors += 1
        else:
            print(f"OK: {rel_path} ({size} bytes, {len(content.splitlines())} lines)")

    # Ensure executable permissions for scripts
    os.chmod(os.path.join(BASE_DIR, "deploy/installer/setup.sh"), 0o755)
    os.chmod(os.path.join(BASE_DIR, "deploy/native/install.sh"), 0o755)
    os.chmod(os.path.join(BASE_DIR, "install.sh"), 0o755)

    # Update frontend/package.json
    pkg_json_path = os.path.join(BASE_DIR, "frontend/package.json")
    with open(pkg_json_path, "r", encoding="utf-8") as f:
        pkg_content = f.read()
    pkg_content = pkg_content.replace('"version": "0.7.0"', '"version": "0.7.1"')
    with open(pkg_json_path, "w", encoding="utf-8") as f:
        f.write(pkg_content)
    print(f"OK: frontend/package.json ({os.path.getsize(pkg_json_path)} bytes)")

    # Update docs/ROADMAP.md
    roadmap_path = os.path.join(BASE_DIR, "docs/ROADMAP.md")
    with open(roadmap_path, "r", encoding="utf-8") as f:
        roadmap_content = f.read()
    old_target = """- **Pre-Flight Health Handoff:** Executes local loopback health checks before completing, outputting direct URLs and instructions for initial super-admin registration.

**Status:** Planned."""
    new_target = """- **Pre-Flight Health Handoff:** Executes local loopback health checks before completing, outputting direct URLs and instructions for initial super-admin registration.
- **Verification:** Pure Python unit tests in `tests/run_tests.py` (`t_installer_role_specialization_and_configs`) validating role package specialization matrices, Nginx reverse proxy configuration generation, systemd unit definitions for API and worker services, and role-tailored environment configurations.

**Status:** Complete."""
    if old_target in roadmap_content:
        roadmap_content = roadmap_content.replace(old_target, new_target)
        with open(roadmap_path, "w", encoding="utf-8") as f:
            f.write(roadmap_content)
    print(f"OK: docs/ROADMAP.md ({os.path.getsize(roadmap_path)} bytes)")

    # Update backend/tests/run_tests.py to include installer test
    run_tests_path = os.path.join(BASE_DIR, "backend/tests/run_tests.py")
    with open(run_tests_path, "r", encoding="utf-8") as f:
        rt_content = f.read()
    test_marker = "def t_installer_role_specialization_and_configs"
    if test_marker not in rt_content:
        anchor = "    asyncio.run(run_daemon_test())\n"
        test_code = """
@test(1, "installer.role_specialization_and_configs",
      "Unified installer verifies package matrices, role specialization, Nginx config, and systemd units (Roadmap Item 23).")
def t_installer_role_specialization_and_configs():
    installer_mod = _imp("core.installer_config")

    # 1. Package isolation per role
    standalone_pkgs = set(installer_mod.get_packages_for_role("standalone"))
    cp_pkgs = set(installer_mod.get_packages_for_role("control-plane"))
    worker_pkgs = set(installer_mod.get_packages_for_role("worker"))

    # Control plane must NOT include playwright browser and graphics dependencies (>1.5GB savings)
    assert "bubblewrap" in standalone_pkgs
    assert "bubblewrap" in worker_pkgs
    assert "bubblewrap" not in cp_pkgs, "control-plane must exclude bubblewrap"
    assert "libx11-xcb1" not in cp_pkgs, "control-plane must exclude X11 packages"
    assert "libatk1.0-0" not in cp_pkgs, "control-plane must exclude browser rendering libraries"

    # Worker must NOT include nginx or web identity dev headers
    assert "nginx" in standalone_pkgs
    assert "nginx" in cp_pkgs
    assert "nginx" not in worker_pkgs, "worker node must exclude nginx web server"
    assert "xmlsec1" not in worker_pkgs, "worker node must exclude xmlsec1 web SSO library"

    # Base dependencies present across all roles
    for base in ("python3", "python3-venv", "curl", "rsync"):
        assert base in standalone_pkgs
        assert base in cp_pkgs
        assert base in worker_pkgs

    # Invalid role raises ValueError
    try:
        installer_mod.get_packages_for_role("invalid-role")
        assert False, "should have raised ValueError on invalid role"
    except ValueError:
        pass

    # 2. Role feature requirements
    assert installer_mod.requires_frontend_build("standalone") is True
    assert installer_mod.requires_frontend_build("control-plane") is True
    assert installer_mod.requires_frontend_build("worker") is False

    assert installer_mod.requires_nginx("standalone") is True
    assert installer_mod.requires_nginx("control-plane") is True
    assert installer_mod.requires_nginx("worker") is False

    assert installer_mod.requires_playwright_browsers("standalone") is True
    assert installer_mod.requires_playwright_browsers("control-plane") is False
    assert installer_mod.requires_playwright_browsers("worker") is True

    # 3. Nginx configuration generator
    nginx_conf = installer_mod.generate_nginx_config(
        domain="privacy.citylibrary.org",
        frontend_root="/opt/privacyshield/frontend/dist",
        api_host="127.0.0.1",
        api_port=8000,
        client_max_body_size="50M",
    )
    assert "server_name privacy.citylibrary.org;" in nginx_conf
    assert "root /opt/privacyshield/frontend/dist;" in nginx_conf
    assert "proxy_pass http://127.0.0.1:8000;" in nginx_conf
    assert "proxy_set_header Upgrade $http_upgrade;" in nginx_conf
    assert 'proxy_set_header Connection "upgrade";' in nginx_conf
    assert "proxy_buffering off;" in nginx_conf
    assert "client_max_body_size 50M;" in nginx_conf
    assert "X-Content-Type-Options" in nginx_conf

    # 4. Systemd unit generators
    api_unit = installer_mod.generate_systemd_api_service(
        install_dir="/opt/privacyshield",
        user="privacyshield",
        workers=3,
        port=8000,
    )
    assert "Description=PrivacyShield API" in api_unit
    assert "ExecStart=/opt/privacyshield/venv/bin/uvicorn app.main:app" in api_unit
    assert "--workers 3" in api_unit
    assert "NoNewPrivileges=true" in api_unit

    worker_unit = installer_mod.generate_systemd_worker_service(
        install_dir="/opt/privacyshield",
        user="privacyshield",
    )
    assert "Description=PrivacyShield Stateless Worker Daemon" in worker_unit
    assert "ExecStart=/opt/privacyshield/venv/bin/python -m app.worker" in worker_unit
    assert "Restart=always" in worker_unit

    # 5. Environment generation (.env) per role
    env_standalone = installer_mod.generate_env_config(
        role="standalone",
        domain="privacy.lib.org",
        database_url="sqlite:////opt/privacyshield/data/privacyshield.db",
    )
    assert env_standalone["ROLE"] == "standalone"
    assert env_standalone["FRONTEND_URL"] == "https://privacy.lib.org"
    assert "DATABASE_URL" in env_standalone
    assert "WORKER_ID" not in env_standalone

    env_cp = installer_mod.generate_env_config(
        role="control-plane",
        redis_url="redis://redis.internal:6379/0",
    )
    assert env_cp["ROLE"] == "control-plane"
    assert env_cp["REDIS_URL"] == "redis://redis.internal:6379/0"

    env_worker = installer_mod.generate_env_config(
        role="worker",
        worker_id="worker-node-42",
        worker_concurrency=4,
        redis_url="redis://control-plane:6379/0",
    )
    assert env_worker["ROLE"] == "worker"
    assert env_worker["WORKER_ID"] == "worker-node-42"
    assert env_worker["WORKER_CONCURRENCY"] == "4"
    assert env_worker["HEADLESS"] == "true"
    assert "DATABASE_URL" not in env_worker, "stateless worker should not require database connection"

    # Format .env content
    env_text = installer_mod.format_env_file(env_worker)
    assert "ROLE=worker" in env_text
    assert "WORKER_ID=worker-node-42" in env_text
    assert "HEADLESS=true" in env_text
"""
        if anchor in rt_content:
            rt_content = rt_content.replace(anchor, anchor + test_code)
            with open(run_tests_path, "w", encoding="utf-8") as f:
                f.write(rt_content)
    print(f"OK: backend/tests/run_tests.py ({os.path.getsize(run_tests_path)} bytes)")

    if errors > 0:
        print(f"FAILED: {errors} files had errors.")
        sys.exit(1)
    print("SUCCESS: All files written, populated, and verified.")


if __name__ == "__main__":
    main()
