#!/usr/bin/env bash
# ==============================================================================
# End-to-end HTTPS test for the Traefik front door: real ACME certificate
# issuance AND automatic renewal, using the exact Traefik config OpenOptOut
# generates (deploy/traefik/entrypoint.sh). The Caddy equivalent is acme_e2e.sh.
#
# Pebble (Let's Encrypt's official test ACME server) stands in for Let's Encrypt,
# issuing 2-minute certificates so a full renewal happens within the test.
# Needs: Linux x86_64, bash, curl, openssl, python3, and permission to add one
# /etc/hosts entry (run with sudo, or pre-add "127.0.0.1 openoptout.test").
#
#   ./deploy/tests/acme_e2e_traefik.sh     # takes ~2 minutes
# ==============================================================================
set -euo pipefail
TRAEFIK_VERSION=3.7.7     # keep in step with the traefik image in docker-compose.yml
PEBBLE_VERSION=v2.6.0
HERE="$(cd "$(dirname "$0")" && pwd)"
ENTRY="$HERE/../traefik/entrypoint.sh"
WORK="$(mktemp -d)"; PIDS=()
# shellcheck disable=SC2317,SC2329
cleanup() {
  for p in "${PIDS[@]:-}"; do
    if [ -n "$p" ]; then
      kill "$p" 2>/dev/null || true
    fi
  done
  rm -rf "$WORK"
}
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; tail -20 "$WORK/traefik.log" >&2 || true; exit 1; }
cd "$WORK"

if ! grep -q "openoptout.test" /etc/hosts; then
  echo "127.0.0.1 openoptout.test" >> /etc/hosts || fail "add '127.0.0.1 openoptout.test' to /etc/hosts (or run with sudo)"
fi

echo "Downloading Traefik $TRAEFIK_VERSION and Pebble $PEBBLE_VERSION…"
curl -sfL "https://github.com/traefik/traefik/releases/download/v${TRAEFIK_VERSION}/traefik_v${TRAEFIK_VERSION}_linux_amd64.tar.gz" | tar xz traefik
curl -sfL "https://github.com/letsencrypt/pebble/releases/download/${PEBBLE_VERSION}/pebble-linux-amd64.tar.gz" | tar xz
mv pebble-linux-amd64/linux/amd64/pebble . && chmod +x traefik pebble
R="https://raw.githubusercontent.com/letsencrypt/pebble/${PEBBLE_VERSION}"
mkdir -p test/certs/localhost
for f in test/certs/localhost/cert.pem test/certs/localhost/key.pem test/certs/pebble.minica.pem; do curl -sfL -o "$f" "$R/$f"; done
cat > pebble.json << 'EOF'
{"pebble": {"listenAddress": "127.0.0.1:14000", "managementListenAddress": "127.0.0.1:15000",
  "certificate": "test/certs/localhost/cert.pem", "privateKey": "test/certs/localhost/key.pem",
  "httpPort": 5002, "tlsPort": 5001, "ocspResponderURL": "", "externalAccountBindingRequired": false,
  "certificateValidityPeriod": 120}}
EOF

mkdir -p www && echo "OpenOptOut OK" > www/index.html
(cd www && exec python3 -m http.server 8080 --bind 127.0.0.1 >/dev/null 2>&1) & PIDS+=($!)
PEBBLE_VA_NOSLEEP=1 PEBBLE_WFE_NONCEREJECT=0 PEBBLE_AUTHZREUSE=0 ./pebble -config pebble.json > pebble.log 2>&1 & PIDS+=($!)
sleep 2
# ACME_CERT_DURATION_HOURS=1 tells Traefik the certs are short-lived, so it
# checks every minute and renews well before Pebble's 2-minute expiry.
PATH="$WORK:$PATH" \
  HTTPS_MODE=acme ACME_CA=https://localhost:14000/dir ACME_CA_ROOT="$WORK/test/certs/pebble.minica.pem" \
  DOMAIN=openoptout.test UPSTREAM=127.0.0.1:8080 HTTP_PORT=5002 HTTPS_PORT=5001 \
  ACME_CERT_DURATION_HOURS=1 TRAEFIK_CONF_DIR="$WORK/conf" ACME_STORAGE="$WORK/acme.json" \
  sh "$ENTRY" > traefik.log 2>&1 & PIDS+=($!)

curl -sfk https://127.0.0.1:15000/roots/0 --retry 5 --retry-connrefused > root.pem
body=""
for _ in $(seq 1 45); do
  body="$(curl -s --max-time 3 --cacert root.pem https://openoptout.test:5001/ || true)"
  [ "$body" = "OpenOptOut OK" ] && break
  sleep 1
done
[ "$body" = "OpenOptOut OK" ] || fail "certificate was not issued (verified HTTPS request failed)"
echo "PASS  issued: verified HTTPS works"
curl -sI --max-time 5 http://openoptout.test:5002/ | grep -qi "^location: https://" || fail "HTTP did not redirect to HTTPS"
echo "PASS  HTTP redirects to HTTPS"
hdrs="$(curl -sI --max-time 5 --cacert root.pem https://openoptout.test:5001/)"
for h in strict-transport-security x-content-type-options x-frame-options referrer-policy; do
  printf '%s' "$hdrs" | grep -qi "^$h:" || fail "$h header missing"
done
printf '%s' "$hdrs" | grep -qi "^server:" && fail "Server header should be stripped"
echo "PASS  security headers present"

serial() { echo | timeout 5 openssl s_client -connect 127.0.0.1:5001 -servername openoptout.test 2>/dev/null | openssl x509 -noout -serial 2>/dev/null; }
first="$(serial)"; [ -n "$first" ] || fail "could not read certificate"
echo "      waiting for automatic renewal of $first (≈60-90s)…"
for i in $(seq 1 15); do
  sleep 10; now="$(serial)"
  if [ -n "$now" ] && [ "$now" != "$first" ]; then
    body="$(curl -s --max-time 5 --cacert root.pem https://openoptout.test:5001/)"
    [ "$body" = "OpenOptOut OK" ] || fail "site broken after renewal"
    echo "PASS  renewed automatically after ~$((i*10))s ($now) and still serving"
    if grep -qi 'level=error\|"level":"error"\| ERR ' traefik.log; then
      fail "Traefik logged errors"
    fi
    echo "ALL PASS"; exit 0
  fi
done
fail "certificate was not renewed within 150s"
