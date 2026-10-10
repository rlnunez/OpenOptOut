#!/usr/bin/env bash
# ==============================================================================
# End-to-end test of HTTPS_MODE=incommon (InCommon certificates via CERTInext, beta) on both front doors, using the exact configs OpenOptOut generates.
#
# CERTInext can't be reached without real university credentials, so Pebble (Let's Encrypt's test ACME server) stands in, configured like CERTInext: it refuses any account without External Account Binding (EAB) credentials. For Caddy and then Traefik it checks that:
#   - with the right key ID + HMAC key, a certificate is issued and served
#   - the certificate key is RSA 2048, as CERTInext requires
#   - with a wrong HMAC key, no certificate is issued
# Needs: Linux x86_64, bash, curl, openssl, python3, and one /etc/hosts entry (run with sudo, or pre-add "127.0.0.1 openoptout.test").
#
#   ./deploy/tests/incommon_e2e.sh     # about a minute
# ==============================================================================
set -uo pipefail
CADDY_VERSION=2.8.4
TRAEFIK_VERSION=3.7.7
PEBBLE_VERSION=v2.6.0
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$HERE/../.." && pwd)"
W="$(mktemp -d)"; PIDS=()
# shellcheck disable=SC2317,SC2329
cleanup() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done; rm -rf "$W"; }
trap cleanup EXIT
export NO_PROXY="127.0.0.1,localhost,openoptout.test${NO_PROXY:+,$NO_PROXY}" no_proxy="127.0.0.1,localhost,openoptout.test${no_proxy:+,$no_proxy}"
FAILED=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAILED=1; }
cd "$W" || exit 1

if ! grep -q "openoptout.test" /etc/hosts; then
  echo "127.0.0.1 openoptout.test" >> /etc/hosts || { echo "add '127.0.0.1 openoptout.test' to /etc/hosts (or run with sudo)"; exit 1; }
fi

mkdir -p bin
if [ -n "${CADDY_BIN:-}" ]; then cp "$CADDY_BIN" bin/caddy; else
  curl -sfL "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" | tar xz -C bin caddy || exit 1; fi
if [ -n "${TRAEFIK_BIN:-}" ]; then cp "$TRAEFIK_BIN" bin/traefik; else
  curl -sfL "https://github.com/traefik/traefik/releases/download/v${TRAEFIK_VERSION}/traefik_v${TRAEFIK_VERSION}_linux_amd64.tar.gz" | tar xz -C bin traefik || exit 1; fi
curl -sfL "https://github.com/letsencrypt/pebble/releases/download/${PEBBLE_VERSION}/pebble-linux-amd64.tar.gz" | tar xz || exit 1
mv pebble-linux-amd64/linux/amd64/pebble bin/ && chmod +x bin/*
export PATH="$W/bin:$PATH"
R="https://raw.githubusercontent.com/letsencrypt/pebble/${PEBBLE_VERSION}"
mkdir -p test/certs/localhost
for f in test/certs/localhost/cert.pem test/certs/localhost/key.pem test/certs/pebble.minica.pem; do curl -sfL -o "$f" "$R/$f" || exit 1; done

# EAB credentials, as campus IT would issue them: a key ID and a base64url HMAC key.
KID="openoptout-test-kid"
HMAC="$(openssl rand 32 | base64 | tr '+/' '-_' | tr -d '=\n')"
cat > pebble.json <<JSON
{"pebble": {"listenAddress": "127.0.0.1:14000", "managementListenAddress": "127.0.0.1:15000",
  "certificate": "test/certs/localhost/cert.pem", "privateKey": "test/certs/localhost/key.pem",
  "httpPort": 5002, "tlsPort": 5001, "ocspResponderURL": "",
  "externalAccountBindingRequired": true, "externalAccountMACKeys": {"$KID": "$HMAC"}}}
JSON
PEBBLE_VA_NOSLEEP=1 PEBBLE_WFE_NONCEREJECT=0 PEBBLE_AUTHZREUSE=0 pebble -config pebble.json > pebble.log 2>&1 & PIDS+=($!)
mkdir -p www && echo "OpenOptOut OK" > www/index.html
(cd www && exec python3 -m http.server 8080 --bind 127.0.0.1 >/dev/null 2>&1) & PIDS+=($!)
sleep 2
curl -sfk --retry 5 --retry-connrefused https://127.0.0.1:15000/roots/0 > root.pem

COMMON=(HTTPS_MODE=incommon ACME_CA=https://localhost:14000/dir ACME_CA_ROOT="$W/test/certs/pebble.minica.pem"
        DOMAIN=openoptout.test UPSTREAM=127.0.0.1:8080 HTTP_PORT=5002 HTTPS_PORT=5001 RATE_LIMIT=off ACME_EAB_KID="$KID")

run_door() {  # run_door <caddy|traefik> <hmac> -> starts it, sets DOOR_PID
  local door=$1 hmac=$2 tag=$1-$3
  if [ "$door" = caddy ]; then
    env "${COMMON[@]}" ACME_EAB_HMAC="$hmac" CADDYFILE="$W/$tag.Caddyfile" XDG_DATA_HOME="$W/$tag.d" XDG_CONFIG_HOME="$W/$tag.c" \
      sh "$REPO/deploy/caddy/entrypoint.sh" > "$W/$tag.log" 2>&1 &
  else
    env "${COMMON[@]}" ACME_EAB_HMAC="$hmac" TRAEFIK_CONF_DIR="$W/$tag" ACME_STORAGE="$W/$tag-acme.json" \
      sh "$REPO/deploy/traefik/entrypoint.sh" > "$W/$tag.log" 2>&1 &
  fi
  DOOR_PID=$!; PIDS+=("$DOOR_PID")
}
served() { curl -s --max-time 3 --cacert root.pem https://openoptout.test:5001/; }

for door in caddy traefik; do
  P=$([ "$door" = caddy ] && echo Caddy || echo Traefik)
  # Right credentials: issued, served, RSA 2048.
  run_door "$door" "$HMAC" good
  body=""; for _ in $(seq 1 40); do body="$(served || true)"; [ "$body" = "OpenOptOut OK" ] && break; sleep 1; done
  if [ "$body" = "OpenOptOut OK" ]; then pass "$P: certificate issued with the key ID + HMAC key, and served"; else fail "$P: no certificate with valid credentials"; tail -5 "$W/$door-good.log"; fi
  bits="$(echo | timeout 5 openssl s_client -connect 127.0.0.1:5001 -servername openoptout.test 2>/dev/null | openssl x509 -noout -text 2>/dev/null | grep -o 'Public-Key: ([0-9]* bit)' | head -1)"
  algo="$(echo | timeout 5 openssl s_client -connect 127.0.0.1:5001 -servername openoptout.test 2>/dev/null | openssl x509 -noout -text 2>/dev/null | grep -o 'Public Key Algorithm: [a-zA-Z]*' | head -1)"
  if [ "$bits" = "Public-Key: (2048 bit)" ] && [ "$algo" = "Public Key Algorithm: rsaEncryption" ]; then pass "$P: key is RSA 2048, as CERTInext requires"; else fail "$P: key was '$algo' '$bits'"; fi
  kill "$DOOR_PID" 2>/dev/null; wait "$DOOR_PID" 2>/dev/null; sleep 1

  # Wrong HMAC key: the CA must refuse the account, so nothing is issued.
  wrong="$(openssl rand 32 | base64 | tr '+/' '-_' | tr -d '=\n')"
  run_door "$door" "$wrong" bad
  sleep 10
  if [ "$(served || true)" = "OpenOptOut OK" ]; then fail "$P: a certificate was issued with a WRONG HMAC key"; else pass "$P: wrong HMAC key refused (no certificate)"; fi
  kill "$DOOR_PID" 2>/dev/null; wait "$DOOR_PID" 2>/dev/null; sleep 1
done

# The HMAC key must never land in the generated config files (Caddy) or in saved config (Caddy autosave).
if grep -rl "$HMAC" "$W"/caddy-good.Caddyfile "$W"/caddy-good.c 2>/dev/null | grep -q .; then fail "Caddy: HMAC key found on disk"; else pass "Caddy: HMAC key never written to its config or saved config"; fi

if [ "$FAILED" = 0 ]; then echo "ALL PASS"; exit 0; else echo "SOME FAILED"; exit 1; fi
