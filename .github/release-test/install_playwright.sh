#!/usr/bin/env bash
# Install Playwright and browser binaries for test run
set -euo pipefail

pip install --quiet "playwright==${PLAYWRIGHT_VERSION}"
python3 -m playwright install --with-deps chromium > /dev/null
