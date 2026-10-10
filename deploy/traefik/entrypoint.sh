#!/bin/sh
# ==============================================================================
# OpenOptOut HTTPS front door (Traefik option) — generates Traefik's static and dynamic config from environment variables, then runs Traefik. Traefik obtains certificates, renews them automatically, and redirects HTTP to HTTPS.
#
# This is the alternative to deploy/caddy/entrypoint.sh, for admins who already know and prefer Traefik. Both read the same .env keys; pick one with FRONT_DOOR=caddy|traefik (scripts/enable-https.* --proxy sets it).
#
#   HTTPS_MODE   letsencrypt          Let's Encrypt (public server; ports 80+443 reachable from the internet, DNS pointing here)
#                letsencrypt-staging  Let's Encrypt's test environment (untrusted certs; use while testing to avoid rate limits)
#                acme                 Any ACME CA, e.g. an internal step-ca (ACME_CA = directory URL, ACME_CA_ROOT optional)
#                custom               Your own certificate files (TLS_CERT_FILE / TLS_KEY_FILE, mounted from ./deploy/certs)
#                none                 No certificate: plain HTTP on port 80 only (DOMAIN optional). Add one later.
#                (internal is Caddy-only: Traefik has no private CA of its own.)
#   ACME_CHALLENGE  http (default)    The CA checks this server over port 80
#                   cloudflare        The CA checks a DNS record instead, created through the Cloudflare API (built into Traefik): no open ports needed. Needs CLOUDFLARE_API_TOKEN. letsencrypt/-staging/acme.
#   RATE_LIMIT   on (default) | off   Per-visitor request limits, built into Traefik.
#   RATE_LIMIT_PER_MINUTE       per visitor, whole site (default 1200)
#   AUTH_RATE_LIMIT_PER_MINUTE  per visitor, /api/auth/* sign-in endpoints (default 60)
#   CLOUDFLARE_PROXY  on | off (default)  The site sits behind Cloudflare's proxy (orange cloud): accept connections ONLY from Cloudflare's IP ranges (CLOUDFLARE_IPS_FILE) and take the visitor's IP from CF-Connecting-IP. Needs ACME_CHALLENGE=cloudflare or HTTPS_MODE=custom.
#   DOMAIN       e.g. privacy.example.org (comma-separate several; no wildcards — HTTP-01 challenges can't issue them)
#   ACME_EMAIL   contact address for the CA (recommended)
#   UPSTREAM     where to send traffic (default web:80)
#   HSTS         on (default) | off
#
# No Docker socket is mounted and the Docker provider is never enabled: routing comes only from the file written here, so nothing that reaches Traefik can discover or steer other containers on the host.
#
# Every value is validated before it's written: an unchecked value containing a newline, quote, or backtick could inject arbitrary Traefik configuration.
# ==============================================================================
set -eu

CONF_DIR="${TRAEFIK_CONF_DIR:-/etc/traefik}"
ACME_STORAGE="${ACME_STORAGE:-/data/acme.json}"
MODE="${HTTPS_MODE:-}"
DOMAIN="${DOMAIN:-}"
EMAIL="${ACME_EMAIL:-}"
UPSTREAM="${UPSTREAM:-web:80}"

die() { echo "OpenOptOut HTTPS (Traefik): $*" >&2; exit 1; }
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
case "$DOMAIN" in *'*'*) die "Wildcard domains aren't supported with Traefik (Let's Encrypt can't issue them over HTTP). List each name, or use FRONT_DOOR=caddy." ;; esac
[ -z "$DOMAIN" ] || matches "$DOMAIN" '^[A-Za-z0-9.-]+(, *[A-Za-z0-9.-]+)*$' || die "DOMAIN has invalid characters: $DOMAIN"
if [ -n "$EMAIL" ]; then
  matches "$EMAIL" '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$' || die "ACME_EMAIL is not a valid email: $EMAIL"
fi
matches "$UPSTREAM" '^[A-Za-z0-9.-]+:[0-9]+$' || die "UPSTREAM must look like host:port: $UPSTREAM"
url_ok() { matches "$1" '^https://[A-Za-z0-9.:/_~%-]+$'; }
path_ok() { matches "$1" '^/[A-Za-z0-9._/-]+$'; }
num_ok() { matches "$1" '^[0-9]+$'; }
path_ok "$CONF_DIR" || die "TRAEFIK_CONF_DIR must be an absolute path"
path_ok "$ACME_STORAGE" || die "ACME_STORAGE must be an absolute path"

case "$MODE" in
  letsencrypt)         CA="https://acme-v02.api.letsencrypt.org/directory" ;;
  letsencrypt-staging) CA="https://acme-staging-v02.api.letsencrypt.org/directory" ;;
  acme)
    CA="${ACME_CA:-}"
    [ -n "$CA" ] || die "HTTPS_MODE=acme needs ACME_CA (the ACME directory URL)."
    url_ok "$CA" || die "ACME_CA must be an https:// URL: $CA" ;;
  custom|none) CA="" ;;
  internal) die "HTTPS_MODE=internal needs Caddy's private CA. Use FRONT_DOOR=caddy, or HTTPS_MODE=custom with your own certificate." ;;
  "") die "HTTPS_MODE is not set (letsencrypt, letsencrypt-staging, acme, custom, none)." ;;
  *)  die "Unknown HTTPS_MODE '$MODE' (letsencrypt, letsencrypt-staging, acme, custom, none)." ;;
esac

CHALLENGE="${ACME_CHALLENGE:-http}"
case "$CHALLENGE" in
  http) ;;
  cloudflare)
    [ -n "$CA" ] || die "ACME_CHALLENGE=cloudflare only works with HTTPS_MODE letsencrypt, letsencrypt-staging, or acme."
    [ -n "${CLOUDFLARE_API_TOKEN:-}" ] || die "Cloudflare DNS is selected but CLOUDFLARE_API_TOKEN isn't set yet. Create a Cloudflare API token with Zone > DNS > Edit for your domain, add CLOUDFLARE_API_TOKEN=... to .env, then run: docker compose up -d" ;;
  *) die "ACME_CHALLENGE must be http or cloudflare: $CHALLENGE" ;;
esac

# ── protection: rate limits + Cloudflare-only ─────────────────────────────────
case "${RATE_LIMIT:-on}" in on|"") RATE_LIMIT=on ;; off) ;; *) die "RATE_LIMIT must be on or off: $RATE_LIMIT" ;; esac
RL_SITE="${RATE_LIMIT_PER_MINUTE:-1200}"
RL_AUTH="${AUTH_RATE_LIMIT_PER_MINUTE:-60}"
pos_ok() { matches "$1" '^[1-9][0-9]{0,6}$'; }
pos_ok "$RL_SITE" || die "RATE_LIMIT_PER_MINUTE must be a whole number above 0: $RL_SITE"
pos_ok "$RL_AUTH" || die "AUTH_RATE_LIMIT_PER_MINUTE must be a whole number above 0: $RL_AUTH"
# Traefik limits are a steady rate plus a burst allowance; a burst of about ten seconds' worth lets a page load all its files at once.
RL_SITE_BURST=$((RL_SITE / 6)); [ "$RL_SITE_BURST" -ge 20 ] || RL_SITE_BURST=20
RL_AUTH_BURST=$((RL_AUTH / 3)); [ "$RL_AUTH_BURST" -ge 5 ] || RL_AUTH_BURST=5

CF_LIST=""
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
      CF_LIST="${CF_LIST:+$CF_LIST, }\"$r\""
    done < "$CF_FILE"
    [ -n "$CF_LIST" ] || die "$CF_FILE has no IP ranges" ;;
  *) die "CLOUDFLARE_PROXY must be on or off: $CLOUDFLARE_PROXY" ;;
esac

HTTP_ADDR=":80"; HTTPS_ADDR=":443"
if [ -n "${HTTP_PORT:-}" ];  then num_ok "$HTTP_PORT"  || die "HTTP_PORT must be a number";  HTTP_ADDR=":$HTTP_PORT"; fi
if [ -n "${HTTPS_PORT:-}" ]; then num_ok "$HTTPS_PORT" || die "HTTPS_PORT must be a number"; HTTPS_ADDR=":$HTTPS_PORT"; fi

# Host(`a`) || Host(`b`) — names are validated above, so no backticks can appear. With no domain ('none' only), match everything.
RULE=""
OLD_IFS=$IFS; IFS=','
for d in $DOMAIN; do
  d=$(printf '%s' "$d" | tr -d ' ')
  [ -n "$d" ] || continue
  RULE="${RULE:+$RULE || }Host(\`$d\`)"
done
IFS=$OLD_IFS
[ -n "$RULE" ] || RULE="PathPrefix(\`/\`)"

# ── static config ─────────────────────────────────────────────────────────────
RESOLVER=""
if [ -n "$CA" ]; then
  RESOLVER="certificatesResolvers:
  openoptout:
    acme:
      caServer: \"$CA\"
      storage: \"$ACME_STORAGE\""
  if [ "$CHALLENGE" = "cloudflare" ]; then
    # Public resolvers, so a home router's own DNS can't hide the new record.
    RESOLVER="$RESOLVER
      dnsChallenge:
        provider: cloudflare
        resolvers: [\"1.1.1.1:53\", \"1.0.0.1:53\"]"
  else
    RESOLVER="$RESOLVER
      httpChallenge:
        entryPoint: web"
  fi
  [ -n "$EMAIL" ] && RESOLVER="$RESOLVER
      email: \"$EMAIL\""
  if [ -n "${ACME_CA_ROOT:-}" ]; then
    path_ok "$ACME_CA_ROOT" || die "ACME_CA_ROOT must be an absolute path: $ACME_CA_ROOT"
    [ -f "$ACME_CA_ROOT" ] || die "ACME_CA_ROOT file not found: $ACME_CA_ROOT"
    RESOLVER="$RESOLVER
      caCertificates:
        - \"$ACME_CA_ROOT\""
  fi
  if [ -n "${ACME_CERT_DURATION_HOURS:-}" ]; then   # testing only (short-lived certs)
    num_ok "$ACME_CERT_DURATION_HOURS" || die "ACME_CERT_DURATION_HOURS must be a number"
    RESOLVER="$RESOLVER
      certificatesDuration: $ACME_CERT_DURATION_HOURS"
  fi
fi

# With a certificate, port 80 only redirects to HTTPS. With none, it serves.
REDIRECT=""
if [ "$MODE" != "none" ]; then
  REDIRECT="    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true"
fi

# Behind Cloudflare: only Cloudflare may pass X-Forwarded-* along (Traefik strips them from anyone else), so the chain the app counts stays honest.
FWD=""
if [ -n "$CF_LIST" ]; then
  FWD="    forwardedHeaders:
      trustedIPs: [$CF_LIST]"
fi

mkdir -p "$CONF_DIR"
cat > "$CONF_DIR/traefik.yml" <<EOF
# Generated by deploy/traefik/entrypoint.sh at container start — edit .env, not this file.
global:
  checkNewVersion: false
  sendAnonymousUsage: false
log:
  level: INFO
accessLog: false
entryPoints:
  web:
    address: "$HTTP_ADDR"
$REDIRECT
$FWD
  websecure:
    address: "$HTTPS_ADDR"
    http3: {}
$FWD
providers:
  file:
    filename: "$CONF_DIR/dynamic.yml"
    watch: false
$RESOLVER
EOF

# ── dynamic config ────────────────────────────────────────────────────────────
ROUTER_EP="websecure"
if [ "$MODE" = "none" ]; then
  ROUTER_EP="web"; ROUTER_TLS=""; TLS_FILES=""
elif [ -n "$CA" ]; then
  ROUTER_TLS="      tls:
        certResolver: openoptout"
  TLS_FILES=""
else
  CERT="${TLS_CERT_FILE:-/certs/fullchain.pem}"
  KEY="${TLS_KEY_FILE:-/certs/privkey.pem}"
  if ! path_ok "$CERT" || ! path_ok "$KEY"; then
    die "TLS_CERT_FILE / TLS_KEY_FILE must be absolute paths."
  fi
  [ -f "$CERT" ] || die "Certificate file not found: $CERT (put it in ./deploy/certs)"
  [ -f "$KEY" ]  || die "Key file not found: $KEY (put it in ./deploy/certs)"
  ROUTER_TLS="      tls: {}"
  TLS_FILES="  certificates:
    - certFile: \"$CERT\"
      keyFile: \"$KEY\"
  stores:
    default:
      defaultCertificate:
        certFile: \"$CERT\"
        keyFile: \"$KEY\""
fi

HSTS_LINE=""
[ "${HSTS:-on}" != "off" ] && [ "$MODE" != "none" ] && HSTS_LINE="          stsSeconds: 31536000"

# Middleware chains, in order: drop non-Cloudflare connections, rate limit, then headers/compression. Sign-in endpoints get their own, stricter router.
SITE_MW="openoptout-headers, openoptout-compress"
AUTH_MW="openoptout-headers, openoptout-compress"
PROTECT_MW=""
if [ "$RATE_LIMIT" = "on" ]; then
  SITE_MW="openoptout-ratelimit, $SITE_MW"
  AUTH_MW="openoptout-signin-ratelimit, $AUTH_MW"
  # Who counts as "one visitor": the connecting address, or — behind Cloudflare, where every connection comes from Cloudflare — the visitor IP Cloudflare reports (safe: nobody else can connect, see cloudflare-only).
  if [ -n "$CF_LIST" ]; then
    SOURCE="        sourceCriterion:
          requestHeaderName: \"Cf-Connecting-Ip\""
  else
    SOURCE=""
  fi
  PROTECT_MW="    openoptout-ratelimit:
      rateLimit:
        average: $RL_SITE
        period: 1m
        burst: $RL_SITE_BURST
$SOURCE
    openoptout-signin-ratelimit:
      rateLimit:
        average: $RL_AUTH
        period: 1m
        burst: $RL_AUTH_BURST
$SOURCE"
fi
if [ -n "$CF_LIST" ]; then
  SITE_MW="openoptout-cloudflare-only, $SITE_MW"
  AUTH_MW="openoptout-cloudflare-only, $AUTH_MW"
  PROTECT_MW="$PROTECT_MW
    openoptout-cloudflare-only:
      ipAllowList:
        sourceRange: [$CF_LIST]"
fi

cat > "$CONF_DIR/dynamic.yml" <<EOF
# Generated by deploy/traefik/entrypoint.sh at container start — edit .env, not this file.
http:
  routers:
    openoptout:
      rule: "$RULE"
      entryPoints: [$ROUTER_EP]
      service: openoptout
      middlewares: [$SITE_MW]
$ROUTER_TLS
    openoptout-signin:
      rule: "($RULE) && PathPrefix(\`/api/auth/\`)"
      entryPoints: [$ROUTER_EP]
      service: openoptout
      middlewares: [$AUTH_MW]
$ROUTER_TLS
  middlewares:
$PROTECT_MW
    openoptout-headers:
      headers:
$HSTS_LINE
          contentTypeNosniff: true
          referrerPolicy: "strict-origin-when-cross-origin"
          frameDeny: true
          customResponseHeaders:
            Server: ""
    openoptout-compress:
      compress:
        encodings: [zstd, gzip]
  services:
    openoptout:
      loadBalancer:
        passHostHeader: true
        servers:
          - url: "http://$UPSTREAM"
tls:
  options:
    default:
      minVersion: VersionTLS12
$TLS_FILES
EOF

echo "OpenOptOut HTTPS (Traefik): mode=$MODE challenge=$CHALLENGE rate_limit=$RATE_LIMIT cloudflare_proxy=${CLOUDFLARE_PROXY:-off} domain=${DOMAIN:-(any)} upstream=$UPSTREAM"
if [ "${GENERATE_ONLY:-}" = "1" ]; then
  cat "$CONF_DIR/traefik.yml" "$CONF_DIR/dynamic.yml"
  exit 0
fi
# Traefik's Cloudflare provider reads this name; .env uses the clearer one.
if [ "$CHALLENGE" = "cloudflare" ]; then
  CF_DNS_API_TOKEN="$CLOUDFLARE_API_TOKEN"; export CF_DNS_API_TOKEN
fi
exec traefik --configFile="$CONF_DIR/traefik.yml"
