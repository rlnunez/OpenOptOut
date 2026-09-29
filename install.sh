#!/bin/sh
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

die()  { printf 'Error: %s\n' "$1" >&2; exit 1; }
info() { printf '%s\n' "$1"; }
warn() { printf 'Warning: %s\n' "$1" >&2; }

show_help() {
  sed -n '2,27p' "$0" 2>/dev/null || true
  if [ ! -f "$0" ]; then
    printf '%s\n' "Flags: --role <ROLE> | --db <ENGINE> | --domain <DOMAIN> | --queue <REDIS_URL> | --unattended | --docker | --native | --dir PATH | -h"
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
    ( cd "$target" && git fetch --quiet origin "$REF" \
        && git checkout --quiet "$REF" \
        && git merge --quiet --ff-only "origin/$REF" ) \
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
