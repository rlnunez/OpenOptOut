#!/usr/bin/env python3
# ==============================================================================
# OpenOptOut — SUSHI / COUNTER API harvest tester
# ==============================================================================
"""
Collect usage statistics from a COUNTER API (SUSHI) server the way a library's
harvester would, and check every answer. Standard library only.

    python3 scripts/sushi-harvest-test.py https://optout.example.org/api/sushi \\
        --requestor-id oo-1234abcd --api-key 'the key shown once' [--customer all]

Make the requestor ID and key under Admin → Usage statistics → Add a harvester.
Exit code 0 when every check passes. --save DIR writes each report it
collected, to upload to the COUNTER Validator (counter-validator.readthedocs.io)
for an independent check.
"""
import argparse
import importlib.util
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "sushi_check", os.path.join(HERE, "..", "backend", "core", "sushi_check.py"))
sushi_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sushi_check)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="the SUSHI base address, ending in /api/sushi")
    ap.add_argument("--requestor-id", required=True)
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--customer", default="all", help="customer ID (default: all)")
    ap.add_argument("--insecure", action="store_true", help="don't check the TLS certificate (test servers only)")
    ap.add_argument("--save", metavar="DIR", help="save each report collected as JSON")
    a = ap.parse_args()

    base = a.base.rstrip("/")
    if base.endswith("/r51"):
        base = base[:-4]
    if not base.startswith("https://"):
        print("Note: the COUNTER API must be served over HTTPS. Testing anyway.\n")
    ctx = ssl._create_unverified_context() if a.insecure else ssl.create_default_context()
    saved = []

    def get(path, params):
        url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                   "User-Agent": "OpenOptOut-SUSHI-tester/1"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        except urllib.error.URLError as e:
            print(f"Can't reach {base}: {e.reason}")
            sys.exit(2)
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            body = None
        if a.save and status == 200 and isinstance(body, dict) and "Report_Header" in body:
            os.makedirs(a.save, exist_ok=True)
            name = os.path.join(a.save, body["Report_Header"].get("Report_ID", "report").replace(":", "_") + ".json")
            if name not in saved:
                with open(name, "w", encoding="utf-8") as f:
                    json.dump(body, f, indent=1, ensure_ascii=False)
                saved.append(name)
        return status, body

    results = sushi_check.run(get, a.requestor_id, a.api_key, a.customer)
    width = max(len(sushi_check.text(r)) for r in results)
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"  [{mark}] {sushi_check.text(r):<{width}}  {r['detail']}")
    failed = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed.")
    if saved:
        print("Saved for the COUNTER Validator: " + ", ".join(saved))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
