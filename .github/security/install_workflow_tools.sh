#!/usr/bin/env bash
# Install workflow analysis tools (zizmor, actionlint)
set -euo pipefail

pip install "zizmor==${ZIZMOR_VERSION}" "actionlint-py==${ACTIONLINT_PY_VERSION}"
