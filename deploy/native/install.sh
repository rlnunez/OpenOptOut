#!/usr/bin/env bash
# ==============================================================================
# Native (no Docker) install/update for PrivacyShield, on Debian/Ubuntu Linux.
#
#   sudo ./deploy/native/install.sh                # first install (interactive wizard or flags)
#   sudo ./deploy/native/install.sh --update        # pull code changes back in
#
# Seamlessly hands off to the unified interactive host & fleet installer (Roadmap Item 23):
#   deploy/installer/setup.sh
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/../installer/setup.sh" "$@"
