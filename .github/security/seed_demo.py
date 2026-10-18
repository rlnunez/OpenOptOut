#!/usr/bin/env python3
"""Seed a disposable OpenOptOut instance with demo data for security probing.

Creates the first account (super admin), one managed family member, and a few
identity fields, using only made-up values (never real people). Pair it with
probe_unauth.py (see docs/dev/audit-scope.md).

Point it ONLY at a throwaway instance you control. Standard library only.

Usage:
  python3 .github/security/seed_demo.py http://127.0.0.1:8000
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

ADMIN_EMAIL = "admin@example.org"
ADMIN_PW = "Demo-Passphrase-123456"
MEMBER = "Jordan Example"
IDENTITIES = [
    ("email", "jordan.demo@example.org"),
    ("phone", "+15550100"),
    ("address", "100 Demo St"),
    ("city", "Springfield"),
    ("state", "IL"),
]


def call(method, url, body=None, token=None, form=False):
    h = {}
    data = None
    if token:
        h["authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body).encode()
        h["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    for _ in range(60):
        try:
            if call("GET", base + "/api/health")[0] == 200:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)

    call("POST", base + "/api/auth/register",
         {"email": ADMIN_EMAIL, "password": ADMIN_PW, "full_name": "Admin Example"})
    # Login form-encoded.
    import urllib.parse
    data = urllib.parse.urlencode({"username": ADMIN_EMAIL, "password": ADMIN_PW}).encode()
    req = urllib.request.Request(base + "/api/auth/token", data=data, method="POST",
                                 headers={"content-type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        token = json.load(resp)["access_token"]

    st, bd = call("POST", base + "/api/family",
                  {"full_name": MEMBER, "authorized": True, "age": 41}, token=token)
    if st != 201:
        print("could not add member:", st, bd)
        return 1
    mid = json.loads(bd)["id"]
    for kind, value in IDENTITIES:
        call("POST", f"{base}/api/identity/{mid}",
             {"kind": kind, "value": value}, token=token)
    print(f"Seeded: admin {ADMIN_EMAIL}, member '{MEMBER}' (id {mid}) "
          f"with {len(IDENTITIES)} identity fields.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
