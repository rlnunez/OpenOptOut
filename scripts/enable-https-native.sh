#!/usr/bin/env bash
# ==============================================================================
# Turn on HTTPS for a NATIVE (no Docker) PrivacyShield install, using certbot's
# nginx plugin. This is the native-Linux equivalent of scripts/enable-https.sh
# (which is for the Docker/Caddy path) — same idea, different mechanism: here,
# certbot edits your nginx site directly and sets up its own renewal timer,
# rather than a Caddy container handling it.
#
# Prerequisites (see docs/NATIVE_INSTALL.md):
#   - PrivacyShield is already installed and running natively (systemd unit +
#     nginx site from deploy/native/), reachable on plain HTTP.
#   - certbot and python3-certbot-nginx are installed
#       Debian/Ubuntu:  sudo apt-get install certbot python3-certbot-nginx
#   - A DNS A/AAAA record for your domain points at this server, and ports 80
#     and 443 are reachable from the internet.
#
#   sudo ./scripts/enable-https-native.sh --domain privacy.lib.org --email it@lib.org
#   sudo ./scripts/enable-https-native.sh --domain privacy.lib.org --email it@lib.org --staging   # test first
#   sudo ./scripts/enable-https-native.sh --disable                                                # revert to plain HTTP
#
# Options: --domain D  --email E  --nginx-site PATH (default: auto-detected
#          under /etc/nginx/sites-available, else /etc/nginx/conf.d)
#          --env-file PATH (default /opt/privacyshield/.env)
#          --staging (Let's Encrypt's test environment — untrusted certs, no
#            rate limits; run this first, then re-run without --staging)
#          --yes (no confirmation prompt)  --disable
#
# What this does NOT do: install certbot, install/configure nginx or the
# PrivacyShield service themselves, or restart the privacyshield-api service
# (HTTPS termination happens entirely at nginx; the API doesn't need to know
# or change). It also does not run docker anything — this script is Docker-free
# on purpose, for hosts that plain can't run it. See docs/HTTPS.md for the
# Docker-based path if that's actually available to you.
# ==============================================================================
set -euo pipefail

DOMAIN=""; EMAIL=""; NGINX_SITE=""; ENV_FILE="/opt/privacyshield/.env"
STAGING=0; YES=0; DISABLE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --nginx-site) NGINX_SITE="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --staging) STAGING=1; shift ;;
    --yes|-y) YES=1; shift ;;
    --disable) DISABLE=1; shift ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

die()  { echo "Error: $*" >&2; exit 1; }
warn() { echo "Warning: $*" >&2; }
ask()  {
  local prompt="$1" def="${2:-}" ans=""
  if [ "$YES" = 1 ] || [ ! -t 0 ]; then echo "$def"; return 0; fi
  read -r -p "$prompt${def:+ [$def]}: " ans || true
  echo "${ans:-$def}"
}
valid_domain() { [[ "$1" =~ ^[A-Za-z0-9.-]+$ ]]; }   # a single hostname here — certbot's --domain takes one at a time
valid_email()  { [[ "$1" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; }

[ "$(id -u)" = 0 ] || die "Run this as root (sudo) — it edits your nginx config and calls certbot."

if [ "$DISABLE" = 0 ]; then
  command -v certbot >/dev/null 2>&1 || die \
    "certbot not found. Install it first, e.g.:  sudo apt-get install certbot python3-certbot-nginx"
  certbot plugins 2>/dev/null | grep -q nginx || die \
    "certbot's nginx plugin isn't installed. On Debian/Ubuntu:  sudo apt-get install python3-certbot-nginx"
fi

set_env() {
  local key="$1" val="$2" tmp; tmp="$(mktemp)"
  if [ -f "$ENV_FILE" ] && grep -q "^${key}=" "$ENV_FILE"; then
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k {print k"="v; next} {print}' "$ENV_FILE" > "$tmp"
  else
    { [ -f "$ENV_FILE" ] && cat "$ENV_FILE"; echo "${key}=${val}"; } > "$tmp"
  fi
  mv "$tmp" "$ENV_FILE"
}
backup_env() { [ -f "$ENV_FILE" ] && cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)" && echo "Backed up $ENV_FILE"; return 0; }

# ── --disable ──
if [ "$DISABLE" = 1 ]; then
  echo "Reverting nginx's PrivacyShield site to certbot's saved pre-HTTPS backup, if one exists."
  found=""
  for f in /etc/nginx/sites-available/privacyshield /etc/nginx/conf.d/privacyshield.conf; do
    [ -f "${f}.certbot.bak" ] && { cp "${f}.certbot.bak" "$f"; found="$f"; }
  done
  [ -n "$found" ] || warn "No certbot backup of the nginx site was found — nothing to revert automatically. Edit the nginx site by hand to remove the TLS block, then 'nginx -t && systemctl reload nginx'."
  command -v nginx >/dev/null && nginx -t && systemctl reload nginx
  backup_env
  set_env FRONTEND_URL "http://localhost"
  echo "certbot's own certificate files and renewal timer are left in place (harmless if unused)."
  echo "To remove them too:  sudo certbot delete --cert-name <your-domain>"
  exit 0
fi

# ── locate the nginx site ──
if [ -z "$NGINX_SITE" ]; then
  for f in /etc/nginx/sites-available/privacyshield /etc/nginx/conf.d/privacyshield.conf; do
    [ -f "$f" ] && NGINX_SITE="$f" && break
  done
fi
[ -n "$NGINX_SITE" ] && [ -f "$NGINX_SITE" ] || die \
  "Couldn't find the PrivacyShield nginx site. Install it first (deploy/native/nginx-privacyshield.conf.example), or pass --nginx-site PATH."

# ── domain / email ──
[ -n "$DOMAIN" ] || DOMAIN="$(ask 'Domain name people will use (e.g. privacy.yourlibrary.org)')"
valid_domain "$DOMAIN" || die "Invalid domain: $DOMAIN"
[ -z "$EMAIL" ] && EMAIL="$(ask 'Contact email for Let'"'"'s Encrypt (recommended)' '')"
[ -z "$EMAIL" ] || valid_email "$EMAIL" || die "Invalid email: $EMAIL"

# ── preflight ──
ip=""
if command -v getent >/dev/null; then ip="$(getent hosts "$DOMAIN" | awk '{print $1; exit}')";
elif command -v host >/dev/null; then ip="$(host "$DOMAIN" 2>/dev/null | awk '/has address/{print $4; exit}')"; fi
if [ -z "$ip" ]; then
  warn "$DOMAIN does not resolve in DNS yet. Let's Encrypt needs a DNS record pointing to this server."
else
  echo "DNS: $DOMAIN -> $ip"
fi
echo "Let's Encrypt must reach this server on ports 80 and 443 from the internet (firewall/router)."
[ "$STAGING" = 0 ] && echo "Tip: run with --staging first to avoid rate limits while testing, then re-run without it."

echo
echo "About to run certbot for: domain=$DOMAIN${EMAIL:+ email=$EMAIL}${STAGING:+ (staging)}"
if [ "$YES" = 0 ]; then [ "$(ask 'Continue? (y/n)' y)" = y ] || die "Cancelled."; fi

# certbot's --nginx plugin edits the site file in place (it makes its own
# backup with a similar naming convention; we also keep an explicit one below
# for --disable to use reliably across certbot versions).
cp "$NGINX_SITE" "${NGINX_SITE}.certbot.bak"

CERTBOT_ARGS=(--nginx -d "$DOMAIN" --redirect --agree-tos --no-eff-email -n)
[ -n "$EMAIL" ] && CERTBOT_ARGS+=(--email "$EMAIL") || CERTBOT_ARGS+=(--register-unsafely-without-email)
[ "$STAGING" = 1 ] && CERTBOT_ARGS+=(--staging)

certbot "${CERTBOT_ARGS[@]}"

nginx -t
systemctl reload nginx

backup_env
set_env FRONTEND_URL "https://$DOMAIN"
set_env HTTPS_MODE "$([ "$STAGING" = 1 ] && echo letsencrypt-staging || echo letsencrypt)"
set_env DOMAIN "$DOMAIN"
set_env HTTPS_CHECK_HOST "127.0.0.1"

echo
echo "HTTPS is on. certbot installed its own systemd timer for automatic renewal"
echo "(check with:  systemctl list-timers | grep certbot)."
echo "Restart the API service so it picks up the new .env values:  sudo systemctl restart privacyshield-api"
[ "$STAGING" = 1 ] && echo "This used Let's Encrypt's STAGING service — the certificate is intentionally untrusted. Re-run without --staging once you've confirmed everything works."
echo "If you use Google/Microsoft sign-in or SAML, update their redirect URLs to https://$DOMAIN (docs/SSO.md)."
exit 0
