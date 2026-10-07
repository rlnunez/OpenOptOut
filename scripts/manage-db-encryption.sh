#!/usr/bin/env bash
# ==============================================================================
# OpenOptOut — Database Encryption Management Tool (SQLCipher AES-256)
#
# Allows superadmins and operators to inspect, encrypt, decrypt, or re-key
# the SQLite database. Works transparently in both Docker Compose and native
# systemd environments.
#
# Usage:
#   ./scripts/manage-db-encryption.sh status
#   ./scripts/manage-db-encryption.sh encrypt [--inplace]
#   ./scripts/manage-db-encryption.sh decrypt [--inplace]
#   ./scripts/manage-db-encryption.sh rekey --old-key <OLD> --new-key <NEW>
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Styling
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info() { printf "${GREEN}==>${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}Warning: %s${NC}\n" "$*" >&2; }
die()  { printf "${RED}Error: %s${NC}\n" "$*" >&2; exit 1; }

show_help() {
  cat <<EOF
${BOLD}OpenOptOut Database Encryption Management Utility${NC}

Commands:
  ${CYAN}status${NC}                           Check database encryption posture and key validity
  ${CYAN}encrypt [--inplace]${NC}              Encrypt an existing plaintext SQLite database to SQLCipher
  ${CYAN}decrypt [--inplace]${NC}              Decrypt an encrypted SQLCipher database back to plain SQLite
  ${CYAN}rekey --old-key <O> --new-key <N>${NC} Change the encryption passphrase of an encrypted database
  ${CYAN}-h, --help${NC}                        Show this help reference

Options:
  --db <path>                 Specify custom database file path
  --key <passphrase>          Specify passphrase (default: DB_ENCRYPTION_KEY / SECRET_KEY)
  --native                    Force native Python environment (/opt/openoptout or local venv)
  --docker                    Force execution inside Docker Compose container

EOF
}

# ── Environment Detection ─────────────────────────────────────────────────────
USE_DOCKER=0
NATIVE_PY=""

if [ -f "$REPO_ROOT/docker-compose.yml" ] && command -v docker >/dev/null 2>&1 && docker compose ps --services 2>/dev/null | grep -q "api"; then
  # Docker container is running or defined
  USE_DOCKER=1
fi

if [ -x "/opt/openoptout/venv/bin/python3" ]; then
  NATIVE_PY="/opt/openoptout/venv/bin/python3"
elif [ -x "$REPO_ROOT/venv/bin/python3" ]; then
  NATIVE_PY="$REPO_ROOT/venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
  NATIVE_PY="$(command -v python3)"
fi

RUN_MODE="auto"
DB_PATH=""
KEY_ARG=""
EXTRA_ARGS=()

if [ $# -eq 0 ]; then
  show_help
  exit 0
fi

CMD="$1"
shift

while [ $# -gt 0 ]; do
  case "$1" in
    --docker) RUN_MODE="docker"; shift ;;
    --native) RUN_MODE="native"; shift ;;
    --db) DB_PATH="$2"; shift 2 ;;
    --key) KEY_ARG="$2"; shift 2 ;;
    -h|--help) show_help; exit 0 ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done

# Run execution helper
exec_py() {
  local py_args=("$@")
  if [ "$RUN_MODE" = "docker" ] || ([ "$RUN_MODE" = "auto" ] && [ "$USE_DOCKER" -eq 1 ]); then
    info "Executing via Docker Compose (api container)..."
    docker compose -f "$REPO_ROOT/docker-compose.yml" exec api python3 -m core.encryption "${py_args[@]}"
  else
    if [ -z "$NATIVE_PY" ]; then
      die "Python environment not found. Ensure Python with sqlcipher3 is installed or run with --docker."
    fi
    info "Executing via native Python ($NATIVE_PY)..."
    PYTHONPATH="$REPO_ROOT/backend" "$NATIVE_PY" -m core.encryption "${py_args[@]}"
  fi
}

# Build parameter array
CMD_ARGS=("$CMD")
[ -n "$DB_PATH" ] && CMD_ARGS+=("$DB_PATH")
[ -n "$KEY_ARG" ] && CMD_ARGS+=("--key" "$KEY_ARG")
[ ${#EXTRA_ARGS[@]} -gt 0 ] && CMD_ARGS+=("${EXTRA_ARGS[@]}")

exec_py "${CMD_ARGS[@]}"
