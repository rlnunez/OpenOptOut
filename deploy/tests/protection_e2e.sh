#!/usr/bin/env bash
# ==============================================================================
# End-to-end test of front door flood protection (Traefik and Caddy):
#   - CLOUDFLARE_PROXY=on: non-Cloudflare IPs refused; forwarded visitor IP kept
#   - CLOUDFLARE_PROXY=off: forged X-Forwarded-For replaced
#   - Rate limits return 429 for general site and sign-in routes
#
# Simulates Cloudflare by setting CLOUDFLARE_IPS_FILE to 127.0.0.1.
# Tests Caddy rate limits if CADDY_BIN is provided; otherwise verifies error on stock Caddy without rate-limit module.
# Requires: Linux x86_64, bash, curl, openssl, python3.
#
#   ./deploy/tests/protection_e2e.sh
#   CADDY_BIN=/path/to/extended/caddy ./deploy/tests/protection_e2e.sh
# ==============================================================================
set -uo pipefail
TRAEFIK_VERSION=3.7.7   # keep in step with docker-compose.yml
CADDY_VERSION=2.8.4
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$HERE/../.." && pwd)"
W="$(mktemp -d)"; PIDS=()
# shellcheck disable=SC2317,SC2329
cleanup() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done; rm -rf "$W"; }
trap cleanup EXIT
export NO_PROXY="127.0.0.1,localhost,openoptout.test${NO_PROXY:+,$NO_PROXY}" no_proxy="127.0.0.1,localhost,openoptout.test${no_proxy:+,$no_proxy}"
FAILED=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAILED=1; }

mkdir -p "$W/bin"
if [ -n "${TRAEFIK_BIN:-}" ]; then cp "$TRAEFIK_BIN" "$W/bin/traefik"; else
  curl -sfL "https://github.com/traefik/traefik/releases/download/v${TRAEFIK_VERSION}/traefik_v${TRAEFIK_VERSION}_linux_amd64.tar.gz" | tar xz -C "$W/bin" traefik || { echo "couldn't download Traefik"; exit 1; }
fi
if [ -n "${CADDY_BIN:-}" ]; then cp "$CADDY_BIN" "$W/bin/caddy"; else
  curl -sfL "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" | tar xz -C "$W/bin" caddy || { echo "couldn't download Caddy"; exit 1; }
fi
chmod +x "$W/bin/"*; export PATH="$W/bin:$PATH"
CADDY_HAS_RL=0; caddy list-modules 2>/dev/null | grep -q '^http.handlers.rate_limit$' && CADDY_HAS_RL=1

openssl req -x509 -newkey rsa:2048 -nodes -keyout "$W/k.pem" -out "$W/c.pem" -days 2 \
  -subj /CN=openoptout.test -addext subjectAltName=DNS:openoptout.test 2>/dev/null
echo "127.0.0.1/32" > "$W/cf-us.txt"       # "Cloudflare" = this test
echo "127.0.0.2/32" > "$W/cf-notus.txt"    # "Cloudflare" = someone else

# Upstream that echoes the X-Forwarded-For it received.
cat > "$W/echo.py" <<'PY'
import http.server, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = (self.headers.get("X-Forwarded-For") or "-").encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
python3 "$W/echo.py" 8095 & PIDS+=($!)

req()  { curl -s --max-time 3 --cacert "$W/c.pem" --resolve "openoptout.test:$1:127.0.0.1" "${@:3}" "https://openoptout.test:$1$2"; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 3 --cacert "$W/c.pem" --resolve "openoptout.test:$1:127.0.0.1" "https://openoptout.test:$1$2"; }

start() {  # start <name> <traefik|caddy> <https-port> [ENV=VALUE...]
  local name=$1 proxy=$2 port=$3; shift 3
  local common=(HTTPS_MODE=custom DOMAIN=openoptout.test TLS_CERT_FILE="$W/c.pem" TLS_KEY_FILE="$W/k.pem"
                UPSTREAM=127.0.0.1:8095 HTTPS_PORT="$port" HTTP_PORT=$((port + 1)))
  if [ "$proxy" = traefik ]; then
    env "${common[@]}" TRAEFIK_CONF_DIR="$W/$name" "$@" sh "$REPO/deploy/traefik/entrypoint.sh" > "$W/$name.log" 2>&1 &
  else
    env "${common[@]}" CADDYFILE="$W/$name.Caddyfile" XDG_DATA_HOME="$W/$name.d" XDG_CONFIG_HOME="$W/$name.c" "$@" \
      sh "$REPO/deploy/caddy/entrypoint.sh" > "$W/$name.log" 2>&1 &
  fi
  PIDS+=($!)
}

RL_TEST=(RATE_LIMIT=on RATE_LIMIT_PER_MINUTE=30 AUTH_RATE_LIMIT_PER_MINUTE=6)
start t_cf_block traefik 6101 CLOUDFLARE_PROXY=on CLOUDFLARE_IPS_FILE="$W/cf-notus.txt" RATE_LIMIT=off
start t_cf_ok    traefik 6111 CLOUDFLARE_PROXY=on CLOUDFLARE_IPS_FILE="$W/cf-us.txt" RATE_LIMIT=off
start t_plain    traefik 6121 RATE_LIMIT=off
start t_rl       traefik 6131 "${RL_TEST[@]}"
start c_cf_block caddy   6201 CLOUDFLARE_PROXY=on CLOUDFLARE_IPS_FILE="$W/cf-notus.txt" RATE_LIMIT=off
start c_cf_ok    caddy   6211 CLOUDFLARE_PROXY=on CLOUDFLARE_IPS_FILE="$W/cf-us.txt" RATE_LIMIT=off
start c_plain    caddy   6221 RATE_LIMIT=off
start c_rl       caddy   6231 "${RL_TEST[@]}"
sleep 6

for p in t c; do
  if [ "$p" = t ]; then P=Traefik; base=61; else P=Caddy; base=62; fi
  c=$(code "${base}01" /)
  if [ "$c" = 403 ] || [ "$c" = 000 ]; then pass "$P: non-Cloudflare connection refused (HTTP $c)"; else fail "$P: non-Cloudflare connection got HTTP $c"; fi
  x=$(req "${base}11" / -H "X-Forwarded-For: 6.6.6.6, 9.9.9.9" -H "CF-Connecting-IP: 9.9.9.9")
  if [ "$x" = "6.6.6.6, 9.9.9.9, 127.0.0.1" ]; then pass "$P: from Cloudflare, visitor chain kept ($x)"; else fail "$P: from Cloudflare, upstream saw '$x'"; fi
  x=$(req "${base}21" / -H "X-Forwarded-For: 6.6.6.6")
  if [ "$x" = "127.0.0.1" ]; then pass "$P: direct visitor's forged X-Forwarded-For replaced"; else fail "$P: forged X-Forwarded-For reached upstream: '$x'"; fi
done

check_limits() {  # check_limits <name> <port>
  local n=0 a=0
  for _ in $(seq 1 40); do [ "$(code "$2" /)" = 429 ] && n=$((n + 1)); done
  if [ "$n" -gt 0 ]; then pass "$1: site limit returned 429 for $n of 40 rapid requests"; else fail "$1: no 429 from the site limit"; fi
  # The sign-in limit is separate and much lower, so sign-in attempts hit it fast.
  for _ in $(seq 1 10); do [ "$(code "$2" /api/auth/login)" = 429 ] && a=$((a + 1)); done
  if [ "$a" -gt 0 ]; then pass "$1: sign-in limit returned 429 for $a of 10 rapid attempts"; else fail "$1: no 429 from the sign-in limit"; fi
}
check_limits Traefik 6131
if [ "$CADDY_HAS_RL" = 1 ]; then
  check_limits Caddy 6231
else
  if grep -q "RATE_LIMIT=on but this Caddy build has no rate limiting" "$W/c_rl.log"; then
    pass "Caddy (stock build): RATE_LIMIT=on stops with a clear message instead of running unprotected"
  else fail "Caddy (stock build): no clear message for RATE_LIMIT=on"; cat "$W/c_rl.log"; fi
  echo "      (Caddy's rate limits themselves need the extended build: set CADDY_BIN to test them)"
fi

for f in "$W"/t_*.log "$W"/c_cf_*.log "$W"/c_plain.log; do
  if grep -qiE '"level":"error"| ERR |level=error' "$f"; then fail "errors in $(basename "$f")"; grep -iE '"level":"error"| ERR ' "$f" | head -3; fi
done
if [ "$FAILED" = 0 ]; then echo "ALL PASS"; exit 0; else echo "SOME FAILED"; exit 1; fi
