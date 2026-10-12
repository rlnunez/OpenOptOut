#!/usr/bin/env python3
# ==============================================================================
# OpenOptOut — usage statistics API tester
# ==============================================================================
"""
Check a server's usage statistics API the way a client script uses it.
Standard library only.

    OPENOPTOUT_STATS_KEY='oos_…' python3 scripts/stats-api-test.py https://optout.example.org/api/stats

Make the key under Admin → Usage statistics → Make a key. Exit code 0 when
every check passes.
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
    "stats_check", os.path.join(HERE, "..", "backend", "core", "stats_check.py"))
stats_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats_check)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="the API's base address, ending in /api/stats")
    ap.add_argument("--key", default=os.environ.get("OPENOPTOUT_STATS_KEY", ""),
                    help="the key (or set OPENOPTOUT_STATS_KEY, so it isn't in your shell history)")
    ap.add_argument("--insecure", action="store_true", help="don't check the TLS certificate (test servers only)")
    a = ap.parse_args()
    if not a.key:
        ap.error("give the key with --key or OPENOPTOUT_STATS_KEY")
    base = a.base.rstrip("/")
    if not base.startswith("https://"):
        print("Note: use HTTPS outside a test setup; the key travels with every request.\n")
    ctx = ssl._create_unverified_context() if a.insecure else ssl.create_default_context()

    def get(path, params, key):
        url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {"User-Agent": "OpenOptOut-stats-tester/1"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60, context=ctx) as r:
                status, raw, ctype = r.status, r.read(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            status, raw, ctype = e.code, e.read(), e.headers.get("Content-Type", "")
        except urllib.error.URLError as e:
            print(f"Can't reach {base}: {e.reason}")
            sys.exit(2)
        text = raw.decode("utf-8", "replace")
        if "csv" in ctype:
            return status, text
        try:
            return status, json.loads(text)
        except ValueError:
            return status, None

    results = stats_check.run(get, a.key)
    width = max(len(stats_check.text(r)) for r in results)
    for r in results:
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {stats_check.text(r):<{width}}  {r['detail']}")
    failed = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
