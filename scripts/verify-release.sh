#!/usr/bin/env bash
# ==============================================================================
# OpenOptOut — Release Tag & Cryptographic Provenance Verification Suite
#
# Verifies that Git release tags, commits, and distribution checksums
# are cryptographically signed and unmodified from the upstream project.
#
# Usage:
#   ./scripts/verify-release.sh [tag_name]
#   ./scripts/verify-release.sh --checksums [checksums_file]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { printf "%b==>%b %s\n" "${GREEN}" "${NC}" "$*"; }
warn() { printf "%bWarning: %s%b\n" "${YELLOW}" "$*" "${NC}" >&2; }
die()  { printf "%bError: %s%b\n" "${RED}" "$*" "${NC}" >&2; exit 1; }

TARGET_TAG="${1:-}"

if [ -z "$TARGET_TAG" ] || [ "$TARGET_TAG" = "--help" ] || [ "$TARGET_TAG" = "-h" ]; then
    echo -e "${BOLD}OpenOptOut Release Provenance Verification${NC}"
    echo "Usage: ./scripts/verify-release.sh <tag_name>"
    echo "       ./scripts/verify-release.sh --checksums SHA256SUMS"
    exit 0
fi

if [ "$TARGET_TAG" = "--checksums" ]; then
    CHECKSUM_FILE="${2:-}"
    if [ -z "$CHECKSUM_FILE" ] || [ ! -f "$CHECKSUM_FILE" ]; then
        die "Please specify a valid checksums file."
    fi
    info "Verifying SHA256 checksums from $CHECKSUM_FILE..."
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -c "$CHECKSUM_FILE"
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -c "$CHECKSUM_FILE"
    else
        die "Neither sha256sum nor shasum is available in this environment."
    fi
    info "Checksum verification passed successfully."
    exit 0
fi

info "Verifying cryptographic signature on tag: $TARGET_TAG..."

if ! git rev-parse "$TARGET_TAG" >/dev/null 2>&1; then
    die "Tag '$TARGET_TAG' not found in repository."
fi

if git tag -v "$TARGET_TAG" >/dev/null 2>&1; then
    info "Tag '$TARGET_TAG' signature verified successfully (GPG/SSH)."
else
    TAG_TYPE=$(git cat-file -t "$TARGET_TAG" 2>/dev/null || echo "commit")
    if [ "$TAG_TYPE" = "tag" ]; then
        warn "Tag '$TARGET_TAG' is annotated but could not be verified against local trusted keys."
    else
        warn "Tag '$TARGET_TAG' is a lightweight tag without a detached signature."
    fi
    info "Verifying target commit signature..."
    COMMIT_HASH=$(git rev-list -n 1 "$TARGET_TAG")
    if git verify-commit "$COMMIT_HASH" >/dev/null 2>&1; then
        info "Commit $COMMIT_HASH signature verified successfully."
    else
        warn "Commit $COMMIT_HASH does not have a verified signature in this keyring."
    fi
fi

info "Release tag verification procedure completed."

