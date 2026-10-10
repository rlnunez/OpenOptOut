#!/usr/bin/env bash
# ==============================================================================
# Refresh deploy/cloudflare/ip-ranges.txt from Cloudflare's published lists.
# Used with CLOUDFLARE_PROXY=on: front door accepts connections ONLY from these ranges.
# Run periodically or via cron, then restart the front door:
#   ./scripts/update-cloudflare-ips.sh && docker compose up -d --force-recreate caddy-extended
#   (or: ... traefik / caddy — whichever front door is running)
# Validates IP range format before writing; refuses empty or partial downloads.
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="deploy/cloudflare/ip-ranges.txt"
tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT

fetch() { curl -fsS --max-time 20 "$1"; }
v4="$(fetch https://www.cloudflare.com/ips-v4)" || { echo "Error: couldn't download https://www.cloudflare.com/ips-v4" >&2; exit 1; }
v6="$(fetch https://www.cloudflare.com/ips-v6)" || { echo "Error: couldn't download https://www.cloudflare.com/ips-v6" >&2; exit 1; }

{
  echo "# Cloudflare's published IP ranges (https://www.cloudflare.com/ips/), used when"
  echo "# CLOUDFLARE_PROXY=on: the front door accepts connections ONLY from these ranges and trusts CF-Connecting-IP."
  echo "# Refresh with:  ./scripts/update-cloudflare-ips.sh (they rarely change)"
  echo "# Last updated: $(date +%Y-%m-%d)"
} > "$tmp"
count=0
while IFS= read -r line; do
  line="$(printf '%s' "$line" | tr -d ' \t\r')"
  [ -n "$line" ] || continue
  [[ "$line" =~ ^[0-9A-Fa-f:.]+/[0-9]{1,3}$ ]] || { echo "Error: unexpected line from Cloudflare: $line" >&2; exit 1; }
  echo "$line" >> "$tmp"; count=$((count + 1))
done <<< "$v4"$'\n'"$v6"
[ "$count" -ge 5 ] || { echo "Error: only $count ranges downloaded; keeping the current list." >&2; exit 1; }

if [ -f "$OUT" ] && diff -q <(grep -v '^#' "$OUT") <(grep -v '^#' "$tmp") >/dev/null; then
  echo "Cloudflare IP ranges unchanged ($count ranges)."
  exit 0
fi
cp "$tmp" "$OUT"
echo "Updated $OUT ($count ranges). Restart your front door to apply."
