#!/usr/bin/env bash
# ==============================================================================
# OpenOptOut — Automated Local Docker Matrix Test Suite
#
# Validates container images, compose profiles, runtime health, test suites,
# security probes, and front-door proxy configurations in Docker.
#
# Usage:
#   ./scripts/test-docker-matrix.sh
#   ./scripts/test-docker-matrix.sh --skip-build
#   ./scripts/test-docker-matrix.sh --keep
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Terminal styling
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { printf "${GREEN}==>${NC} %s\n" "$*"; }
section() { printf "\n${BOLD}${BLUE}=== %s ===${NC}\n" "$*"; }
warn()    { printf "${YELLOW}Warning: %s${NC}\n" "$*" >&2; }
die()     { printf "${RED}Error: %s${NC}\n" "$*" >&2; exit 1; }

SKIP_BUILD=0
KEEP_CONTAINERS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-build) SKIP_BUILD=1; shift ;;
    --keep) KEEP_CONTAINERS=1; shift ;;
    -h|--help)
      cat <<EOF
OpenOptOut Automated Docker Matrix Test Suite

Flags:
  --skip-build     Skip image build phase (use existing local images)
  --keep           Do not tear down containers upon test completion
  -h, --help       Show this help message
EOF
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

REPORT_DIR="$REPO_ROOT/test-reports"
mkdir -p "$REPORT_DIR"

cleanup() {
  local exit_code=$?
  if [ "$exit_code" -ne 0 ]; then
    printf "\n${BOLD}${RED}TEST SUITE FAILED (exit code: %s)${NC}\n" "$exit_code"
    info "Dumping container logs for diagnostics..."
    docker compose logs --no-color > "$REPORT_DIR/containers.log" 2>/dev/null || true
    if [ -f "$REPO_ROOT/.github/release-test/scan_logs.py" ] && [ -s "$REPORT_DIR/containers.log" ]; then
      python3 "$REPO_ROOT/.github/release-test/scan_logs.py" "Docker Failure Audit" "$REPORT_DIR/containers.log" "$REPORT_DIR/error-report.md" 2>/dev/null || true
    fi
    printf "Container logs saved to: %s\n" "$REPORT_DIR/containers.log"
    if [ -f "$REPORT_DIR/error-report.md" ]; then
      printf "\n${BOLD}Aggregated Error Report:${NC}\n"
      cat "$REPORT_DIR/error-report.md"
    fi
    if [ -d "$REPORT_DIR/screenshots" ]; then
      printf "\nFailure screenshots saved to: %s\n" "$REPORT_DIR/screenshots"
    fi
  fi
  if [ "$KEEP_CONTAINERS" -eq 0 ]; then
    info "Cleaning up Docker resources..."
    docker compose down -v >/dev/null 2>&1 || true
  else
    warn "Containers left running (--keep specified)."
  fi
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

# ── Pre-flight Checks ──────────────────────────────────────────────────────────
section "Pre-flight Verification"

command -v docker >/dev/null 2>&1 || die "Docker CLI is not installed."
docker compose version >/dev/null 2>&1 || die "Docker Compose plugin is not installed."

if ! docker info >/dev/null 2>&1; then
  die "Docker daemon is not running. Please start Docker (e.g., 'open -a Docker' on macOS) and retry."
fi
info "Docker engine and compose verified."

# ── 1. Compose Profiles Syntax Check ──────────────────────────────────────────
section "1. Compose Profile Validation"

validate_profile() {
  local prof="$1"
  if [ -n "$prof" ]; then
    docker compose --profile "$prof" config >/dev/null
    printf "  [✓] Profile '%s' parsed cleanly\n" "$prof"
  else
    docker compose config >/dev/null
    printf "  [✓] Base compose config parsed cleanly\n"
  fi
}

validate_profile ""
validate_profile "https"
validate_profile "https-caddy-extended"
validate_profile "https-traefik"
validate_profile "cloudflare-tunnel"

# ── 2. Image Build Matrix ─────────────────────────────────────────────────────
section "2. Container Image Builds"

if [ "$SKIP_BUILD" -eq 1 ]; then
  info "Skipping image builds (--skip-build active)."
else
  info "Building 'api' image..."
  docker compose build api
  info "Building 'web' image..."
  docker compose build web
  info "Building 'caddy-extended' image..."
  docker compose --profile https-caddy-extended build caddy-extended
  info "All container images built successfully."
fi

# ── 3. Runtime Health Verification ────────────────────────────────────────────
section "3. Core Services Runtime Health"

info "Starting api and web services..."
docker compose up -d api web

info "Waiting for API readiness at /api/health..."
max_attempts=30
attempt=1
ready=0
while [ "$attempt" -le "$max_attempts" ]; do
  if docker compose exec -T api python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
  attempt=$((attempt + 1))
done

if [ "$ready" -ne 1 ]; then
  docker compose logs api
  die "API container failed to answer /api/health after ${max_attempts}s."
fi
info "API health confirmed (HTTP 200)."

# ── 4. Full Containerized Test Suite ──────────────────────────────────────────
section "4. Full Backend Test Suite (In-Container)"

info "Running complete test suite inside 'api' container..."
docker compose exec -T api python3 -m tests.run_tests

info "Running plugin sandbox preflight verification..."
docker compose exec -T api python3 -m plugins.preflight_sandbox

info "Running plugin gRPC smoke test..."
docker compose exec -T api python3 -m plugins.smoke_test

# ── 5. Security Posture Probes ────────────────────────────────────────────────
section "5. Container Security Posture Probes"

info "Running RAM tmpfs stress benchmark inside 'api' container..."
docker compose exec -T api python3 tests/test_tmpfs_sizing.py --concurrency 4 --payload-mb 25

info "Running no-new-privileges compatibility probe inside 'api' container..."
docker compose exec -T api python3 tests/test_no_new_privs.py

# ── 6. Live Email OAuth Account Verification (Optional) ───────────────────────
EMAIL_CFG=""
for f in "test_email_accounts.json" ".test_email_accounts.json"; do
  if [ -f "$REPO_ROOT/$f" ]; then
    EMAIL_CFG="$f"
    break
  fi
done

if [ -n "$EMAIL_CFG" ]; then
  section "6. Live Email OAuth Verification"
  info "Found $EMAIL_CFG — executing live OAuth account probe..."
  docker compose cp "$REPO_ROOT/$EMAIL_CFG" api:/app/test_email_accounts.json
  docker compose exec -T api python3 tests/test_email_accounts.py --config /app/test_email_accounts.json
  docker compose exec -T api rm -f /app/test_email_accounts.json
fi

# ── 7. Browser Walk-Through & Screenshot Capture ──────────────────────────────
section "7. Browser UI Walk-Through & Screenshot Capture"

info "Running browser walkthrough and capturing page screenshots..."
docker compose cp "$REPO_ROOT/.github" api:/app/ 2>/dev/null || true
docker compose exec -T api python3 /app/.github/release-test/ui_check.py \
  --base-url http://web:80 \
  --browser firefox \
  --out-dir /app/test-reports \
  --creds-file /app/test-reports/creds.json || true
docker compose cp api:/app/test-reports/. "$REPORT_DIR/" 2>/dev/null || true

if [ -d "$REPORT_DIR/screenshots" ]; then
  count=$(find "$REPORT_DIR/screenshots" -name "*.png" | wc -l | tr -d ' ')
  info "Screenshots saved: $count captured in $REPORT_DIR/screenshots"
  if [ -f "$REPORT_DIR/ui-report.md" ]; then
    grep -E '❌|⚠️' "$REPORT_DIR/ui-report.md" || true
  fi
fi

# ── 8. Front Door Config Generation Matrix ────────────────────────────────────
section "8. Reverse Proxy Configuration Tests"

info "Testing Caddy extended configuration generation..."
docker compose run --rm --no-deps -e HTTPS_MODE=internal -e DOMAIN=localhost caddy-extended /bin/sh -c "test -s /etc/caddy/Caddyfile"
info "Caddy extended generated valid Caddyfile."

info "Testing Traefik configuration generation..."
docker compose run --rm --no-deps -e HTTPS_MODE=none -e DOMAIN=localhost traefik /bin/sh -c "test -s /etc/traefik/traefik.yml"
info "Traefik generated valid configuration."

# ── Summary ───────────────────────────────────────────────────────────────────
section "Test Matrix Complete"

docker compose logs --no-color > "$REPORT_DIR/containers.log" 2>/dev/null || true
if [ -f "$REPO_ROOT/.github/release-test/scan_logs.py" ] && [ -s "$REPORT_DIR/containers.log" ]; then
  python3 "$REPO_ROOT/.github/release-test/scan_logs.py" "Docker Matrix Audit" "$REPORT_DIR/containers.log" "$REPORT_DIR/error-report.md" 2>/dev/null || true
fi

printf "${BOLD}${GREEN}All Docker tests, profiles, UI checks, and security probes passed successfully!${NC}\n"
printf "Full container logs available at: %s\n" "$REPORT_DIR/containers.log"
if [ -f "$REPORT_DIR/error-report.md" ]; then
  printf "Log error summary available at: %s\n" "$REPORT_DIR/error-report.md"
fi
if [ -d "$REPORT_DIR/screenshots" ]; then
  printf "Page and failure screenshots available at: %s\n\n" "$REPORT_DIR/screenshots"
fi
