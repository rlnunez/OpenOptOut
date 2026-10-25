#!/usr/bin/env bash
# ==============================================================================
# OpenOptOut — Local Pre-Push Security Verification Suite
#
# Runs local security scans and validations before code is pushed to git:
#   1. Repository Invariants & Security Unit Tests
#   2. Frontend Build, Undefined Symbol Check, and SRI Hash Injection
#   3. Broker Add-on Spec Validation
#   4. Static Security Linters (Bandit, Semgrep, Zizmor, Hadolint, Gitleaks, ShellCheck)
#
# Usage:
#   ./scripts/security-check.sh                # Run available scanners
#   ./scripts/security-check.sh --install-hook # Install as Git pre-push hook
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
NC='\033[0m'

if [ -n "${NO_COLOR:-}" ] || [ ! -t 1 ]; then
  BOLD='' GREEN='' BLUE='' YELLOW='' RED='' NC=''
fi

info() { printf "\n%b==>%b %s\n" "${BLUE}" "${NC}" "$*"; }
success() { printf "%b[PASS]%b %s\n" "${GREEN}" "${NC}" "$*"; }
warn() { printf "%b[SKIP/WARN]%b %s\n" "${YELLOW}" "${NC}" "$*"; }
fail() { printf "%b[FAIL]%b %s\n" "${RED}" "${NC}" "$*"; }

# ── Argument Handling ─────────────────────────────────────────────────────────
if [ "${1:-}" = "--install-hook" ]; then
  HOOK_PATH="$REPO_ROOT/.git/hooks/pre-push"
  mkdir -p "$(dirname "$HOOK_PATH")"
  cat <<'EOF' > "$HOOK_PATH"
#!/usr/bin/env bash
# OpenOptOut pre-push security gate
set -e
echo "Running OpenOptOut pre-push security verification..."
exec ./scripts/security-check.sh
EOF
  chmod +x "$HOOK_PATH"
  printf "%bInstalled pre-push hook to %s%b\n" "${GREEN}" "$HOOK_PATH" "${NC}"
  printf "Every 'git push' will now run security-check.sh automatically before uploading.\n"
  exit 0
fi

FAILED_CHECKS=0

# ── 1. Backend Security Unit Tests ───────────────────────────────────────────
info "Running backend security tests..."
if python3 -m backend.tests.run_tests --only security.; then
  success "Backend security test suite passed"
else
  fail "Backend security test suite failed"
  FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# ── 2. Broker Plugin Validation ──────────────────────────────────────────────
info "Validating broker plugins and translation coverage..."
if python3 broker-plugins/tools/validate.py > /dev/null && python3 scripts/plugin_texts.py --check > /dev/null; then
  success "Broker add-on manifests, specs, and translations are valid"
else
  fail "Broker add-on validation failed"
  FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# ── 3. Frontend Build, Symbol Check & SRI Injection ──────────────────────────
info "Validating frontend build & SRI hash generation..."
if (cd frontend && npm run check:names > /dev/null && npm run build > /dev/null); then
  success "Frontend build and SRI hash injection succeeded"
else
  fail "Frontend build failed"
  FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# ── 4. Python AST Security (Bandit) ──────────────────────────────────────────
info "Running Bandit (Python AST security linter)..."
if command -v bandit > /dev/null 2>&1; then
  if bandit -r backend -x backend/tests -s B101,B110,B112 -q; then
    success "Bandit passed (no security issues detected)"
  else
    fail "Bandit detected potential vulnerabilities in backend/"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
  fi
else
  warn "bandit not installed (install with: pip install bandit)"
fi

# ── 5. Semantic Code Analysis (Semgrep) ──────────────────────────────────────
info "Running Semgrep (Repository & OWASP rules)..."
if command -v semgrep > /dev/null 2>&1; then
  if semgrep scan --config .semgrep/ --metrics=off --disable-version-check --error backend/; then
    success "Semgrep passed with 0 findings"
  else
    fail "Semgrep reported security findings matching .semgrep/ rules"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
  fi
else
  warn "semgrep not installed (install with: pip install semgrep)"
fi

# ── 6. GitHub Actions Workflow Security (zizmor) ──────────────────────────────
info "Running zizmor (GitHub Actions workflow auditor)..."
if command -v zizmor > /dev/null 2>&1; then
  if zizmor .github/workflows/; then
    success "zizmor passed (no workflow injection or permission risks)"
  else
    fail "zizmor detected workflow security alerts"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
  fi
else
  warn "zizmor not installed (install with: brew install zizmor or cargo install zizmor)"
fi

# ── 7. Dockerfile Best Practices (Hadolint) ──────────────────────────────────
info "Running Hadolint (Dockerfile linter)..."
if command -v hadolint > /dev/null 2>&1; then
  if hadolint backend/Dockerfile frontend/Dockerfile; then
    success "Hadolint passed (Dockerfiles conform to CIS best practices)"
  else
    fail "Hadolint detected Dockerfile syntax or best-practice violations"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
  fi
else
  warn "hadolint not installed (install with: brew install hadolint)"
fi

# ── 8. Secret & Key Scanning (Gitleaks) ───────────────────────────────────────
info "Running Gitleaks (Secret and credential detection)..."
if command -v gitleaks > /dev/null 2>&1; then
  if gitleaks detect --no-git --redact > /dev/null 2>&1; then
    success "Gitleaks passed (no unencrypted credentials or API keys found)"
  else
    fail "Gitleaks detected potential secret or API key patterns"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
  fi
else
  warn "gitleaks not installed (install with: brew install gitleaks)"
fi

# ── 9. Shell Script Analysis (ShellCheck) ─────────────────────────────────────
info "Running ShellCheck (Shell script analysis)..."
if command -v shellcheck > /dev/null 2>&1; then
  if shellcheck -e SC1090,SC1091 install.sh scripts/*.sh; then
    success "ShellCheck passed with 0 errors"
  else
    fail "ShellCheck detected shell script bugs or syntax warnings"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
  fi
else
  warn "shellcheck not installed (install with: brew install shellcheck)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "======================================================================"
if [ "$FAILED_CHECKS" -eq 0 ]; then
  printf "%bAll executed security checks passed! Ready to push.%b\n" "${GREEN}${BOLD}" "${NC}"
  echo "======================================================================"
  exit 0
else
  printf "%bSecurity verification failed (%d check(s) failed). Resolve before pushing.%b\n" "${RED}${BOLD}" "$FAILED_CHECKS" "${NC}"
  echo "======================================================================"
  exit 1
fi
