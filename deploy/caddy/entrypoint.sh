#!/bin/sh
# ==============================================================================
# OpenOptOut HTTPS front door — generates Caddy config from environment variables and runs Caddy.
#
#   HTTPS_MODE   letsencrypt          Let's Encrypt (ports 80+443 reachable)
#                letsencrypt-staging  Let's Encrypt staging environment
#                acme                 Custom ACME CA (ACME_CA directory URL)
#                incommon             InCommon via CERTInext (requires EAB keys)
#                internal             Caddy private CA (LAN-only testing)
#                custom               Local cert files (mounted in ./deploy/certs)
#                none                 Plain HTTP on port 80 only
#   ACME_CHALLENGE  http (default)    HTTP-01 challenge over port 80
#                   cloudflare        DNS-01 via Cloudflare API (needs token)
#   RATE_LIMIT   on | off             Per-visitor request limits
#   RATE_LIMIT_PER_MINUTE             Whole site limit per visitor (default 1200)
#   AUTH_RATE_LIMIT_PER_MINUTE        Sign-in limit per visitor (default 60)
#   CLOUDFLARE_PROXY  on | off        Restrict access to Cloudflare IPs
#   DOMAIN                            Domain name(s) (comma-separated)
#   ACME_EMAIL                        Registration email for the ACME CA
#   ACME_KEY_TYPE                     Certificate key type (e.g. rsa2048, p256)
#   UPSTREAM                          Backend address (default web:80)
#   HSTS         on | off             Strict-Transport-Security header
# ==============================================================================
set -eu

CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
MODE="${HTTPS_MODE:-}"
DOMAIN="${DOMAIN:-}"
EMAIL="${ACME_EMAIL:-}"
UPSTREAM="${UPSTREAM:-web:80}"

die() { echo "OpenOptOut HTTPS: $*" >&2; exit 1; }
# Allowed character sets (no whitespace except the ", " list separator, no braces, quotes, or line breaks). grep matches line by line, so a value with a valid FIRST line and a malicious second line would pass — reject line breaks/tabs outright.
NL='
'
CR=$(printf '\r'); TAB=$(printf '\t')
matches() {
  case "$1" in *"$NL"*|*"$CR"*|*"$TAB"*) return 1 ;; esac
  printf '%s' "$1" | grep -Eq "$2"
}

if [ -z "$DOMAIN" ] && [ "$MODE" != "none" ]; then
  die "DOMAIN is not set (e.g. DOMAIN=privacy.example.org in .env)."
fi
[ -z "$DOMAIN" ] || matches "$DOMAIN" '^[A-Za-z0-9*.-]+(, *[A-Za-z0-9*.-]+)*$' || die "DOMAIN has invalid characters: $DOMAIN"
if [ -n "$EMAIL" ]; then
  matches "$EMAIL" '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$' || die "ACME_EMAIL is not a valid email: $EMAIL"
fi
matches "$UPSTREAM" '^[A-Za-z0-9.-]+:[0-9]+$' || die "UPSTREAM must look like host:port: $UPSTREAM"
url_ok() { matches "$1" '^https://[A-Za-z0-9.:/_~%-]+$'; }
path_ok() { matches "$1" '^/[A-Za-z0-9._/ -]+$'; }
num_ok() { matches "$1" '^[1-9][0-9]{0,6}$'; }

case "$MODE" in
  letsencrypt)         CA="https://acme-v02.api.letsencrypt.org/directory" ;;
  letsencrypt-staging) CA="https://acme-staging-v02.api.letsencrypt.org/directory" ;;
  acme)
    CA="${ACME_CA:-}"
    [ -n "$CA" ] || die "HTTPS_MODE=acme needs ACME_CA (the ACME directory URL)."
    url_ok "$CA" || die "ACME_CA must be an https:// URL: $CA" ;;
  incommon)
    CA="${ACME_CA:-https://acme-us.certinext.io/v1/directory}"
    url_ok "$CA" || die "ACME_CA must be an https:// URL: $CA"
    if [ -z "${ACME_EAB_KID:-}" ] || [ -z "${ACME_EAB_HMAC:-}" ]; then
      die "HTTPS_MODE=incommon needs ACME_EAB_KID and ACME_EAB_HMAC: the ACME key ID and HMAC key your campus IT issues for the InCommon certificate service."
    fi ;;
  internal|custom|none) CA="" ;;
  "") die "HTTPS_MODE is not set (letsencrypt, letsencrypt-staging, acme, incommon, internal, custom, none)." ;;
  *)  die "Unknown HTTPS_MODE '$MODE' (letsencrypt, letsencrypt-staging, acme, incommon, internal, custom, none)." ;;
esac

# Account credentials some CAs issue (External Account Binding): both or neither.
EAB_KID="${ACME_EAB_KID:-}"; EAB_HMAC="${ACME_EAB_HMAC:-}"
if [ -n "$EAB_KID$EAB_HMAC" ]; then
  [ "$MODE" = "acme" ] || [ "$MODE" = "incommon" ] || die "ACME_EAB_KID / ACME_EAB_HMAC only apply to HTTPS_MODE acme or incommon."
  if [ -z "$EAB_KID" ] || [ -z "$EAB_HMAC" ]; then
    die "Set both ACME_EAB_KID and ACME_EAB_HMAC (or neither)."
  fi
  matches "$EAB_KID" '^[A-Za-z0-9_.-]{1,128}$' || die "ACME_EAB_KID has unexpected characters."
  matches "$EAB_HMAC" '^[A-Za-z0-9_-]{16,}={0,2}$' || die "ACME_EAB_HMAC doesn't look like a base64url key (copy it exactly as issued)."
fi
KEY_TYPE="${ACME_KEY_TYPE:-}"
[ "$MODE" = "incommon" ] && KEY_TYPE=rsa2048   # CERTInext requires RSA 2048
case "$KEY_TYPE" in ""|rsa2048|rsa4096|p256|p384) ;; *) die "ACME_KEY_TYPE must be rsa2048, rsa4096, p256 or p384: $KEY_TYPE" ;; esac

CHALLENGE="${ACME_CHALLENGE:-http}"
case "$CHALLENGE" in
  http) ;;
  cloudflare)
    [ -n "$CA" ] || die "ACME_CHALLENGE=cloudflare only works with HTTPS_MODE letsencrypt, letsencrypt-staging, acme, or incommon."
    [ -n "${CLOUDFLARE_API_TOKEN:-}" ] || die "Cloudflare DNS is selected but CLOUDFLARE_API_TOKEN isn't set yet. Create a Cloudflare API token with Zone > DNS > Edit for your domain, add CLOUDFLARE_API_TOKEN=... to .env, then run: docker compose up -d"
    if [ "${GENERATE_ONLY:-}" != "1" ] && ! caddy list-modules 2>/dev/null | grep -q '^dns.providers.cloudflare$'; then
      die "This Caddy build has no Cloudflare DNS support. Rerun scripts/enable-https.sh, which switches to the caddy-extended service that includes it."
    fi ;;
  *) die "ACME_CHALLENGE must be http or cloudflare: $CHALLENGE" ;;
esac

# ── protection: rate limits + Cloudflare-only ─────────────────────────────────
has_ratelimit() {
  [ "${GENERATE_ONLY:-}" = "1" ] || caddy list-modules 2>/dev/null | grep -q '^http.handlers.rate_limit$'
}
case "${RATE_LIMIT:-}" in
  on)  has_ratelimit || die "RATE_LIMIT=on but this Caddy build has no rate limiting. Rerun scripts/enable-https.sh, which switches to the caddy-extended service that includes it." ;;
  off) ;;
  "")  if has_ratelimit; then RATE_LIMIT=on; else
         RATE_LIMIT=off
         echo "OpenOptOut HTTPS: rate limiting is OFF (this Caddy build doesn't include it). Rerun scripts/enable-https.sh to turn it on." >&2
       fi ;;
  *)   die "RATE_LIMIT must be on or off: $RATE_LIMIT" ;;
esac
RL_SITE="${RATE_LIMIT_PER_MINUTE:-1200}"
RL_AUTH="${AUTH_RATE_LIMIT_PER_MINUTE:-60}"
num_ok "$RL_SITE" || die "RATE_LIMIT_PER_MINUTE must be a whole number above 0: $RL_SITE"
num_ok "$RL_AUTH" || die "AUTH_RATE_LIMIT_PER_MINUTE must be a whole number above 0: $RL_AUTH"

CF_RANGES=""
case "${CLOUDFLARE_PROXY:-off}" in
  off) ;;
  on)
    [ "$MODE" != "none" ] || die "CLOUDFLARE_PROXY=on needs a certificate: Cloudflare would otherwise reach this server over plain HTTP across the internet."
    if [ "$CHALLENGE" != "cloudflare" ] && [ "$MODE" != "custom" ]; then
      die "CLOUDFLARE_PROXY=on needs ACME_CHALLENGE=cloudflare (or HTTPS_MODE=custom with a Cloudflare Origin certificate): behind Cloudflare's proxy, Let's Encrypt can't reliably check this server over port 80."
    fi
    CF_FILE="${CLOUDFLARE_IPS_FILE:-/deploy/cloudflare-ips.txt}"
    path_ok "$CF_FILE" || die "CLOUDFLARE_IPS_FILE must be an absolute path"
    [ -f "$CF_FILE" ] || die "Cloudflare IP list not found: $CF_FILE"
    while IFS= read -r r || [ -n "$r" ]; do
      r=$(printf '%s' "$r" | tr -d ' \t\r')
      case "$r" in ""|"#"*) continue ;; esac
      matches "$r" '^[0-9A-Fa-f:.]+/[0-9]{1,3}$' || die "Bad entry in $CF_FILE: $r"
      CF_RANGES="${CF_RANGES:+$CF_RANGES }$r"
    done < "$CF_FILE"
    [ -n "$CF_RANGES" ] || die "$CF_FILE has no IP ranges" ;;
  *) die "CLOUDFLARE_PROXY must be on or off: $CLOUDFLARE_PROXY" ;;
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
  if [ -n "$EAB_KID" ]; then
    # Read from the environment when Caddy loads the config ({$VAR}); the secret itself is never written to this file.
    TLS="$TLS
		eab {\$ACME_EAB_KID} {\$ACME_EAB_HMAC}"
  fi
  if [ -n "$KEY_TYPE" ]; then
    TLS="$TLS
		key_type $KEY_TYPE"
  fi
  if [ "$CHALLENGE" = "cloudflare" ]; then
    # The token stays in the environment; only a placeholder is written to disk. Public resolvers, so a home router's own DNS can't hide the new record.
    TLS="$TLS
		dns cloudflare {env.CLOUDFLARE_API_TOKEN}
		resolvers 1.1.1.1 1.0.0.1"
  fi
  TLS="$TLS
	}"
elif [ "$MODE" = "internal" ]; then
  TLS="	tls internal"
elif [ "$MODE" = "none" ]; then
  TLS=""
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

# HSTS tells browsers to always use HTTPS. Off by default for 'internal' (a private CA the browser may not trust yet) and whenever HSTS=off.
HSTS_LINE=""
if [ "${HSTS:-on}" != "off" ] && [ "$MODE" != "internal" ] && [ "$MODE" != "none" ]; then
  HSTS_LINE='		Strict-Transport-Security "max-age=31536000"'
fi

# ── global options ────────────────────────────────────────────────────────────
# persist_config off: Caddy would otherwise save the loaded config, including any {$VAR} secrets it read (ACME_EAB_HMAC), to autosave.json on the caddy_config volume.
GLOBAL="	admin off
	persist_config off"
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
# Slow-header ("slowloris") protection, and — behind Cloudflare — where the visitor's real IP comes from. Only Cloudflare's own addresses are trusted to set CF-Connecting-IP; anyone else can't reach the site at all (below).
SERVERS="		timeouts {
			read_header 10s
		}"
if [ -n "$CF_RANGES" ]; then
  SERVERS="$SERVERS
		trusted_proxies static $CF_RANGES
		client_ip_headers CF-Connecting-IP"
fi
GLOBAL="$GLOBAL
	servers {
$SERVERS
	}"

# Request handling, in this exact order (a route block keeps it literal): drop non-Cloudflare connections, apply rate limits, then proxy.
ROUTE=""
MATCHERS=""
if [ -n "$CF_RANGES" ]; then
  MATCHERS="	@not_cloudflare not remote_ip $CF_RANGES"
  ROUTE="		abort @not_cloudflare"
fi
if [ "$RATE_LIMIT" = "on" ]; then
  ROUTE="${ROUTE:+$ROUTE
}		rate_limit {
			zone site {
				key {client_ip}
				window 1m
				events $RL_SITE
			}
			zone signin {
				match {
					path /api/auth/*
				}
				key {client_ip}
				window 1m
				events $RL_AUTH
			}
		}"
fi
ROUTE="${ROUTE:+$ROUTE
}		reverse_proxy $UPSTREAM"

# Site address: the domain(s) for HTTPS. With no certificate ('none'), plain HTTP only — http:// tells Caddy not to fetch a certificate or redirect.
SITE="$DOMAIN"
if [ "$MODE" = "none" ]; then
  if [ -n "$DOMAIN" ]; then
    SITE=$(printf '%s' "$DOMAIN" | sed 's/ //g; s/^/http:\/\//; s/,/, http:\/\//g')
  else
    SITE=":${HTTP_PORT:-80}"
  fi
fi

mkdir -p "$(dirname "$CADDYFILE")"
cat > "$CADDYFILE" <<EOF
# Generated by deploy/caddy/entrypoint.sh at container start — edit .env, not this file.
{
$GLOBAL
}

$SITE {
$TLS
	encode zstd gzip
	header {
$HSTS_LINE
		X-Content-Type-Options "nosniff"
		Referrer-Policy "strict-origin-when-cross-origin"
		X-Frame-Options "DENY"
		-Server
	}
$MATCHERS
	route {
$ROUTE
	}
}
EOF

echo "OpenOptOut HTTPS: mode=$MODE challenge=$CHALLENGE rate_limit=$RATE_LIMIT cloudflare_proxy=${CLOUDFLARE_PROXY:-off} domain=${DOMAIN:-(any)} upstream=$UPSTREAM"
if [ "${GENERATE_ONLY:-}" = "1" ]; then
  cat "$CADDYFILE"
  exit 0
fi
exec caddy run --config "$CADDYFILE" --adapter caddyfile
