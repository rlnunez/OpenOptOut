#!/usr/bin/env bash
# Install backend Python dependencies and optional SQLCipher encryption
set -euo pipefail

pip install --no-cache-dir -r requirements.txt

if [ "${WITH_ENCRYPTION:-false}" = "true" ]; then
  pip install --no-cache-dir -r requirements-encryption.txt \
    || echo "WARN: sqlcipher3 install failed for this platform — continuing without file-level encryption"
else
  echo "SQLCipher not requested (WITH_ENCRYPTION=false) — file-level encryption disabled"
fi
