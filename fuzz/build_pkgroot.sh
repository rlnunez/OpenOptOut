#!/usr/bin/env bash
# Make the backend importable as the package `app`, exactly like backend/Dockerfile
# does (the code uses package-relative imports such as `from ..core import ...`).
#
#   fuzz/build_pkgroot.sh [DEST]      (default DEST: fuzz/.pkgroot)
#
# Afterwards `import app.core.interpreter.broker_spec` works with DEST on sys.path.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"
dest="${1:-$here/.pkgroot}"

rm -rf "$dest"
mkdir -p "$dest"
cp -r "$repo/backend" "$dest/app"
for d in "$dest/app" "$dest/app/models" "$dest/app/routers" "$dest/app/core"; do
  [ -d "$d" ] && touch "$d/__init__.py"
done
echo "Backend package ready at $dest/app"
