#!/usr/bin/env bash
#
# Assembles the complete AGPL-3.0 LICENSE file by fetching the canonical
# license text from gnu.org and prepending the PrivacyShield copyright block.
#
# Run this ONCE locally (where you have internet) before publishing:
#   bash scripts/finalize-license.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LICENSE_FILE="$REPO_ROOT/LICENSE"
TMP_AGPL="$(mktemp)"

echo "Fetching canonical AGPL-3.0 text from gnu.org..."
if command -v curl >/dev/null 2>&1; then
  curl -fsSL https://www.gnu.org/licenses/agpl-3.0.txt -o "$TMP_AGPL"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$TMP_AGPL" https://www.gnu.org/licenses/agpl-3.0.txt
else
  echo "ERROR: need curl or wget to fetch the license text." >&2
  exit 1
fi

# Sanity check — the file should contain the AGPL title
if ! grep -q "GNU AFFERO GENERAL PUBLIC LICENSE" "$TMP_AGPL"; then
  echo "ERROR: fetched file doesn't look like the AGPL. Aborting." >&2
  exit 1
fi

echo "Writing LICENSE with copyright block + full canonical text..."
cat > "$LICENSE_FILE" <<'HEADER'
    PrivacyShield — an open-source personal data removal pipeline
    Copyright (C) 2026 Robert Nunez

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

================================================================================

HEADER

cat "$TMP_AGPL" >> "$LICENSE_FILE"
rm -f "$TMP_AGPL"

echo "Done. LICENSE now contains the copyright block and full AGPL-3.0 text."
echo "Review it, then commit."
