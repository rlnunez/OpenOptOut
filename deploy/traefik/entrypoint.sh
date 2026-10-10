#!/bin/sh
# ==============================================================================
# OpenOptOut HTTPS front door (Traefik option) — generates Traefik's static and
# dynamic config from environment variables, then runs Traefik. Traefik obtains
# certificates, renews them automatically, and redirects HTTP to HTTPS.
#
# This is the alternative to deploy/caddy/entrypoint.sh, for admins who already
# know and prefer Traefik. Both read the same .env keys; pick one with
# FRONT_DOOR=caddy|traefik (scripts/enable-https.* --proxy sets it).
#
#   HTTPS_MODE   letsencrypt          Let's Encrypt (public server; ports 80+443
#                                     reachable from the internet, DNS pointing here)
#                letsencrypt-staging  Let's Encrypt's test environment (untrusted
#                                     certs; use while testing to avoid rate limits)
#                acme                 Any ACME CA, e.g. an internal step-ca
#                                     (ACME_CA = directory URL, ACME_CA_ROOT optional)
#                custom               Your own certificate files (TLS_CERT_FILE /
#                                     TLS_KEY_FILE, mounted from ./deploy/certs)
#                (internal is Caddy-only: Traefik has no private CA of its own.)
#   DOMAIN       e.g. privacy.example.org (comma-separate several; no wildcards —
#                HTTP-01 challenges can't issue them)
#   ACME_EMAIL   contact address for the CA (recommended)
#   UPSTREAM     where to send traffic (default web:80)
#   HSTS         on (default) | off
#
# No Docker socket is mounted and the Docker provider is never enabled: routing
# comes only from the file written here, so nothing that reaches Traefik can
# discover or steer other containers on the host.
#
# Every value is validated before it's written: an unchecked value containing a
# newline, quote, or backtick could inject arbitrary Traefik configuration.
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

[ -n "$DOMAIN" ] || die "DOMAIN is not set (e.g. DOMAIN=privacy.example.org in .env)."
case "$DOMAIN" in *'*'*) die "Wildcard domains aren't supported with Traefik (Let's Encrypt can't issue them over HTTP). List each name, or use FRONT_DOOR=caddy." ;; esac
matches "$DOMAIN" '^[A-Za-z0-9.-]+(, *[A-Za-z0-9.-]+)*$' || die "DOMAIN has invalid characters: $DOMAIN"
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
  custom) CA="" ;;
  internal) die "HTTPS_MODE=internal needs Caddy's private CA. Use FRONT_DOOR=caddy, or HTTPS_MODE=custom with your own certificate." ;;
  "") die "HTTPS_MODE is not set (letsencrypt, letsencrypt-staging, acme, custom)." ;;
  *)  die "Unknown HTTPS_MODE '$MODE' (letsencrypt, letsencrypt-staging, acme, custom)." ;;
esac

HTTP_ADDR=":80"; HTTPS_ADDR=":443"
if [ -n "${HTTP_PORT:-}" ];  then num_ok "$HTTP_PORT"  || die "HTTP_PORT must be a number";  HTTP_ADDR=":$HTTP_PORT"; fi
if [ -n "${HTTPS_PORT:-}" ]; then num_ok "$HTTPS_PORT" || die "HTTPS_PORT must be a number"; HTTPS_ADDR=":$HTTPS_PORT"; fi

# Host(`a`) || Host(`b`) — names are validated above, so no backticks can appear.
RULE=""
OLD_IFS=$IFS; IFS=','
for d in $DOMAIN; do
  d=$(printf '%s' "$d" | tr -d ' ')
  [ -n "$d" ] || continue
  RULE="${RULE:+$RULE || }Host(\`$d\`)"
done
IFS=$OLD_IFS

# ── static config ─────────────────────────────────────────────────────────────
RESOLVER=""
if [ -n "$CA" ]; then
  RESOLVER="certificatesResolvers:
  openoptout:
    acme:
      caServer: \"$CA\"
      storage: \"$ACME_STORAGE\"
      httpChallenge:
        entryPoint: web"
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
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true
  websecure:
    address: "$HTTPS_ADDR"
    http3: {}
providers:
  file:
    filename: "$CONF_DIR/dynamic.yml"
    watch: false
$RESOLVER
EOF

# ── dynamic config ────────────────────────────────────────────────────────────
if [ -n "$CA" ]; then
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
[ "${HSTS:-on}" != "off" ] && HSTS_LINE="          stsSeconds: 31536000"

cat > "$CONF_DIR/dynamic.yml" <<EOF
# Generated by deploy/traefik/entrypoint.sh at container start — edit .env, not this file.
http:
  routers:
    openoptout:
      rule: "$RULE"
      entryPoints: [websecure]
      service: openoptout
      middlewares: [openoptout-headers, openoptout-compress]
$ROUTER_TLS
  middlewares:
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

echo "OpenOptOut HTTPS (Traefik): mode=$MODE domain=$DOMAIN upstream=$UPSTREAM"
if [ "${GENERATE_ONLY:-}" = "1" ]; then
  cat "$CONF_DIR/traefik.yml" "$CONF_DIR/dynamic.yml"
  exit 0
fi
exec traefik --configFile="$CONF_DIR/traefik.yml"
