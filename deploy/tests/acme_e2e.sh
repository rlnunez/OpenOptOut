#!/usr/bin/env bash
# ==============================================================================
# End-to-end HTTPS test: real ACME certificate issuance AND automatic renewal,
# using the exact Caddy config PrivacyShield generates (deploy/caddy/entrypoint.sh).
#
# Pebble (Let's Encrypt's official test ACME server) stands in for Let's Encrypt,
# issuing 2-minute certificates so a full renewal happens within the test.
# Needs: Linux x86_64, bash, curl, openssl, python3, and permission to add one
# /etc/hosts entry (run with sudo, or pre-add "127.0.0.1 privacyshield.test").
#
#   ./deploy/tests/acme_e2e.sh          # takes ~2 minutes
# ==============================================================================
set -euo pipefail
CADDY_VERSION=2.8.4
PEBBLE_VERSION=v2.6.0
HERE="$(cd "$(dirname "$0")" && pwd)"
ENTRY="$HERE/../caddy/entrypoint.sh"
WORK="$(mktemp -d)"; PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done; rm -rf "$WORK"; }
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
cd "$WORK"

grep -q "privacyshield.test" /etc/hosts || echo "127.0.0.1 privacyshield.test" >> /etc/hosts \
  || fail "add '127.0.0.1 privacyshield.test' to /etc/hosts (or run with sudo)"

echo "Downloading Caddy $CADDY_VERSION and Pebble $PEBBLE_VERSION…"
curl -sfL "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" | tar xz caddy
curl -sfL "https://github.com/letsencrypt/pebble/releases/download/${PEBBLE_VERSION}/pebble-linux-amd64.tar.gz" | tar xz
mv pebble-linux-amd64/linux/amd64/pebble . && chmod +x caddy pebble
R="https://raw.githubusercontent.com/letsencrypt/pebble/${PEBBLE_VERSION}"
mkdir -p test/certs/localhost
for f in test/certs/localhost/cert.pem test/certs/localhost/key.pem test/certs/pebble.minica.pem; do curl -sfL -o "$f" "$R/$f"; done
cat > pebble.json << 'EOF'
{"pebble": {"listenAddress": "127.0.0.1:14000", "managementListenAddress": "127.0.0.1:15000",
  "certificate": "test/certs/localhost/cert.pem", "privateKey": "test/certs/localhost/key.pem",
  "httpPort": 5002, "tlsPort": 5001, "ocspResponderURL": "", "externalAccountBindingRequired": false,
  "certificateValidityPeriod": 120}}
EOF

mkdir -p www && echo "PrivacyShield OK" > www/index.html
(cd www && exec python3 -m http.server 8080 --bind 127.0.0.1 >/dev/null 2>&1) & PIDS+=($!)
PEBBLE_VA_NOSLEEP=1 PEBBLE_WFE_NONCEREJECT=0 PEBBLE_AUTHZREUSE=0 ./pebble -config pebble.json > pebble.log 2>&1 & PIDS+=($!)
sleep 2
PATH="$WORK:$PATH" XDG_DATA_HOME="$WORK/cd" XDG_CONFIG_HOME="$WORK/cc" \
  HTTPS_MODE=acme ACME_CA=https://localhost:14000/dir ACME_CA_ROOT="$WORK/test/certs/pebble.minica.pem" \
  DOMAIN=privacyshield.test UPSTREAM=127.0.0.1:8080 HTTP_PORT=5002 HTTPS_PORT=5001 RENEW_INTERVAL=10s \
  CADDYFILE="$WORK/Caddyfile" sh "$ENTRY" > caddy.log 2>&1 & PIDS+=($!)

for _ in $(seq 1 30); do grep -q "certificate obtained successfully" caddy.log && break; sleep 1; done
grep -q "certificate obtained successfully" caddy.log || { tail -20 caddy.log; fail "certificate was not issued"; }
curl -sk https://127.0.0.1:15000/roots/0 > root.pem
body="$(curl -s --max-time 5 --cacert root.pem https://privacyshield.test:5001/)"
[ "$body" = "PrivacyShield OK" ] || fail "verified HTTPS request failed (got: $body)"
echo "PASS  issued: verified HTTPS works"
curl -sI --max-time 5 http://privacyshield.test:5002/ | grep -qi "^location: https://" || fail "HTTP did not redirect to HTTPS"
echo "PASS  HTTP redirects to HTTPS"
curl -sI --max-time 5 --cacert root.pem https://privacyshield.test:5001/ | grep -qi "^strict-transport-security" || fail "HSTS header missing"
echo "PASS  security headers present"

serial() { echo | timeout 5 openssl s_client -connect 127.0.0.1:5001 -servername privacyshield.test 2>/dev/null | openssl x509 -noout -serial 2>/dev/null; }
first="$(serial)"; [ -n "$first" ] || fail "could not read certificate"
echo "      waiting for automatic renewal of $first (≈80s)…"
for i in $(seq 1 15); do
  sleep 10; now="$(serial)"
  if [ -n "$now" ] && [ "$now" != "$first" ]; then
    body="$(curl -s --max-time 5 --cacert root.pem https://privacyshield.test:5001/)"
    [ "$body" = "PrivacyShield OK" ] || fail "site broken after renewal"
    echo "PASS  renewed automatically after ~$((i*10))s ($now) and still serving"
    grep -q '"level":"error"' caddy.log && fail "Caddy logged errors" || true
    echo "ALL PASS"; exit 0
  fi
done
fail "certificate was not renewed within 150s"
