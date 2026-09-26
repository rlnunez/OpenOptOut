#!/bin/sh
# ==============================================================================
# PrivacyShield one-line installer.
#
#   curl -fsSL https://get.privacyshield.example/ | sh
#   curl -fsSL https://get.privacyshield.example/ | sh -s -- --native
#   curl -fsSL https://get.privacyshield.example/ | sh -s -- --dir /srv/privacyshield
#
# (Replace get.privacyshield.example with wherever you actually host this file
# — e.g. a GitHub raw URL. REPO_URL below also needs to point at your fork.)
#
# What it does: clones PrivacyShield, then picks ONE path automatically and
# hands off to it — it does not duplicate that path's own logic:
#   - Docker available and running -> docker compose up -d (see docs/HTTPS.md
#     afterward for enabling HTTPS)
#   - No Docker, but this looks like a Debian/Ubuntu host running as root ->
#     deploy/native/install.sh (systemd + nginx, no containers — see
#     docs/NATIVE_INSTALL.md)
#   - Neither applies -> prints what to do instead rather than guessing
#
# Flags:  --docker            force the Docker path
#         --native            force the native (no-container) path
#         --dir PATH          where to put the checkout (defaults differ by path)
#         --ref BRANCH        git branch/tag to check out (default: main)
#         --repo URL          git URL to clone (default: this project's repo)
#         -h / --help         show this
#
# Written in POSIX sh on purpose (not bash) so it works under whatever /bin/sh
# actually is (dash on Debian/Ubuntu, ash in BusyBox, etc.) — the same reason
# well-known installers like get.docker.com are shipped this way. Safe to
# re-run: an existing checkout is updated (git pull) rather than clobbered,
# and an existing .env is never touched or overwritten.
# ==============================================================================
set -e

REPO_URL="https://github.com/YOUR_USERNAME/privacyshield.git"
REF="main"
MODE=""
DIR=""

die()  { printf 'Error: %s\n' "$1" >&2; exit 1; }
info() { printf '%s\n' "$1"; }
warn() { printf 'Warning: %s\n' "$1" >&2; }

show_help() {
  sed -n '2,26p' "$0" 2>/dev/null || true
  # $0 is "sh"/"-" when piped (no real script file to read), so fall back to
  # a plain restatement of the flags in that case.
  if [ ! -f "$0" ]; then
    printf '%s\n' "Flags: --docker | --native | --dir PATH | --ref BRANCH | --repo URL | -h"
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --docker) MODE="docker"; shift ;;
    --native) MODE="native"; shift ;;
    --dir) DIR="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    -h|--help) show_help; exit 0 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
done

command -v git >/dev/null 2>&1 || {
  if command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
    info "git not found — installing it (apt-get)…"
    apt-get update -qq && apt-get install -y -qq git
  fi
}
command -v git >/dev/null 2>&1 || die "git not found. Install it first, then re-run this script."

# ── clone or update a checkout at $1 ─────────────────────────────────────────
# Never deletes or force-overwrites an existing directory: if it's already a
# git checkout, pulls; if it exists and ISN'T one, stops rather than guessing.
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

# A generated SECRET_KEY, the same way deploy/native/install.sh makes one —
# openssl if present (virtually always is), else Python as a fallback.
gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  else
    die "Neither openssl nor python3 is available to generate a SECRET_KEY."
  fi
}

# ── decide the path, if not forced by a flag ─────────────────────────────────
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
      die "Docker is installed but not usable right now (daemon not running, Compose v2 missing, or needs sudo). Fix that and re-run, or pass --native if this is meant to be a no-container install."
    fi
    die "Docker isn't installed, and this doesn't look like a Debian/Ubuntu host running as root (needed for the automated native path). Either install Docker (https://get.docker.com) and re-run, or see docs/NATIVE_INSTALL.md to install natively by hand on your OS."
  fi
fi

# ── Docker path ───────────────────────────────────────────────────────────────
if [ "$MODE" = "docker" ]; then
  command -v docker >/dev/null 2>&1 || die "docker not found. Install it first (https://get.docker.com), then re-run this script."

  if [ -z "$DIR" ]; then
    if [ -f "./docker-compose.yml" ] && [ -f "./backend/main.py" ]; then
      DIR="$PWD"    # already run from inside a checkout — use it in place
    else
      DIR="$PWD/privacyshield"
    fi
  fi
  [ "$DIR" = "$PWD" ] || checkout "$DIR"
  cd "$DIR"

  if [ ! -f ".env" ]; then
    cp .env.example .env
    secret="$(gen_secret)"
    # Portable in-place edit: BSD sed (macOS) and GNU sed (Linux) disagree on
    # `-i` — write to a temp file and move it instead of relying on either.
    sed "s/^SECRET_KEY=.*/SECRET_KEY=$secret/" .env > .env.tmp && mv .env.tmp .env
    info "Created .env with a generated SECRET_KEY."
  fi

  # Record which commit is about to be built, so a rebuild bakes an accurate
  # answer into the image for core/version.py to report (startup log +
  # /api/health) — "unknown" if this isn't a real git checkout (e.g. a
  # downloaded zip), which docker-compose.yml's default already handles.
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

# ── Native path ────────────────────────────────────────────────────────────────
if [ "$MODE" = "native" ]; then
  [ "$(id -u)" = 0 ] || die "The native install needs root (it creates a system user and installs OS packages). Re-run with sudo."
  command -v bash >/dev/null 2>&1 || die "deploy/native/install.sh needs bash, which wasn't found. Install it first (it ships by default on virtually every Linux distro)."

  [ -n "$DIR" ] || DIR="/opt/privacyshield-src"
  checkout "$DIR"

  info "Handing off to the native (no-Docker) installer…"
  bash "$DIR/deploy/native/install.sh"
  exit $?
fi

die "Internal error: unknown mode '$MODE'."
