#!/usr/bin/env bash
# Install security scanners (Semgrep, Bandit)
set -euo pipefail

pip install "semgrep==${SEMGREP_VERSION}" "bandit[sarif]==${BANDIT_VERSION}"
