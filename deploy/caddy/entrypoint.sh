#!/bin/sh
# ==============================================================================
# OpenOptOut HTTPS front door — generates the Caddy config from environment
# variables, then runs Caddy. Caddy obtains certificates, renews them
# automatically, and redirects HTTP to HTTPS.
#
#   HTTPS_MODE   letsencrypt          Let's Encrypt (public server; ports 80+443
#                                     reachable from the internet, DNS pointing here)
#                letsencrypt-staging  Let's Encrypt's test environment (untrusted
#                                     certs; use while testing to avoid rate limits)
#                acme                 Any ACME CA, e.g. an internal step-ca
#                                     (ACME_CA = directory URL, ACME_CA_ROOT optional)
#                internal             Caddy's own private CA (LAN-only; browsers
#                                     warn unless its root is installed)
#                custom               Your own certificate files (TLS_CERT_FILE /
#                                     TLS_KEY_FILE, mounted from ./deploy/certs)
#   DOMAIN       e.g. privacy.example.org (comma-separate several)
#   ACME_EMAIL   contact address for the CA (recommended)
#   UPSTREAM     where to send traffic (default web:80)
#   HSTS         on (default for trusted certs) | off
#
# Every value is validated before it's written: an unchecked value containing a
# newline or brace could inject arbitrary Caddy configuration.
# ==============================================================================
set -eu

CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
MODE="${HTTPS_MODE:-}"
DOMAIN="${DOMAIN:-}"
EMAIL="${ACME_EMAIL:-}"
UPSTREAM="${UPSTREAM:-web:80}"

die() { echo "OpenOptOut HTTPS: $*" >&2; exit 1; }
# Allowed character sets (no whitespace except the ", " list separator, no braces,
# quotes, or line breaks). grep matches line by line, so a value with a valid FIRST
# line and a malicious second line would pass — reject line breaks/tabs outright.
NL='
'
CR=$(printf '\r'); TAB=$(printf '\t')
matches() {
  case "$1" in *"$NL"*|*"$CR"*|*"$TAB"*) return 1 ;; esac
  printf '%s' "$1" | grep -Eq "$2"
}

[ -n "$DOMAIN" ] || die "DOMAIN is not set (e.g. DOMAIN=privacy.example.org in .env)."
matches "$DOMAIN" '^[A-Za-z0-9*.-]+(, *[A-Za-z0-9*.-]+)*$' || die "DOMAIN has invalid characters: $DOMAIN"
if [ -n "$EMAIL" ]; then
  matches "$EMAIL" '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$' || die "ACME_EMAIL is not a valid email: $EMAIL"
fi
matches "$UPSTREAM" '^[A-Za-z0-9.-]+:[0-9]+$' || die "UPSTREAM must look like host:port: $UPSTREAM"
url_ok() { matches "$1" '^https://[A-Za-z0-9.:/_~%-]+$'; }
path_ok() { matches "$1" '^/[A-Za-z0-9._/-]+$'; }

case "$MODE" in
  letsencrypt)         CA="https://acme-v02.api.letsencrypt.org/directory" ;;
  letsencrypt-staging) CA="https://acme-staging-v02.api.letsencrypt.org/directory" ;;
  acme)
    CA="${ACME_CA:-}"
    [ -n "$CA" ] || die "HTTPS_MODE=acme needs ACME_CA (the ACME directory URL)."
    url_ok "$CA" || die "ACME_CA must be an https:// URL: $CA" ;;
  internal|custom) CA="" ;;
  "") die "HTTPS_MODE is not set (letsencrypt, letsencrypt-staging, acme, internal, custom)." ;;
  *)  die "Unknown HTTPS_MODE '$MODE' (letsencrypt, letsencrypt-staging, acme, internal, custom)." ;;
esac

# ── tls directive ─────────────────────────────────────────────────────────────
if [ -n "$CA" ]; then
  TLS="	tls ${EMAIL} {
		ca $CA"
  if [ -n "${ACME_CA_ROOT:-}" ]; then
    path_ok "$ACME_CA_ROOT" || die "ACME_CA_ROOT must be an absolute path: $ACME_CA_ROOT"
    [ -f "$ACME_CA_ROOT" ] || die "ACME_CA_ROOT file not found: $ACME_CA_ROOT"
    TLS="$TLS
		ca_root $ACME_CA_ROOT"
  fi
  TLS="$TLS
	}"
elif [ "$MODE" = "internal" ]; then
  TLS="	tls internal"
else
  CERT="${TLS_CERT_FILE:-/certs/fullchain.pem}"
  KEY="${TLS_KEY_FILE:-/certs/privkey.pem}"
  if ! path_ok "$CERT" || ! path_ok "$KEY"; then
    die "TLS_CERT_FILE / TLS_KEY_FILE must be absolute paths."
  fi
  [ -f "$CERT" ] || die "Certificate file not found: $CERT (put it in ./deploy/certs)"
  [ -f "$KEY" ]  || die "Key file not found: $KEY (put it in ./deploy/certs)"
  TLS="	tls $CERT $KEY"
fi

# HSTS tells browsers to always use HTTPS. Off by default for 'internal' (a
# private CA the browser may not trust yet) and whenever HSTS=off.
HSTS_LINE=""
if [ "${HSTS:-on}" != "off" ] && [ "$MODE" != "internal" ]; then
  HSTS_LINE='		Strict-Transport-Security "max-age=31536000"'
fi

# ── global options ────────────────────────────────────────────────────────────
GLOBAL="	admin off"
[ -n "$EMAIL" ] && GLOBAL="$GLOBAL
	email $EMAIL"
if [ -n "${HTTP_PORT:-}" ]; then
  matches "$HTTP_PORT" '^[0-9]+$' || die "HTTP_PORT must be a number"
  GLOBAL="$GLOBAL
	http_port $HTTP_PORT"
fi
if [ -n "${HTTPS_PORT:-}" ]; then
  matches "$HTTPS_PORT" '^[0-9]+$' || die "HTTPS_PORT must be a number"
  GLOBAL="$GLOBAL
	https_port $HTTPS_PORT"
fi
if [ -n "${RENEW_INTERVAL:-}" ]; then     # testing only; Caddy's default is fine
  matches "$RENEW_INTERVAL" '^[0-9]+[smh]$' || die "RENEW_INTERVAL must look like 10m"
  GLOBAL="$GLOBAL
	renew_interval $RENEW_INTERVAL"
fi

mkdir -p "$(dirname "$CADDYFILE")"
cat > "$CADDYFILE" <<EOF
# Generated by deploy/caddy/entrypoint.sh at container start — edit .env, not this file.
{
$GLOBAL
}

$DOMAIN {
$TLS
	encode zstd gzip
	header {
$HSTS_LINE
		X-Content-Type-Options "nosniff"
		Referrer-Policy "strict-origin-when-cross-origin"
		X-Frame-Options "DENY"
		-Server
	}
	reverse_proxy $UPSTREAM
}
EOF

echo "OpenOptOut HTTPS: mode=$MODE domain=$DOMAIN upstream=$UPSTREAM"
if [ "${GENERATE_ONLY:-}" = "1" ]; then
  cat "$CADDYFILE"
  exit 0
fi
exec caddy run --config "$CADDYFILE" --adapter caddyfile
