#!/usr/bin/env bash
# ==============================================================================
# Set up OpenOptOut's front door: how people reach it, and how it gets HTTPS.
#
#   ./scripts/enable-https.sh                       # interactive setup
#   ./scripts/enable-https.sh --proxy caddy --cert letsencrypt --domain privacy.lib.org --email it@lib.org
#   ./scripts/enable-https.sh --proxy traefik --cert cloudflare-dns --domain home.example.org
#   ./scripts/enable-https.sh --proxy cloudflare-tunnel --domain home.example.org
#   ./scripts/enable-https.sh --disable             # back to plain HTTP, no front door
#
# Step 1, --proxy:  caddy (default) | traefik | cloudflare-tunnel
# Step 2, --cert (Caddy/Traefik only):
#          letsencrypt      Let's Encrypt; ports 80/443 must reach server
#          cloudflare-dns   Let's Encrypt via Cloudflare DNS (no open ports; token: --cf-token)
#          none             Plain HTTP through the reverse proxy
#          advanced         Choose a specific --mode below
# Step 3 (cloudflare-dns or custom only), --cloudflare-proxy: DDoS protection via Cloudflare
# Rate limits (Caddy/Traefik; on by default):
#          --no-rate-limit   --rate-limit N (per visitor per min, default 1200)
#          --auth-rate-limit N (sign-in attempts per visitor per min, default 60)
# Advanced: --mode letsencrypt|letsencrypt-staging|acme|incommon|internal|custom|none
#          --mode incommon (BETA, untested): InCommon certs via CERTInext (needs EAB keys)
#          --eab-kid K --eab-hmac H   EAB account credentials for ACME CAs
#          --key-type rsa2048|rsa4096|p256|p384   key type (incommon forces rsa2048)
#          --acme-ca URL  --acme-ca-root FILE
# Other:   --domain D  --email E  --cf-token T  --tunnel-token T
#          --env-file PATH (default .env)  --yes (non-interactive; use defaults)
#
# Backs up .env before applying changes. Compatible with Linux and macOS.
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env"; MODE=""; CERT=""; DOMAIN=""; EMAIL=""; ACME_CA=""; ACME_CA_ROOT_SRC=""
YES=0; DISABLE=0; PROXY=""; CF_TOKEN=""; TUNNEL_TOKEN=""; CF_PROXY=""; RL=on; RL_SITE=""; RL_AUTH=""
EAB_KID=""; EAB_HMAC=""; KEY_TYPE=""
INCOMMON_CA_DEFAULT="https://acme-us.certinext.io/v1/directory"
while [ $# -gt 0 ]; do
  case "$1" in
    --proxy) PROXY="$2"; shift 2 ;;
    --cert) CERT="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --acme-ca) ACME_CA="$2"; shift 2 ;;
    --acme-ca-root) ACME_CA_ROOT_SRC="$2"; shift 2 ;;
    --cf-token) CF_TOKEN="$2"; shift 2 ;;
    --tunnel-token) TUNNEL_TOKEN="$2"; shift 2 ;;
    --eab-kid) EAB_KID="$2"; shift 2 ;;
    --eab-hmac) EAB_HMAC="$2"; shift 2 ;;
    --key-type) KEY_TYPE="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --yes|-y) YES=1; shift ;;
    --disable) DISABLE=1; shift ;;
    --cloudflare-proxy) CF_PROXY=on; shift ;;
    --no-cloudflare-proxy) CF_PROXY=off; shift ;;
    --no-rate-limit) RL=off; shift ;;
    --rate-limit) RL_SITE="$2"; shift 2 ;;
    --auth-rate-limit) RL_AUTH="$2"; shift 2 ;;
    -h|--help) awk 'NR > 2 && /^# =+$/ { exit } NR > 2 { sub(/^# ?/, ""); print }' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

die()  { echo "Error: $*" >&2; exit 1; }
warn() { echo "Warning: $*" >&2; }
interactive() { [ "$YES" = 0 ] && [ -t 0 ]; }
# Prompt only at interactive terminal. Defaults used under --yes or non-interactive stdin.
ask()  {
  local prompt="$1" def="${2:-}" ans=""
  if ! interactive; then echo "$def"; return 0; fi
  read -r -p "$prompt${def:+ [$def]}: " ans || true
  echo "${ans:-$def}"
}
# Same, without echoing what's typed (tokens).
ask_secret() {
  local prompt="$1" ans=""
  if ! interactive; then echo ""; return 0; fi
  read -r -s -p "$prompt: " ans || true
  echo >&2
  echo "$ans"
}
valid_domain() { [[ "$1" =~ ^[A-Za-z0-9*.-]+(,\ *[A-Za-z0-9*.-]+)*$ ]]; }
valid_email()  { [[ "$1" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; }
# Tokens go into .env, so allow only their real character sets (no newlines/quotes).
valid_cf_token()     { [[ "$1" =~ ^[A-Za-z0-9_-]{20,}$ ]]; }
valid_tunnel_token() { [[ "$1" =~ ^[A-Za-z0-9+/=_.-]{20,}$ ]]; }

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
has_env() { [ -f "$ENV_FILE" ] && grep -q "^${1}=." "$ENV_FILE"; }
backup() { [ -f "$ENV_FILE" ] && cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)" && echo "Backed up $ENV_FILE"; return 0; }

FRONT_DOOR_KEYS="COMPOSE_PROFILES FRONT_DOOR HTTPS_CHECK_HOST HTTPS_MODE ACME_CHALLENGE DOMAIN ACME_EMAIL ACME_CA ACME_CA_ROOT ACME_EAB_KID ACME_EAB_HMAC ACME_KEY_TYPE WEB_BIND WEB_PORT TRUSTED_PROXY_HOPS RATE_LIMIT CLOUDFLARE_PROXY"

if [ "$DISABLE" = 1 ]; then
  backup
  # Tokens too: no reason to keep Cloudflare credentials around with this off.
  for k in $FRONT_DOOR_KEYS RATE_LIMIT_PER_MINUTE AUTH_RATE_LIMIT_PER_MINUTE CLOUDFLARE_API_TOKEN CLOUDFLARE_TUNNEL_TOKEN; do unset_env "$k"; done
  set_env FRONTEND_URL "http://localhost"
  echo "Front door disabled. Run:  docker compose down && docker compose up -d"
  exit 0
fi

[ -f "$ENV_FILE" ] || die "$ENV_FILE not found. Create it first (cp .env.example .env)."

# ── step 1: front door ────────────────────────────────────────────────────────
if [ -z "$PROXY" ]; then
  if interactive; then
    echo "How should people reach OpenOptOut?"
    echo "  1) Caddy              Built-in front door. Recommended if you have no preference."
    echo "  2) Traefik            Built-in front door, for teams that already use Traefik."
    echo "  3) Cloudflare Tunnel  No open ports or router setup at all."
    echo "                        WARNING: Cloudflare decrypts and can see all traffic."
    case "$(ask 'Choose 1-3' 1)" in
      1) PROXY=caddy ;; 2) PROXY=traefik ;; 3) PROXY=cloudflare-tunnel ;;
      *) die "Please choose 1-3." ;;
    esac
    echo
  else
    PROXY=caddy
  fi
fi
case "$PROXY" in caddy|traefik|cloudflare-tunnel) ;; *) die "--proxy must be caddy, traefik, or cloudflare-tunnel" ;; esac

# ── Cloudflare Tunnel: its own short path (Cloudflare holds the certificate) ──
if [ "$PROXY" = cloudflare-tunnel ]; then
  [ -z "$CERT$MODE" ] || die "--cert/--mode don't apply to Cloudflare Tunnel: Cloudflare issues the certificate."
  [ "$CF_PROXY" != on ] || die "--cloudflare-proxy doesn't apply to Cloudflare Tunnel: tunnel traffic already goes through Cloudflare."
  cat <<'EOF'
────────────────────────────────────────────────────────────────────────────────
 WARNING: with Cloudflare Tunnel, Cloudflare decrypts ALL traffic to this site.
 Cloudflare's servers can see everything people send and receive here: names,
 home addresses, phone numbers, email addresses, and sign-in tokens.
 If that isn't acceptable, choose Caddy or Traefik with "Let's Encrypt via
 Cloudflare DNS" instead: no open ports needed, and Cloudflare only ever sees a
 DNS record, never your traffic.
────────────────────────────────────────────────────────────────────────────────
EOF
  if interactive; then
    [ "$(ask 'Type yes to use Cloudflare Tunnel anyway')" = yes ] || die "Cancelled. Nothing was changed."
  fi
  [ -n "$DOMAIN" ] || DOMAIN="$(ask 'Public hostname you set (or will set) on the tunnel (e.g. privacy.example.org)')"
  [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || die "Enter one hostname, like privacy.example.org (got: ${DOMAIN:-nothing})."
  if [ -z "$TUNNEL_TOKEN" ] && ! has_env CLOUDFLARE_TUNNEL_TOKEN; then
    TUNNEL_TOKEN="$(ask_secret 'Tunnel token from the Cloudflare dashboard (blank = add it to .env later)')"
  fi
  [ -z "$TUNNEL_TOKEN" ] || valid_tunnel_token "$TUNNEL_TOKEN" || die "That doesn't look like a tunnel token (copy the long value after --token)."

  backup
  for k in $FRONT_DOOR_KEYS; do unset_env "$k"; done
  set_env COMPOSE_PROFILES cloudflare-tunnel
  set_env FRONT_DOOR cloudflare-tunnel
  set_env HTTPS_MODE cloudflare-tunnel   # tells the certificate monitor not to check
  set_env DOMAIN "$DOMAIN"
  [ -z "$TUNNEL_TOKEN" ] || set_env CLOUDFLARE_TUNNEL_TOKEN "$TUNNEL_TOKEN"
  # Nothing listens publicly: the tunnel reaches the web container internally.
  set_env WEB_BIND 127.0.0.1
  set_env WEB_PORT 8080
  set_env TRUSTED_PROXY_HOPS 2     # cloudflared + nginx in front of the API
  set_env FRONTEND_URL "https://$DOMAIN"
  echo
  echo "Settings saved to $ENV_FILE."
  if ! has_env CLOUDFLARE_TUNNEL_TOKEN; then
    echo "Before starting, finish the Cloudflare side (docs/HTTPS.md, Option D):"
    echo "  1. Cloudflare dashboard > Zero Trust > Networks > Tunnels > Create a tunnel (Cloudflared)."
    echo "  2. Copy its token into $ENV_FILE as  CLOUDFLARE_TUNNEL_TOKEN=..."
    echo "  3. Add a public hostname: $DOMAIN  ->  Service: HTTP, URL: web:80"
    echo "Then run:  docker compose up -d"
  else
    echo "In the Cloudflare dashboard, make sure the tunnel's public hostname is"
    echo "  $DOMAIN  ->  Service: HTTP, URL: web:80"
    echo "Then run:  docker compose up -d   and open https://$DOMAIN"
  fi
  echo "Watch progress:  docker compose logs -f cloudflared"
  echo "If you use Google/Microsoft sign-in or SAML, update their redirect URLs to https://$DOMAIN (docs/SSO.md)."
  exit 0
fi

# ── step 2: certificate (Caddy / Traefik) ─────────────────────────────────────
if [ -z "$CERT" ] && [ -z "$MODE" ]; then
  if interactive; then
    echo "Where should the HTTPS certificate come from?"
    echo "  1) Let's Encrypt                     Free and automatic. Ports 80 and 443 must"
    echo "                                       be reachable from the internet."
    echo "  2) Let's Encrypt via Cloudflare DNS  Free and automatic, NO open ports needed."
    echo "                                       Your domain's DNS must be on Cloudflare."
    echo "                                       Cloudflare sees only a DNS record, never"
    echo "                                       your traffic. For many home internet plans"
    echo "                                       (blocked ports, shared IP) this is the only"
    echo "                                       option that works."
    echo "  3) None for now                      Plain HTTP. Add a certificate later by"
    echo "                                       running this script again."
    echo "  4) Advanced                          Test service, your own CA, or your own files."
    case "$(ask 'Choose 1-4' 1)" in
      1) CERT=letsencrypt ;; 2) CERT=cloudflare-dns ;; 3) CERT=none ;; 4) CERT=advanced ;;
      *) die "Please choose 1-4." ;;
    esac
    echo
  else
    CERT=letsencrypt
  fi
fi
[ -n "$CERT" ] || { [ "$MODE" = none ] && CERT=none || CERT=advanced; }

CHALLENGE=http
case "$CERT" in
  letsencrypt)
    case "$MODE" in ""|letsencrypt|letsencrypt-staging) MODE="${MODE:-letsencrypt}" ;; *) die "--cert letsencrypt goes with --mode letsencrypt or letsencrypt-staging." ;; esac ;;
  cloudflare-dns)
    CHALLENGE=cloudflare
    case "$MODE" in ""|letsencrypt|letsencrypt-staging|acme|incommon) MODE="${MODE:-letsencrypt}" ;; *) die "Cloudflare DNS works with --mode letsencrypt, letsencrypt-staging, acme, or incommon." ;; esac ;;
  none)
    [ -z "$MODE" ] || [ "$MODE" = none ] || die "--cert none can't be combined with --mode $MODE."
    MODE=none ;;
  advanced)
    if [ -z "$MODE" ]; then
      echo "Advanced certificate options:"
      echo "  1) letsencrypt-staging  Let's Encrypt's TEST service (untrusted certs; good for trying things)"
      echo "  2) acme                 your own ACME CA (e.g. internal step-ca)"
      if [ "$PROXY" = caddy ]; then
        echo "  3) internal             Caddy's own private CA (LAN only; browsers warn until trusted)"
      else
        echo "  3) internal             (Caddy only — not available with Traefik)"
      fi
      echo "  4) custom               certificate files you provide"
      echo "  5) incommon             InCommon certificates via CERTInext — BETA, untested."
      echo "                          Mostly for universities in InCommon. You'll need the ACME key ID,"
      echo "                          HMAC key and server address from your campus IT now."
      case "$(ask 'Choose 1-5' 1)" in
        1) MODE=letsencrypt-staging ;; 2) MODE=acme ;; 3) MODE=internal ;; 4) MODE=custom ;; 5) MODE=incommon ;;
        *) die "Please choose 1-5." ;;
      esac
    fi ;;
  *) die "--cert must be letsencrypt, cloudflare-dns, none, or advanced" ;;
esac
case "$MODE" in letsencrypt|letsencrypt-staging|acme|incommon|internal|custom|none) ;; *) die "Unknown mode: $MODE" ;; esac
[ "$PROXY" = traefik ] && [ "$MODE" = internal ] && die "internal mode uses Caddy's private CA. Use --proxy caddy, or --mode custom with your own certificate."

if [ "$MODE" = none ]; then
  [ -n "$DOMAIN" ] || DOMAIN="$(ask 'Domain name, if you have one (blank = answer on any name)' '')"
  [ -z "$DOMAIN" ] || valid_domain "$DOMAIN" || die "Invalid domain: $DOMAIN"
else
  [ -n "$DOMAIN" ] || DOMAIN="$(ask 'Domain name people will use (e.g. privacy.yourlibrary.org)')"
  valid_domain "$DOMAIN" || die "Invalid domain: ${DOMAIN:-nothing entered}"
fi
if [ "$PROXY" = traefik ] && [[ "$DOMAIN" == *"*"* ]]; then die "Wildcard domains need --proxy caddy (or list each name)."; fi
PRIMARY="${DOMAIN%%,*}"; PRIMARY="${PRIMARY// /}"

if [ -z "$EMAIL" ] && [ "$MODE" != internal ] && [ "$MODE" != custom ] && [ "$MODE" != none ]; then
  EMAIL="$(ask 'Contact email for the certificate authority (recommended)' '')"
fi
[ -z "$EMAIL" ] || valid_email "$EMAIL" || die "Invalid email: $EMAIL"

ACME_CA_ROOT=""
if [ "$MODE" = acme ]; then
  [ -n "$ACME_CA" ] || ACME_CA="$(ask 'ACME directory URL (e.g. https://ca.internal/acme/acme/directory)')"
  [[ "$ACME_CA" =~ ^https://[A-Za-z0-9.:/_~%-]+$ ]] || die "ACME CA must be an https:// URL"
  if [ -z "$ACME_CA_ROOT_SRC" ]; then
    ACME_CA_ROOT_SRC="$(ask 'Path to the CA root certificate, if the ACME server uses an internal CA (blank = none)' '')"
  fi
  if [ -n "$ACME_CA_ROOT_SRC" ]; then
    [ -f "$ACME_CA_ROOT_SRC" ] || die "File not found: $ACME_CA_ROOT_SRC"
    grep -q "BEGIN CERTIFICATE" "$ACME_CA_ROOT_SRC" || die "Not a PEM certificate: $ACME_CA_ROOT_SRC"
    mkdir -p deploy/certs && cp "$ACME_CA_ROOT_SRC" deploy/certs/acme-ca-root.pem
    ACME_CA_ROOT="/certs/acme-ca-root.pem"
  fi
fi

# ── account credentials (EAB) + key type ──
valid_eab_kid()  { [[ "$1" =~ ^[A-Za-z0-9_.-]{1,128}$ ]]; }
valid_eab_hmac() { [[ "$1" =~ ^[A-Za-z0-9_-]{16,}={0,2}$ ]]; }
if [ "$MODE" = incommon ]; then
  # Required now, unlike the Cloudflare token: without them CERTInext refuses the account and nothing works.
  echo
  echo "InCommon (BETA, untested against a live account): CERTInext issues these to your campus IT,"
  echo "who give each department its own ACME key ID, HMAC key and server address."
  [ -n "$ACME_CA" ] || ACME_CA="$(ask 'ACME server address (directory URL) from campus IT' "$INCOMMON_CA_DEFAULT")"
  [ -n "$EAB_KID" ] || EAB_KID="$(ask 'ACME key ID (EAB key ID)')"
  [ -n "$EAB_HMAC" ] || EAB_HMAC="$(ask_secret 'ACME HMAC key (EAB HMAC key; typing is hidden)')"
  if [ -z "$EAB_KID" ] || [ -z "$EAB_HMAC" ]; then
    die "InCommon needs the ACME key ID and HMAC key from campus IT during setup (--eab-kid / --eab-hmac). Nothing was changed."
  fi
  KEY_TYPE=rsa2048   # CERTInext requires RSA 2048
elif [ "$MODE" = acme ] && [ -z "$EAB_KID$EAB_HMAC" ] && interactive; then
  if [ "$(ask 'Did your CA give you account credentials (an EAB key ID and HMAC key)? (y/n)' n)" = y ]; then
    EAB_KID="$(ask 'EAB key ID')"
    EAB_HMAC="$(ask_secret 'EAB HMAC key (typing is hidden)')"
  fi
fi
if [ -n "$EAB_KID$EAB_HMAC" ]; then
  [ "$MODE" = acme ] || [ "$MODE" = incommon ] || die "--eab-kid/--eab-hmac only apply to --mode acme or incommon."
  if [ -z "$EAB_KID" ] || [ -z "$EAB_HMAC" ]; then
    die "Give both the EAB key ID and the HMAC key."
  fi
  valid_eab_kid "$EAB_KID" || die "That EAB key ID has unexpected characters."
  valid_eab_hmac "$EAB_HMAC" || die "That HMAC key doesn't look right (it's a long base64url string; copy it exactly)."
fi
case "$KEY_TYPE" in ""|rsa2048|rsa4096|p256|p384) ;; *) die "--key-type must be rsa2048, rsa4096, p256 or p384" ;; esac
[ "$MODE" = incommon ] && { [[ "$ACME_CA" =~ ^https://[A-Za-z0-9.:/_~%-]+$ ]] || die "The ACME server address must be an https:// URL"; }

if [ "$MODE" = custom ]; then
  for f in deploy/certs/fullchain.pem deploy/certs/privkey.pem; do
    [ -f "$f" ] || die "Put your certificate files in deploy/certs/ first: fullchain.pem and privkey.pem ($f missing)."
  done
fi

if [ "$CHALLENGE" = cloudflare ] && [ -z "$CF_TOKEN" ] && ! has_env CLOUDFLARE_API_TOKEN; then
  echo "Cloudflare API token: in the Cloudflare dashboard, My Profile > API Tokens >"
  echo "Create Token > 'Edit zone DNS' template, limited to this domain's zone."
  CF_TOKEN="$(ask_secret 'Paste the token (blank = add CLOUDFLARE_API_TOKEN to .env later)')"
fi
[ -z "$CF_TOKEN" ] || valid_cf_token "$CF_TOKEN" || die "That doesn't look like a Cloudflare API token."

# ── step 3: Cloudflare's proxy (DDoS protection) ──
# Only offered where it works: the certificate must not depend on Let's Encrypt reaching this server directly (Cloudflare DNS, or your own e.g. Cloudflare Origin certificate).
CF_PROXY_OK=0
{ [ "$CHALLENGE" = cloudflare ] || [ "$MODE" = custom ]; } && CF_PROXY_OK=1
if [ "$CF_PROXY" = on ] && [ "$CF_PROXY_OK" = 0 ]; then
  die "--cloudflare-proxy needs --cert cloudflare-dns (or --mode custom with a Cloudflare Origin certificate)."
fi
if [ -z "$CF_PROXY" ] && [ "$CF_PROXY_OK" = 1 ] && interactive; then
  echo
  echo "Also put the site behind Cloudflare's proxy for DDoS protection?"
  echo "  Cloudflare absorbs floods of traffic, hides this server's address, and this"
  echo "  server will then refuse every connection that doesn't come through Cloudflare."
  echo "  WARNING: Cloudflare then decrypts and can see ALL traffic to this site: names,"
  echo "  home addresses, phone numbers, emails, and sign-in tokens."
  echo "  Needs ports 80/443 reachable from the internet (from Cloudflare). Most homes"
  echo "  don't need this — it's for sites that are public and big enough to be a target."
  [ "$(ask 'Use Cloudflare proxy? Type yes, or press Enter for no' no)" = yes ] && CF_PROXY=on
fi
[ -n "$CF_PROXY" ] || CF_PROXY=off

# ── rate limits ──
num_ok() { [[ "$1" =~ ^[1-9][0-9]{0,6}$ ]]; }
[ -z "$RL_SITE" ] || num_ok "$RL_SITE" || die "--rate-limit must be a whole number above 0"
[ -z "$RL_AUTH" ] || num_ok "$RL_AUTH" || die "--auth-rate-limit must be a whole number above 0"

# ── preflight ──
if [ "$CHALLENGE" = http ] && { [ "$MODE" = letsencrypt ] || [ "$MODE" = letsencrypt-staging ]; }; then
  ip=""
  if command -v getent >/dev/null; then ip="$(getent hosts "$PRIMARY" | awk '{print $1; exit}' || true)";
  elif command -v host >/dev/null; then ip="$(host "$PRIMARY" 2>/dev/null | awk '/has address/{print $4; exit}' || true)"; fi
  if [ -z "$ip" ]; then
    warn "$PRIMARY does not resolve in DNS yet. Let's Encrypt needs a DNS record pointing to this server."
  else
    echo "DNS: $PRIMARY -> $ip"
  fi
  echo "Let's Encrypt must reach this server on ports 80 and 443 from the internet (router/firewall)."
  echo "If your internet provider blocks those ports or gives you a shared IP, use --cert cloudflare-dns."
  [ "$MODE" = letsencrypt ] && echo "Tip: test with --mode letsencrypt-staging first to avoid rate limits, then switch."
fi

CERT_LABEL="$MODE"; [ "$MODE" = incommon ] && CERT_LABEL="incommon (beta)"; [ "$CHALLENGE" = cloudflare ] && CERT_LABEL="$CERT_LABEL via Cloudflare DNS"
echo
PROTECT_LABEL="rate-limits=$RL"; [ "$CF_PROXY" = on ] && PROTECT_LABEL="$PROTECT_LABEL  cloudflare-proxy=on"
echo "About to set up:  proxy=$PROXY  certificate=$CERT_LABEL  $PROTECT_LABEL  domain=${DOMAIN:-(any)}${EMAIL:+  email=$EMAIL}"
if interactive; then [ "$(ask 'Continue? (y/n)' y)" = y ] || die "Cancelled."; fi

backup
for k in $FRONT_DOOR_KEYS; do unset_env "$k"; done
# Caddy needs its extended build (caddy-extended service) for rate limits or Cloudflare DNS; Traefik has both built in.
if [ "$PROXY" = traefik ]; then set_env COMPOSE_PROFILES https-traefik
elif [ "$CHALLENGE" = cloudflare ] || [ "$RL" = on ]; then set_env COMPOSE_PROFILES https-caddy-extended
else set_env COMPOSE_PROFILES https; fi
set_env RATE_LIMIT "$RL"
[ -z "$RL_SITE" ] || set_env RATE_LIMIT_PER_MINUTE "$RL_SITE"
[ -z "$RL_AUTH" ] || set_env AUTH_RATE_LIMIT_PER_MINUTE "$RL_AUTH"
set_env CLOUDFLARE_PROXY "$CF_PROXY"
set_env FRONT_DOOR "$PROXY"
set_env HTTPS_CHECK_HOST "$PROXY"   # the certificate monitor checks this container
set_env HTTPS_MODE "$MODE"
set_env ACME_CHALLENGE "$CHALLENGE"
[ -z "$DOMAIN" ] || set_env DOMAIN "$DOMAIN"
[ -z "$EMAIL" ] || set_env ACME_EMAIL "$EMAIL"
[ -z "$ACME_CA" ] || set_env ACME_CA "$ACME_CA"
[ -z "$EAB_KID" ] || set_env ACME_EAB_KID "$EAB_KID"
[ -z "$EAB_HMAC" ] || set_env ACME_EAB_HMAC "$EAB_HMAC"
[ -z "$KEY_TYPE" ] || set_env ACME_KEY_TYPE "$KEY_TYPE"
[ -z "$ACME_CA_ROOT" ] || set_env ACME_CA_ROOT "$ACME_CA_ROOT"
[ -z "$CF_TOKEN" ] || set_env CLOUDFLARE_API_TOKEN "$CF_TOKEN"
# The front door owns ports 80/443; the web container stays reachable only on this machine.
set_env WEB_BIND 127.0.0.1
set_env WEB_PORT 8080
if [ "$CF_PROXY" = on ]; then
  set_env TRUSTED_PROXY_HOPS 3   # Cloudflare + front door + nginx in front of the API
else
  set_env TRUSTED_PROXY_HOPS 2   # front door + nginx in front of the API
fi
if [ "$MODE" = none ]; then
  set_env FRONTEND_URL "http://${PRIMARY:-localhost}"
else
  set_env FRONTEND_URL "https://$PRIMARY"
fi

echo
echo "Settings saved to $ENV_FILE."
if [ "$CHALLENGE" = cloudflare ] && ! has_env CLOUDFLARE_API_TOKEN; then
  echo "Not started yet: add your Cloudflare API token first (Zone > DNS > Edit for this domain):"
  echo "    CLOUDFLARE_API_TOKEN=...   in $ENV_FILE"
  echo "Then run:  docker compose up -d --build"
else
  echo "Now run:"
  echo "    docker compose up -d --build"
fi
if [ "$MODE" = none ]; then
  echo "Then open http://${PRIMARY:-<this server>}  (plain HTTP — rerun this script to add a certificate)."
else
  echo "Then open https://$PRIMARY  (first certificate can take a minute; with Cloudflare DNS, up to a few)."
fi
LOG_SVC="$PROXY"
[ "$PROXY" = caddy ] && { [ "$RL" = on ] || [ "$CHALLENGE" = cloudflare ]; } && LOG_SVC=caddy-extended
echo "Watch progress:  docker compose logs -f $LOG_SVC"
if [ "$PROXY" = caddy ] && { [ "$RL" = on ] || [ "$CHALLENGE" = cloudflare ]; }; then
  echo "(The first start builds Caddy with its extra modules; that takes a minute or two.)"
fi
if [ "$CF_PROXY" = on ]; then
  echo
  echo "Cloudflare proxy: finish these in the Cloudflare dashboard (docs/HTTPS.md, \"Behind Cloudflare's proxy\"):"
  echo "  1. DNS: set the record for $PRIMARY to Proxied (orange cloud), pointing at this server's public IP."
  echo "  2. SSL/TLS > Overview: set encryption mode to Full (strict)."
  echo "  3. Forward ports 80 and 443 to this server. Only Cloudflare will be let in."
  echo "Remember: Cloudflare can now see all traffic to this site."
fi
[ "$MODE" = internal ] && echo "Browsers will warn until Caddy's root CA is trusted — see docs/HTTPS.md."
if [ "$MODE" = incommon ]; then
  echo "InCommon is BETA and untested against a live CERTInext account. If the certificate doesn't arrive, check"
  echo "the logs above and confirm the key ID, HMAC key, server address and domain with campus IT (docs/HTTPS.md)."
fi
[ "$MODE" = letsencrypt-staging ] && echo "Staging certificates are intentionally untrusted. Rerun with --mode letsencrypt when it works."
[ "$MODE" = none ] || echo "If you use Google/Microsoft sign-in or SAML, update their redirect URLs to https://$PRIMARY (docs/SSO.md)."
exit 0
