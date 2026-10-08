#!/usr/bin/env bash
# ==============================================================================
# OpenOptOut — Security Hardening & Container Sandbox Verification Suite
#
# Runs testing probes for:
#   1. Ephemeral RAM tmpfs (/tmp) sizing & leak tests (Roadmap Phase 15.2)
#   2. Container no-new-privileges bubblewrap sandbox compatibility (Roadmap Phase 21.2)
#
# Usage:
#   ./scripts/test-hardening-posture.sh [--all]
#   ./scripts/test-hardening-posture.sh --tmpfs
#   ./scripts/test-hardening-posture.sh --no-new-privs
#   ./scripts/test-hardening-posture.sh --docker
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

RUN_TMPFS=0
RUN_NNP=0
USE_DOCKER=0
FORCE_NATIVE=0
SPECIFIC_TEST=0

while [ $# -gt 0 ]; do
  case "$1" in
    --tmpfs) RUN_TMPFS=1; SPECIFIC_TEST=1; shift ;;
    --no-new-privs|--nnp) RUN_NNP=1; SPECIFIC_TEST=1; shift ;;
    --all) RUN_TMPFS=1; RUN_NNP=1; SPECIFIC_TEST=1; shift ;;
    --docker) USE_DOCKER=1; shift ;;
    --native) FORCE_NATIVE=1; shift ;;
    -h|--help)
      cat <<EOF
${BOLD}OpenOptOut Hardening Verification Suite${NC}

Flags:
  --all            Run both tmpfs sizing and no-new-privileges probes (default)
  --tmpfs          Run ephemeral RAM /tmp stress and leak benchmark
  --no-new-privs   Run container no-new-privileges and bubblewrap compatibility probe
  --docker         Execute inside Docker Compose 'api' container
  --native         Execute directly in host Python environment
EOF
      exit 0
      ;;
    *) die "Unknown argument: $1" ;;
  esac
done

if [ "$SPECIFIC_TEST" -eq 0 ]; then
  RUN_TMPFS=1
  RUN_NNP=1
fi

# Auto-detect Docker
if [ "$FORCE_NATIVE" -eq 0 ] && [ "$USE_DOCKER" -eq 0 ]; then
  if command -v docker >/dev/null 2>&1 && docker compose ps --services 2>/dev/null | grep -q "api"; then
    USE_DOCKER=1
  fi
fi

run_test() {
  local script_rel="$1"
  shift
  if [ "$USE_DOCKER" -eq 1 ]; then
    local target="$script_rel"
    if ! docker compose -f "$REPO_ROOT/docker-compose.yml" exec api test -f "$target" 2>/dev/null; then
      target="tests/$(basename "$script_rel")"
    fi
    info "Running $target inside Docker 'api' container..."
    docker compose -f "$REPO_ROOT/docker-compose.yml" exec api python3 "$target" "$@"
  else
    local py_bin="python3"
    if [ -x "/opt/openoptout/venv/bin/python3" ]; then
      py_bin="/opt/openoptout/venv/bin/python3"
    fi
    info "Running $script_rel locally ($py_bin)..."
    PYTHONPATH="$REPO_ROOT/backend" "$py_bin" "$REPO_ROOT/$script_rel" "$@"
  fi
}

echo
echo -e "${BOLD}${BLUE}========================================================================${NC}"
echo -e "${BOLD}${BLUE}  OpenOptOut Security Hardening Verification Test Suite${NC}"
echo -e "${BOLD}${BLUE}========================================================================${NC}"
echo

if [ "$RUN_TMPFS" -eq 1 ]; then
  run_test "deploy/tests/test_tmpfs_sizing.py" --concurrency 4 --payload-mb 25
  echo
fi

if [ "$RUN_NNP" -eq 1 ]; then
  run_test "deploy/tests/test_no_new_privs.py"
  echo
fi

info "Hardening test execution completed."
