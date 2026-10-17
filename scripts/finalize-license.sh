#!/usr/bin/env bash
#
# Assembles the complete AGPL-3.0 LICENSE file by fetching the canonical
# license text from gnu.org and prepending the OpenOptOut copyright block.
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
    OpenOptOut — an open-source personal data removal pipeline
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

cat >> "$LICENSE_FILE" <<'FOOTER'

ADDITIONAL TERMS UNDER SECTION 7 OF THE GNU AFFERO GENERAL PUBLIC LICENSE

The following additional terms apply to this program and to any covered work that includes all or part of it.
1. Attribution (Section 7(b)). You must keep the following attribution in the Appropriate Legal Notices shown by any covered work with an interactive user interface, and in any notice file, documentation or “About” information distributed with it:

“Based on OpenOptOut by Robert Nunez and contributors — https://github.com/rlnunez/Privacy-Shield. Includes work from the projects listed in CREDITS.md.”

You must also keep the CREDITS.md file, unchanged except for additions, in any copy you distribute, and link to it from the same notice. You may add your own credits, but you may not remove existing ones.

The attribution must be legible and easy to find from the main screen, for example in an About page, a footer or a Help menu.

2. Marking modified versions (Section 7(c)). A modified version must be clearly marked as different from the original, and must not be presented as the official OpenOptOut project.

3. Project name (Section 7(e)). This license does not grant permission to use the name “OpenOptOut” or its logo to name or promote a modified version, except to give the attribution required above.
FOOTER

echo "Done. LICENSE now contains the copyright block, full AGPL-3.0 text, and Section 7 additional terms."
echo "Review it, then commit."

