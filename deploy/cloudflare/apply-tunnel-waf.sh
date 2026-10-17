#!/usr/bin/env bash
# ==============================================================================
# Apply OpenOptOut's rate-limiting and WAF ruleset to a Cloudflare zone.
#
# Particularly valuable for Cloudflare Tunnel deployments (where traffic bypasses
# local reverse proxies like Caddy/Traefik and reaches the app container directly),
# but can also be used with standard Cloudflare proxy deployments.
#
# Usage:
#   ./deploy/cloudflare/apply-tunnel-waf.sh --zone-id <ZONE_ID> [--token <CF_API_TOKEN>] [--dry-run]
#
# If --token is omitted, CLOUDFLARE_API_TOKEN is read from the environment or .env.
# Token requirements: Zone > WAF > Edit permission for the target zone.
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")/../.."

ZONE_ID=""
TOKEN="${CLOUDFLARE_API_TOKEN:-}"
DRY_RUN=0
RULESET_FILE="deploy/cloudflare/tunnel-waf-ruleset.json"

while [ $# -gt 0 ]; do
  case "$1" in
    --zone-id) ZONE_ID="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      awk 'NR > 2 && /^# =+$/ { exit } NR > 2 { sub(/^# ?/, ""); print }' "$0"
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$TOKEN" ] && [ -f .env ]; then
  TOKEN="$(grep -E '^CLOUDFLARE_API_TOKEN=' .env | cut -d'=' -f2- | tr -d ' "\r\n' || true)"
fi

if [ -z "$ZONE_ID" ]; then
  echo "Error: --zone-id is required (find your Zone ID in the Cloudflare dashboard on the domain Overview page)." >&2
  exit 1
fi

if [ -z "$TOKEN" ]; then
  echo "Error: Cloudflare API token is required via --token, CLOUDFLARE_API_TOKEN in environment, or .env." >&2
  exit 1
fi

if [ ! -f "$RULESET_FILE" ]; then
  echo "Error: Ruleset definition not found at $RULESET_FILE" >&2
  exit 1
fi

# Extract the rules arrays using Python's json module (available across standard environments)
python3 -c "
import json, sys
data = json.load(open('$RULESET_FILE'))
ratelimit = data['rulesets']['http_ratelimit']['rules']
firewall = data['rulesets']['http_request_firewall_custom']['rules']
" 2>/dev/null || { echo "Error: Failed to parse $RULESET_FILE" >&2; exit 1; }

echo "Cloudflare Zone ID: $ZONE_ID"
echo "Ruleset source: $RULESET_FILE"

if [ "$DRY_RUN" = 1 ]; then
  echo "Dry run mode active. No changes will be sent to Cloudflare API."
  echo "Payloads to deploy:"
  python3 -c "
import json
data = json.load(open('$RULESET_FILE'))
print('--- http_ratelimit rules ---')
print(json.dumps(data['rulesets']['http_ratelimit']['rules'], indent=2))
print('--- http_request_firewall_custom rules ---')
print(json.dumps(data['rulesets']['http_request_firewall_custom']['rules'], indent=2))
"
  exit 0
fi

# Deploy http_ratelimit rules
RATELIMIT_PAYLOAD="$(python3 -c "
import json
data = json.load(open('$RULESET_FILE'))
print(json.dumps({'rules': data['rulesets']['http_ratelimit']['rules']}))
")"

echo "Applying rate-limiting ruleset (phase: http_ratelimit)..."
HTTP_CODE="$(curl -s -o /tmp/cf_ratelimit_resp.json -w "%{http_code}" \
  -X PUT "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/http_ratelimit/entrypoint" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data "$RATELIMIT_PAYLOAD")"

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
  echo "✓ Successfully configured rate limiting rules (60 req/min auth, 1200 req/min site)."
else
  echo "✗ Failed to update http_ratelimit ruleset (HTTP $HTTP_CODE):" >&2
  cat /tmp/cf_ratelimit_resp.json >&2
  echo >&2
  exit 1
fi

# Deploy custom firewall rules
FIREWALL_PAYLOAD="$(python3 -c "
import json
data = json.load(open('$RULESET_FILE'))
print(json.dumps({'rules': data['rulesets']['http_request_firewall_custom']['rules']}))
")"

echo "Applying custom firewall ruleset (phase: http_request_firewall_custom)..."
HTTP_CODE="$(curl -s -o /tmp/cf_firewall_resp.json -w "%{http_code}" \
  -X PUT "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/http_request_firewall_custom/entrypoint" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data "$FIREWALL_PAYLOAD")"

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
  echo "✓ Successfully configured custom WAF rules (scanner block, bot challenge)."
else
  echo "✗ Failed to update http_request_firewall_custom ruleset (HTTP $HTTP_CODE):" >&2
  cat /tmp/cf_firewall_resp.json >&2
  echo >&2
  exit 1
fi

rm -f /tmp/cf_ratelimit_resp.json /tmp/cf_firewall_resp.json
echo "All Cloudflare edge WAF rules successfully deployed."

