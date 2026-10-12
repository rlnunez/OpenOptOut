"""
Checks for the usage statistics web service, as a client script sees it. Used
by the "Run the self-test" button (Admin → Usage statistics) and by
scripts/stats-api-test.py, which points them at any server.

Standard library only, and no imports from the app, so the script can load
this file on its own.

run(get, key, today) -> [{"key", "ok", "detail", "vars"}]
where get(path, params, key) -> (http_status, body), body being parsed JSON,
or text for CSV. path is relative to the base address ("/v1/status").
"""
import csv
import io
from datetime import date, timedelta

# Every check, in the reader's words (scripts/extract_page_texts.py reads this).
CHECK_TEXTS = {
    "status_public": "The status answers without a key",
    "no_key": "A request without a key is refused (401)",
    "bad_key": "A wrong key is refused (401)",
    "institutions": "Institutions are listed",
    "metrics": "All five metrics are described",
    "daily": "Daily counts have one row per day, zeros included",
    "monthly_matches_daily": "Monthly totals match the daily counts",
    "weekly": "Weeks start on Monday",
    "total": "A total for the whole range matches the daily counts",
    "csv": "CSV has a header and the same rows as JSON",
    "today_incomplete": "Today's numbers are marked as not complete",
    "bad_range": "Dates the wrong way round are refused (400)",
    "future": "A date in the future is refused (400)",
    "bad_metric": "An unknown metric is refused (400)",
    "bad_institution": "An institution the key can't see is refused (403)",
}
METRICS = ("people_added", "listing_searches", "listings_found", "optout_requests_sent", "removals_confirmed")


def run(get, key, today=None):
    today = today or date.today()
    out = []

    def add(name, ok, detail=""):
        out.append({"key": name, "ok": bool(ok), "detail": detail, "vars": {}})

    st, body = get("/v1/status", {}, None)
    add("status_public", st == 200 and isinstance(body, dict) and "enabled" in body,
        f"HTTP {st}" + (f", enabled={body.get('enabled')}" if isinstance(body, dict) else ""))
    st, body = get("/v1/institutions", {}, None)
    add("no_key", st == 401, f"HTTP {st}")
    st, body = get("/v1/institutions", {}, key[:-4] + "XXXX" if key else "nope")
    add("bad_key", st == 401, f"HTTP {st}")

    st, body = get("/v1/institutions", {}, key)
    insts = body.get("institutions", []) if isinstance(body, dict) else []
    add("institutions", st == 200 and insts and all({"id", "name", "type"} <= set(i) for i in insts),
        f"HTTP {st}, {len(insts)} institution(s)")
    inst = insts[0]["id"] if insts else "all"

    st, body = get("/v1/metrics", {}, key)
    names = [m.get("name") for m in body.get("metrics", [])] if isinstance(body, dict) else []
    add("metrics", st == 200 and all(m in names for m in METRICS), f"HTTP {st}: {', '.join(map(str, names))}")

    # Two whole months before this one, by day, month and total.
    first = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    first = (first - timedelta(days=1)).replace(day=1)
    last = today.replace(day=1) - timedelta(days=1)
    rng = {"from": first.isoformat(), "to": last.isoformat(), "institution": inst}
    st, daily = get("/v1/usage", dict(rng, granularity="day"), key)
    rows = daily.get("rows", []) if isinstance(daily, dict) else []
    days = (last - first).days + 1
    ok = (st == 200 and len(rows) == days and all(all(m in r for m in METRICS) for r in rows)
          and [r["period_start"] for r in rows] == [(first + timedelta(days=i)).isoformat() for i in range(days)])
    add("daily", ok, f"HTTP {st}, {len(rows)} rows for {days} days")
    sums = {m: sum(r.get(m, 0) for r in rows) for m in METRICS}

    st, monthly = get("/v1/usage", dict(rng, granularity="month"), key)
    mrows = monthly.get("rows", []) if isinstance(monthly, dict) else []
    msums = {m: sum(r.get(m, 0) for r in mrows) for m in METRICS}
    add("monthly_matches_daily", st == 200 and len(mrows) == 2 and msums == sums,
        f"HTTP {st}, {len(mrows)} rows; daily {sums}; monthly {msums}" if msums != sums else f"HTTP {st}, {len(mrows)} rows")

    st, weekly = get("/v1/usage", dict(rng, granularity="week"), key)
    wrows = weekly.get("rows", []) if isinstance(weekly, dict) else []
    starts = [date.fromisoformat(r["period_start"]) for r in wrows[1:]]
    add("weekly", st == 200 and wrows and all(d.weekday() == 0 for d in starts)
        and {m: sum(r.get(m, 0) for r in wrows) for m in METRICS} == sums, f"HTTP {st}, {len(wrows)} rows")

    st, total = get("/v1/usage", dict(rng, granularity="total"), key)
    trows = total.get("rows", []) if isinstance(total, dict) else []
    add("total", st == 200 and len(trows) == 1 and {m: trows[0].get(m, 0) for m in METRICS} == sums, f"HTTP {st}")

    st, text = get("/v1/usage", dict(rng, granularity="day", format="csv"), key)
    try:
        table = list(csv.reader(io.StringIO(text))) if isinstance(text, str) else []
    except csv.Error:
        table = []
    ok = (st == 200 and table and table[0][:4] == ["institution", "period_start", "period_end", "complete"]
          and len(table) - 1 == len(rows))
    add("csv", ok, f"HTTP {st}, {max(len(table) - 1, 0)} rows")

    st, body = get("/v1/usage", {"from": today.isoformat(), "to": today.isoformat(), "institution": inst}, key)
    r = body.get("rows", [{}]) if isinstance(body, dict) else [{}]
    add("today_incomplete", st == 200 and r and r[0].get("complete") is False, f"HTTP {st}")

    st, _ = get("/v1/usage", {"from": last.isoformat(), "to": first.isoformat()}, key)
    add("bad_range", st == 400, f"HTTP {st}")
    st, _ = get("/v1/usage", {"from": today.isoformat(), "to": (today + timedelta(days=2)).isoformat()}, key)
    add("future", st == 400, f"HTTP {st}")
    st, _ = get("/v1/usage", dict(rng, metrics="favourite_colour"), key)
    add("bad_metric", st == 400, f"HTTP {st}")
    st, _ = get("/v1/usage", dict(rng, institution="no-such-institution"), key)
    add("bad_institution", st == 403, f"HTTP {st}")
    return out


def text(result):
    return CHECK_TEXTS[result["key"]].format(**result.get("vars") or {})
