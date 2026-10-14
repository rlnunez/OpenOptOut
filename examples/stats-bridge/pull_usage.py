#!/usr/bin/env python3
"""
Example bridge: pull OpenOptOut's usage statistics and save them where your
own tools can load them (a data mart such as LibInsight, a data warehouse, a data lake).

Copy this script and change load() for your destination. Standard library only.

    export OPENOPTOUT_STATS_KEY='oos_…'          # from Admin → Usage statistics
    python3 pull_usage.py https://optout.example.org/api/stats --out ./usage

Each run collects every complete day since the last run (yesterday on the
first run), for every institution the key may see, one row per institution
per day, and remembers where it got to in ./usage/state.json. Run it daily
from cron or Task Scheduler. Use --from/--to to backfill a range, and
--granularity total for one row per institution for the whole range.

Re-running a day is safe: the rows carry institution + period_start, so load
them with an upsert (or delete-then-insert) on those two columns.
"""
import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta


def fetch(base, key, params):
    url = base.rstrip("/") + "/v1/usage?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}",
                                               "User-Agent": "openoptout-stats-bridge/1"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"OpenOptOut answered {e.code}: {body}")


def load(rows, out_dir, begin, end):
    """Change this for your destination. As shipped, it writes one CSV and one
    JSON Lines file per run.

    LibInsight: post the rows to your custom dataset's add-records address
    (Admin → Widgets & API in LibInsight), mapping each metric to one of the
    dataset's fields. Warehouse or lake: copy the CSV, or upsert the rows on
    (institution, period_start)."""
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, f"usage_{begin}_{end}")
    if rows:
        with open(stem + ".csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    with open(stem + ".jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"Saved {len(rows)} rows to {stem}.csv and .jsonl")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="the API's base address, ending in /api/stats")
    ap.add_argument("--out", default="usage", help="folder for the files and state.json")
    ap.add_argument("--from", dest="begin", help="first day, yyyy-mm-dd (default: the day after the last run)")
    ap.add_argument("--to", dest="end", help="last day, yyyy-mm-dd (default: yesterday)")
    ap.add_argument("--granularity", default="day", choices=["day", "week", "month", "total"])
    ap.add_argument("--institution", default="*", help="an institution id, several with commas, or * (default)")
    a = ap.parse_args()
    key = os.environ.get("OPENOPTOUT_STATS_KEY")
    if not key:
        sys.exit("Set OPENOPTOUT_STATS_KEY to the key from Admin → Usage statistics.")

    state_file = os.path.join(a.out, "state.json")
    state = {}
    if os.path.exists(state_file):
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
    yesterday = date.today() - timedelta(days=1)
    end = date.fromisoformat(a.end) if a.end else yesterday
    if a.begin:
        begin = date.fromisoformat(a.begin)
    elif state.get("last_day"):
        begin = date.fromisoformat(state["last_day"]) + timedelta(days=1)
    else:
        begin = yesterday
    if begin > end:
        print("Nothing new to collect.")
        return

    # Ask in pieces of at most a year, so long backfills stay within the API's limits.
    rows, d = [], begin
    while d <= end:
        piece_end = min(end, d + timedelta(days=364))
        body = fetch(a.base, key, {"from": d.isoformat(), "to": piece_end.isoformat(),
                                   "granularity": a.granularity, "institution": a.institution})
        rows += body["rows"]
        d = piece_end + timedelta(days=1)
    load(rows, a.out, begin.isoformat(), end.isoformat())

    if not a.begin and not a.end:
        os.makedirs(a.out, exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({"last_day": end.isoformat()}, f)


if __name__ == "__main__":
    main()
