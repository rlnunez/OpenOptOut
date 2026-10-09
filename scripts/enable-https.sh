#!/usr/bin/env bash
# ==============================================================================
# Turn on HTTPS for OpenOptOut (Caddy front door + automatic certificates).
#
#   ./scripts/enable-https.sh                       # interactive
#   ./scripts/enable-https.sh --mode letsencrypt --domain privacy.lib.org --email it@lib.org
#   ./scripts/enable-https.sh --disable             # back to plain HTTP
#
# Options: --mode letsencrypt|letsencrypt-staging|acme|internal|custom
#          --domain D  --email E  --acme-ca URL  --acme-ca-root FILE
#          --env-file PATH (default .env)  --yes (no confirmation prompt)
#
# Writes settings to .env (a timestamped backup is made first), then tell you the
# one command to run. Works on Linux and macOS (no GNU-only tools).
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env"; MODE=""; DOMAIN=""; EMAIL=""; ACME_CA=""; ACME_CA_ROOT_SRC=""; YES=0; DISABLE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --acme-ca) ACME_CA="$2"; shift 2 ;;
    --acme-ca-root) ACME_CA_ROOT_SRC="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --yes|-y) YES=1; shift ;;
    --disable) DISABLE=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

die()  { echo "Error: $*" >&2; exit 1; }
warn() { echo "Warning: $*" >&2; }
# Prompt only when a person is at the terminal. With --yes, or when stdin isn't a
# terminal (automation/CI), never block: use the default; required values that
# are still missing are then rejected by validation.
ask()  {
  local prompt="$1" def="${2:-}" ans=""
  if [ "$YES" = 1 ] || [ ! -t 0 ]; then echo "$def"; return 0; fi
  read -r -p "$prompt${def:+ [$def]}: " ans || true
  echo "${ans:-$def}"
}
valid_domain() { [[ "$1" =~ ^[A-Za-z0-9*.-]+(,\ *[A-Za-z0-9*.-]+)*$ ]]; }
valid_email()  { [[ "$1" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; }

# Set KEY=VALUE in the env file: replace an existing (uncommented) line, else append.
set_env() {
  local key="$1" val="$2" tmp; tmp="$(mktemp)"
  if [ -f "$ENV_FILE" ] && grep -q "^${key}=" "$ENV_FILE"; then
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k {print k"="v; next} {print}' "$ENV_FILE" > "$tmp"
  else
    { [ -f "$ENV_FILE" ] && cat "$ENV_FILE"; echo "${key}=${val}"; } > "$tmp"
  fi
  mv "$tmp" "$ENV_FILE"
}
unset_env() {
  local key="$1" tmp; [ -f "$ENV_FILE" ] || return 0; tmp="$(mktemp)"
  grep -v "^${key}=" "$ENV_FILE" > "$tmp" || true; mv "$tmp" "$ENV_FILE"
}
backup() { [ -f "$ENV_FILE" ] && cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)" && echo "Backed up $ENV_FILE"; return 0; }

if [ "$DISABLE" = 1 ]; then
  backup
  for k in COMPOSE_PROFILES HTTPS_MODE DOMAIN ACME_EMAIL ACME_CA ACME_CA_ROOT WEB_BIND WEB_PORT TRUSTED_PROXY_HOPS; do unset_env "$k"; done
  set_env FRONTEND_URL "http://localhost"
  echo "HTTPS disabled. Run:  docker compose down && docker compose up -d"
  exit 0
fi

[ -f "$ENV_FILE" ] || die "$ENV_FILE not found. Create it first (cp .env.example .env)."

if [ -z "$MODE" ]; then
  echo "How should OpenOptOut get its certificate?"
  echo "  1) letsencrypt          public server (ports 80+443 reachable from the internet)"
  echo "  2) letsencrypt-staging  same, but Let's Encrypt's TEST service (untrusted certs; use first)"
  echo "  3) acme                 your own ACME CA (e.g. internal step-ca)"
  echo "  4) internal             Caddy's own private CA (LAN only; browsers warn until trusted)"
  echo "  5) custom               certificate files you provide"
  case "$(ask 'Choose 1-5' 2)" in
    1) MODE=letsencrypt ;; 2) MODE=letsencrypt-staging ;; 3) MODE=acme ;; 4) MODE=internal ;; 5) MODE=custom ;;
    *) die "Please choose 1-5." ;;
  esac
fi
case "$MODE" in letsencrypt|letsencrypt-staging|acme|internal|custom) ;; *) die "Unknown mode: $MODE" ;; esac

[ -n "$DOMAIN" ] || DOMAIN="$(ask 'Domain name people will use (e.g. privacy.yourlibrary.org)')"
valid_domain "$DOMAIN" || die "Invalid domain: $DOMAIN"
PRIMARY="${DOMAIN%%,*}"

if [ -z "$EMAIL" ] && [ "$MODE" != internal ] && [ "$MODE" != custom ]; then
  EMAIL="$(ask 'Contact email for the certificate authority (recommended)' '')"
fi
[ -z "$EMAIL" ] || valid_email "$EMAIL" || die "Invalid email: $EMAIL"

ACME_CA_ROOT=""
if [ "$MODE" = acme ]; then
  [ -n "$ACME_CA" ] || ACME_CA="$(ask 'ACME directory URL (e.g. https://ca.internal/acme/acme/directory)')"
  [[ "$ACME_CA" =~ ^https://[A-Za-z0-9.:/_~%-]+$ ]] || die "ACME CA must be an https:// URL"
  if [ -z "$ACME_CA_ROOT_SRC" ] && [ "$YES" = 0 ]; then
    ACME_CA_ROOT_SRC="$(ask 'Path to the CA root certificate, if the ACME server uses an internal CA (blank = none)' '')"
  fi
  if [ -n "$ACME_CA_ROOT_SRC" ]; then
    [ -f "$ACME_CA_ROOT_SRC" ] || die "File not found: $ACME_CA_ROOT_SRC"
    grep -q "BEGIN CERTIFICATE" "$ACME_CA_ROOT_SRC" || die "Not a PEM certificate: $ACME_CA_ROOT_SRC"
    mkdir -p deploy/certs && cp "$ACME_CA_ROOT_SRC" deploy/certs/acme-ca-root.pem
    ACME_CA_ROOT="/certs/acme-ca-root.pem"
  fi
fi

if [ "$MODE" = custom ]; then
  for f in deploy/certs/fullchain.pem deploy/certs/privkey.pem; do
    [ -f "$f" ] || die "Put your certificate files in deploy/certs/ first: fullchain.pem and privkey.pem ($f missing)."
  done
fi

# ── preflight ──
if [ "$MODE" = letsencrypt ] || [ "$MODE" = letsencrypt-staging ]; then
  ip=""
  if command -v getent >/dev/null; then ip="$(getent hosts "$PRIMARY" | awk '{print $1; exit}')";
  elif command -v host >/dev/null; then ip="$(host "$PRIMARY" 2>/dev/null | awk '/has address/{print $4; exit}')"; fi
  if [ -z "$ip" ]; then
    warn "$PRIMARY does not resolve in DNS yet. Let's Encrypt needs a DNS record pointing to this server."
  else
    echo "DNS: $PRIMARY -> $ip"
  fi
  echo "Let's Encrypt must reach this server on ports 80 and 443 from the internet (router/firewall)."
  [ "$MODE" = letsencrypt ] && echo "Tip: test with letsencrypt-staging first to avoid rate limits, then switch."
fi

echo
echo "About to enable HTTPS:  mode=$MODE  domain=$DOMAIN${EMAIL:+  email=$EMAIL}"
if [ "$YES" = 0 ]; then [ "$(ask 'Continue? (y/n)' y)" = y ] || die "Cancelled."; fi

backup
set_env COMPOSE_PROFILES https
set_env HTTPS_MODE "$MODE"
set_env DOMAIN "$DOMAIN"
if [ -n "$EMAIL" ]; then set_env ACME_EMAIL "$EMAIL"; else unset_env ACME_EMAIL; fi
if [ -n "$ACME_CA" ]; then set_env ACME_CA "$ACME_CA"; else unset_env ACME_CA; fi
if [ -n "$ACME_CA_ROOT" ]; then set_env ACME_CA_ROOT "$ACME_CA_ROOT"; else unset_env ACME_CA_ROOT; fi
# Caddy owns ports 80/443; the web container stays reachable only on this machine.
set_env WEB_BIND 127.0.0.1
set_env WEB_PORT 8080
set_env TRUSTED_PROXY_HOPS 2     # Caddy + nginx in front of the API
set_env FRONTEND_URL "https://$PRIMARY"

echo
echo "HTTPS settings saved to $ENV_FILE. Now run:"
echo "    docker compose up -d --build"
echo "Then open https://$PRIMARY  (first certificate can take a minute)."
echo "Watch progress:  docker compose logs -f caddy"
[ "$MODE" = internal ] && echo "Browsers will warn until Caddy's root CA is trusted — see docs/HTTPS.md."
[ "$MODE" = letsencrypt-staging ] && echo "Staging certificates are intentionally untrusted. Rerun with --mode letsencrypt when it works."
echo "If you use Google/Microsoft sign-in or SAML, update their redirect URLs to https://$PRIMARY (docs/SSO.md)."
exit 0
