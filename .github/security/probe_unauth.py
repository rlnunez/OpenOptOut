#!/usr/bin/env python3
"""Probe every unauthenticated route of a running OpenOptOut API.

For external security evaluators (see docs/dev/audit-scope.md). It:

  1. Imports the FastAPI app and lists every /api route whose dependency
     tree has NO auth gate (no get_current_user / require_super_admin /
     require_parent). These are the routes reachable with no token. Routes
     that enforce their own token inside the handler (e.g. /api/stats,
     /api/metrics) show up here too — that is expected; the probe then
     confirms they still refuse to serve data.
  2. Hits each one with no credentials and flags any response that looks
     like an auth bypass, a server error, or a leak of a known demo PII
     value or a secret-shaped string.
  3. Runs a handful of targeted checks: path traversal on the wildcard
     routes, SQL-ish payloads into sign-in, and account enumeration on the
     passwordless and magic-link endpoints.

Point it ONLY at a disposable instance you control, seeded with the demo
data from seed_demo.py. Standard library only, so it runs in any Python
container. It never sends real personal data.

Usage:
  python3 .github/security/probe_unauth.py http://127.0.0.1:8000
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# Run from anywhere: put the repo root (two levels up from .github/security/)
# on the path so `backend` imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Demo values written by seed_demo.py — never real people. A probe response
# containing one of these from an unauthenticated route would be a leak.
DEMO_PII = ["Jordan Example", "jordan.demo@example.org", "100 Demo St",
            "Springfield", "+15550100"]
# Shapes of secret VALUES, not field names: a config endpoint legitimately
# returns keys like "ldap_bind_password": null, so matching the key name
# cries wolf. These markers only appear in an actual leaked secret.
SECRET_SHAPES = ["$2b$", "-----begin"]
PATH_PARAM_SAMPLES = {
    "{provider}": "google", "{locale}": "en",
    "{token}": "a" * 40, "{path:path}": "v1/removals",
}


def ungated_api_routes():
    """Return [(method, path)] for /api routes with no auth-gate dependency."""
    from backend.main import app  # noqa: E402
    from backend.core import auth  # noqa: E402
    from fastapi.routing import APIRoute

    hard = {"require_super_admin", "get_current_user", "require_parent"}

    def gated(dependant):
        found = set()

        def walk(dep):
            name = getattr(dep.call, "__name__", "")
            if name in hard:
                found.add(name)
            for sub in dep.dependencies:
                walk(sub)
        walk(dependant)
        return found

    def collect(routes):
        out = []
        for r in routes:
            if isinstance(r, APIRoute):
                out.append((r.path, r.methods, r.dependant))
            elif hasattr(r, "effective_route_contexts"):
                for c in r.effective_route_contexts():
                    if getattr(c, "dependant", None) is not None:
                        out.append((c.path, c.methods, c.dependant))
            elif hasattr(r, "routes"):
                out += collect(r.routes)
        return out

    seen = []
    for path, methods, dep in collect(app.routes):
        if not path.startswith("/api") or gated(dep):
            continue
        for m in sorted((methods or set()) - {"HEAD", "OPTIONS"}):
            seen.append((m, path))
    return sorted(seen, key=lambda x: x[1])


def call(base, method, path, body=None, headers=None, form=False):
    url = base + path
    h = dict(headers or {})
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            h["content-type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            h["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return -1, repr(e)


def leaks(body):
    low = body.lower()
    found = [p for p in DEMO_PII if p in body]
    found += ["secret:" + s for s in SECRET_SHAPES if s in low]
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    bad = 0

    print("== Unauthenticated routes (no auth-gate dependency) ==")
    routes = ungated_api_routes()
    for m, path in routes:
        p = path
        for k, v in PATH_PARAM_SAMPLES.items():
            p = p.replace(k, v)
        if "{" in p:
            continue
        body = {} if m in ("POST", "PUT", "PATCH") else None
        st, bd = call(base, m, p, body)
        hit = leaks(bd)
        # An unauthenticated route should answer 200 only for genuinely public
        # data, or 400/401/403/404/422 otherwise. A 2xx carrying a demo PII
        # value or secret-shaped string, or a 500, is worth a human's eyes.
        flag = ""
        if hit:
            flag = "  <<< LEAK? " + ", ".join(hit)
            bad += 1
        elif st >= 500:
            flag = "  <<< SERVER ERROR"
            bad += 1
        print(f"  [{st}] {m:6} {path}{flag}")

    print("\n== Targeted checks ==")
    for payload in ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "secret.key"]:
        st, bd = call(base, "GET", "/api/stats/" + payload)
        print(f"  [{st}] stats traversal {payload!r} -> {bd[:80]!r}")
        if "root:" in bd:
            bad += 1
    for loc in ["../../../etc/passwd", "..%2f..%2fsecret.key"]:
        st, bd = call(base, "GET", "/api/i18n/translations/"
                      + urllib.parse.quote(loc, safe=""))
        print(f"  [{st}] i18n locale {loc!r} -> {bd[:60]!r}")
        if "root:" in bd or "BEGIN" in bd:
            bad += 1
    for u in ["x@example.org' OR '1'='1", 'x@example.org" --']:
        st, bd = call(base, "POST", "/api/auth/token",
                      {"username": u, "password": "x"}, form=True)
        print(f"  [{st}] login SQLi {u!r} -> {bd[:60]!r}")
        if st in (200,):
            bad += 1
    print("  (account enumeration — same answer for known vs unknown "
          "address is correct)")
    for ep in ("/api/auth/passwordless/magic-link/request",
               "/api/auth/passwordless/options"):
        a = call(base, "POST", ep, {"email": "admin@example.org"})
        b = call(base, "POST", ep, {"email": "nobody@example.org"})
        same = a == b
        print(f"  {ep}: known==unknown? {same}  ({a[0]}/{b[0]})")

    print(f"\nRoutes probed: {len(routes)}   Items needing review: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
