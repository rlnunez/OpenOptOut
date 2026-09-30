#!/usr/bin/env python3
"""Prepare a throwaway OpenOptOut API for dynamic (DAST) scanning.

  1. waits for /api/health to answer
  2. creates the first account (which becomes super admin) with random,
     throwaway credentials
  3. logs in and writes the bearer token to --token-file
  4. saves the OpenAPI schema to --schema-file

Only ever point this at a disposable CI instance: it creates an admin account.
Standard library only, so it runs in any Python container.
"""
import argparse
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def call(method, url, data=None, headers=None, timeout=15):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url", help="e.g. http://api:8000")
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--schema-file", required=True)
    ap.add_argument("--wait-seconds", type=int, default=300)
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    # 1. Wait for the API to come up
    deadline = time.time() + args.wait_seconds
    last_err = None
    while time.time() < deadline:
        try:
            status, body = call("GET", f"{base}/api/health", timeout=5)
            if status == 200:
                print(f"API is up: {body.decode()[:200]}")
                break
        except Exception as e:  # noqa: BLE001 — any failure just means "not up yet"
            last_err = e
        time.sleep(3)
    else:
        print(f"::error::API did not become healthy within {args.wait_seconds}s "
              f"(last error: {last_err}). Check the 'API container logs' step.")
        return 1

    # 2. Create the first (super admin) account with throwaway credentials
    email = f"dast-admin-{secrets.token_hex(4)}@example.com"
    password = secrets.token_urlsafe(24)
    payload = json.dumps({"email": email, "password": password,
                          "full_name": "DAST Scanner"}).encode()
    try:
        status, _ = call("POST", f"{base}/api/auth/register", payload,
                         {"Content-Type": "application/json"})
        print(f"Registered scan account ({status})")
    except urllib.error.HTTPError as e:
        print(f"::error::Could not register the scan account: HTTP {e.code} "
              f"{e.read().decode()[:300]}")
        return 1

    # 3. Log in (OAuth2 password form)
    form = urllib.parse.urlencode({"username": email, "password": password}).encode()
    try:
        _, body = call("POST", f"{base}/api/auth/token", form,
                       {"Content-Type": "application/x-www-form-urlencoded"})
    except urllib.error.HTTPError as e:
        print(f"::error::Login failed: HTTP {e.code} {e.read().decode()[:300]}")
        return 1
    token = json.loads(body)["access_token"]
    with open(args.token_file, "w") as f:
        f.write(token)
    print("Logged in; token saved.")

    # Sanity check: the token actually works
    call("GET", f"{base}/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    # 4. Save the OpenAPI schema (used by Schemathesis and ZAP, and kept as an artifact)
    _, schema = call("GET", f"{base}/openapi.json")
    with open(args.schema_file, "wb") as f:
        f.write(schema)
    ops = sum(len(v) for v in json.loads(schema).get("paths", {}).values())
    print(f"OpenAPI schema saved: {ops} operations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
