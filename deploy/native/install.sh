#!/usr/bin/env bash
# ==============================================================================
# Native (no Docker) install/update for PrivacyShield, on Debian/Ubuntu Linux.
#
#   sudo ./deploy/native/install.sh                # first install
#   sudo ./deploy/native/install.sh --update        # pull code changes back in
#                                                    # (re-runs the build steps
#                                                    # without touching .env or data)
#
# What this does:
#   1. Creates a dedicated 'privacyshield' system user and /opt/privacyshield
#   2. Copies the backend into /opt/privacyshield/app, laid out as an
#      importable "app" package (main.py's relative imports need this — this
#      mirrors exactly what the Docker image's build step does)
#   3. Creates a venv, installs Python dependencies, installs Playwright's
#      Firefox + its OS dependencies
#   4. Compiles the plugin gRPC protocol stubs (best-effort — the plugin
#      system just stays inactive if this fails, same as the Docker image)
#   5. Builds the frontend (npm run build) into /opt/privacyshield/frontend/dist
#   6. Installs the systemd unit (deploy/native/privacyshield-api.service)
#   7. On first install only: creates /opt/privacyshield/.env from
#      .env.example if it doesn't already exist, and prints the remaining
#      manual steps (nginx site, SECRET_KEY, HTTPS)
#
# This assumes Debian or Ubuntu (uses apt). On RHEL/Rocky/openSUSE/other
# distros, install the equivalent packages by hand (see the apt-get lines
# below for what's needed) and skip straight to the venv/pip steps.
#
# This script does NOT touch nginx, certbot, or HTTPS — see
# deploy/native/nginx-privacyshield.conf.example and
# scripts/enable-https-native.sh for those, and docs/NATIVE_INSTALL.md for
# the full walkthrough tying every piece together.
# ==============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INSTALL_DIR="/opt/privacyshield"
SVC_USER="privacyshield"
UPDATE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --update) UPDATE=1; shift ;;
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

die() { echo "Error: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "Run this as root (sudo) — it creates a system user and installs system packages."
[ -f "$REPO_ROOT/backend/main.py" ] || die "Couldn't find backend/main.py under $REPO_ROOT — run this from inside the PrivacyShield repo checkout."
command -v python3 >/dev/null 2>&1 || die "python3 not found. Install it first (it's included in the apt list below if you're on Debian/Ubuntu)."

echo "==> Installing to $INSTALL_DIR (repo checkout: $REPO_ROOT)"

# ── 1. system user + directories ──
if ! id "$SVC_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SVC_USER"
  echo "Created system user: $SVC_USER"
fi
mkdir -p "$INSTALL_DIR" "$INSTALL_DIR/data" "$INSTALL_DIR/data/screenshots" \
         "$INSTALL_DIR/data/plugins" "$INSTALL_DIR/data/plugin_storage" \
         "$INSTALL_DIR/data/logo" /var/log/privacyshield

# ── 2. OS packages (Playwright's Firefox deps + bubblewrap for plugin
#      sandboxing + libldap/libsasl headers to build python-ldap) ──
if command -v apt-get >/dev/null 2>&1; then
  echo "==> Installing OS packages (apt)…"
  apt-get update
  apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev \
    wget curl ca-certificates fonts-liberation rsync \
    libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libxss1 libxtst6 xdg-utils \
    bubblewrap libseccomp2 python3-seccomp \
    xmlsec1 gcc build-essential libldap2-dev libsasl2-dev \
    nginx
else
  echo "==> apt-get not found — skipping OS package install."
  echo "    Install the equivalent of these packages for your distro before continuing:"
  echo "    python3, python3-venv/pip, a C toolchain, libldap/libsasl headers,"
  echo "    xmlsec1, bubblewrap + libseccomp (for plugin sandboxing),"
  echo "    and Playwright's Firefox runtime dependencies (playwright install-deps"
  echo "    below will list exactly what's missing on your system)."
fi

# ── 3. copy the backend, laid out as the "app" package ──
# Mirrors the Docker image's build step exactly: main.py's relative imports
# (from .models, from .core, from .routers) only resolve when this code is
# imported as a package, so we copy backend/ to app/ and add __init__.py
# files, then always run uvicorn as "app.main:app" from INSTALL_DIR.
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '*.db' \
  --exclude 'privacyshield_settings.json' --exclude 'cert_monitor.json' \
  "$REPO_ROOT/backend/" "$INSTALL_DIR/app/"
touch "$INSTALL_DIR/app/__init__.py"
for d in models routers core; do
  [ -d "$INSTALL_DIR/app/$d" ] && touch "$INSTALL_DIR/app/$d/__init__.py"
done

# ── 4. venv + Python deps ──
if [ ! -d "$INSTALL_DIR/venv" ]; then
  python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/app/requirements.txt"
if [ -f "$INSTALL_DIR/app/requirements-encryption.txt" ]; then
  "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/app/requirements-encryption.txt" \
    || echo "WARN: sqlcipher3 install failed for this platform — continuing without file-level encryption"
fi
if ! "$INSTALL_DIR/venv/bin/playwright" install firefox; then
  echo "WARN: Playwright's Firefox download failed — common behind corporate"
  echo "      firewalls/proxies that block Microsoft's CDN (playwright*.azureedge.net)."
  echo "      The rest of PrivacyShield will still work; automated opt-out form-filling"
  echo "      won't, until you retry this manually once network access allows it:"
  echo "        sudo -u $SVC_USER $INSTALL_DIR/venv/bin/playwright install firefox"
fi
"$INSTALL_DIR/venv/bin/playwright" install-deps firefox || \
  echo "WARN: some Playwright OS dependencies may be missing — see the output above."

# ── 5. compile the plugin gRPC stubs (best-effort) ──
PROTO_DIR="$INSTALL_DIR/app/plugins/proto"
if [ -f "$PROTO_DIR/plugin.proto" ]; then
  "$INSTALL_DIR/venv/bin/python" -m grpc_tools.protoc -I"$PROTO_DIR" \
    --python_out="$PROTO_DIR" --grpc_python_out="$PROTO_DIR" "$PROTO_DIR/plugin.proto" \
    && sed -i 's/^import plugin_pb2 as/from . import plugin_pb2 as/' "$PROTO_DIR/plugin_pb2_grpc.py" \
    && touch "$PROTO_DIR/__init__.py" \
    || echo "WARN: proto compile skipped — plugin system will be inactive"
fi

# ── 6. build the frontend ──
if command -v npm >/dev/null 2>&1; then
  echo "==> Building frontend…"
  ( cd "$REPO_ROOT/frontend" && npm install && npm run build )
  mkdir -p "$INSTALL_DIR/frontend"
  rsync -a --delete "$REPO_ROOT/frontend/dist/" "$INSTALL_DIR/frontend/dist/"
else
  die "npm not found. Install Node.js/npm, or build the frontend elsewhere and copy" \
      "frontend/dist into $INSTALL_DIR/frontend/dist yourself, then re-run with --update."
fi

# ── 7. permissions ──
chown -R "$SVC_USER:$SVC_USER" "$INSTALL_DIR" /var/log/privacyshield

# ── 8. systemd unit ──
cp "$REPO_ROOT/deploy/native/privacyshield-api.service" /etc/systemd/system/privacyshield-api.service
systemctl daemon-reload

# ── 8.5. record the git commit being installed/updated to ──
# Read by core/version.py (via EnvironmentFile in the systemd unit) — logged
# at startup and served from /api/health, so there's never a question of
# exactly what code is running. Runs on every install AND --update, unlike
# the .env creation below, since this should always reflect the checkout
# that was just built from. "unknown" (core/version.py's own fallback) if
# this isn't a real git checkout at all.
if [ -d "$REPO_ROOT/.git" ] && command -v git >/dev/null 2>&1; then
  COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || true)"
  if [ -n "$COMMIT" ] && [ -f "$INSTALL_DIR/.env" ]; then
    if grep -q "^GIT_COMMIT=" "$INSTALL_DIR/.env" 2>/dev/null; then
      sed -i "s/^GIT_COMMIT=.*/GIT_COMMIT=$COMMIT/" "$INSTALL_DIR/.env"
    else
      echo "GIT_COMMIT=$COMMIT" >> "$INSTALL_DIR/.env"
    fi
  fi
fi

# ── 9. first-install-only setup ──
if [ "$UPDATE" = 0 ]; then
  if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$REPO_ROOT/.env.example" "$INSTALL_DIR/.env"
    SECRET="$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')"
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET/" "$INSTALL_DIR/.env"
    echo "SETTINGS_FILE=$INSTALL_DIR/data/privacyshield_settings.json" >> "$INSTALL_DIR/.env"
    echo "LOGO_PATH=$INSTALL_DIR/data/logo" >> "$INSTALL_DIR/.env"
    # .env didn't exist yet when the block above ran, so GIT_COMMIT wasn't
    # written there — add it now that the file actually exists.
    if [ -d "$REPO_ROOT/.git" ] && command -v git >/dev/null 2>&1; then
      COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || true)"
      [ -n "$COMMIT" ] && echo "GIT_COMMIT=$COMMIT" >> "$INSTALL_DIR/.env"
    fi
    chown "$SVC_USER:$SVC_USER" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    echo "Created $INSTALL_DIR/.env with a generated SECRET_KEY."
  fi
  echo
  echo "============================================================"
  echo " First install steps still needed:"
  echo "   1. Review $INSTALL_DIR/.env (database, email, etc — see .env.example)"
  echo "   2. sudo systemctl enable --now privacyshield-api"
  echo "   3. Install the nginx site:"
  echo "      sudo cp deploy/native/nginx-privacyshield.conf.example /etc/nginx/sites-available/privacyshield"
  echo "      (edit YOUR_DOMAIN in it first)"
  echo "      sudo ln -s /etc/nginx/sites-available/privacyshield /etc/nginx/sites-enabled/"
  echo "      sudo nginx -t && sudo systemctl reload nginx"
  echo "   4. Turn on HTTPS:  sudo ./scripts/enable-https-native.sh --domain your.domain --email you@your.org"
  echo " Full walkthrough: docs/NATIVE_INSTALL.md"
  echo "============================================================"
else
  echo "==> Update complete. Restart the service to pick up code changes:"
  echo "    sudo systemctl restart privacyshield-api"
fi
exit 0
