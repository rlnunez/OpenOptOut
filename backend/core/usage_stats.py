"""
Usage statistics web service: counts a library's own scripts can pull into
a data mart such as LibInsight, a data warehouse or a data lake.

  GET /api/stats/v1/status          public: is the service on
  GET /api/stats/v1/institutions    the institutions this key may see
  GET /api/stats/v1/metrics         what each count means
  GET /api/stats/v1/usage           counts for a date range

Every path but /status needs a key, sent as "Authorization: Bearer <key>".
Keys are made on Admin → Usage statistics, shown once, and only their hash is
kept. A key can be limited to some institutions.

/usage parameters:
  from, to      dates, yyyy-mm-dd, inclusive (to may be today; today's numbers
                are marked complete=false)
  granularity   day | week (starting Monday) | month | total   (default day)
  institution   an institution id, several separated by commas, or * for every
                one the key may see (default all)
  metrics       comma-separated metric names (default all)
  format        json | csv   (default json)

Every period in the range gets a row, with zeros, so loading is simple. Dates
are UTC days. Counts only: never a name or a detail about anyone.

Institutions: "all" is the whole server, a library system's code is that
system, and "<system>-<branch>" is one branch. A person counts for the branch
of their account; people a parent adds count for the parent's branch.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import re
import secrets
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

VERSION = 1
DEFAULTS = {"enabled": False, "clients": []}
METRICS = {
    "people_added": "People whose details were added.",
    "listing_searches": "A person's listings looked for on one broker on one day.",
    "listings_found": "A person found on a broker for the first time.",
    "optout_requests_sent": "Opt-out requests sent. A request sent again counts on its latest date.",
    "removals_confirmed": "Removals confirmed.",
}
GRANULARITIES = ("day", "week", "month", "total")
MAX_DAYS_DAILY = 1100           # about three years of daily rows per request
MAX_DAYS = 3660                 # about ten years for week, month and total
KEY = re.compile(r"^oos_([0-9a-f]{12})_([A-Za-z0-9_-]{20,})$")


class StatsError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message

    def body(self) -> dict:
        return {"error": self.code, "message": self.message}


def config(settings: Optional[dict] = None) -> dict:
    if settings is None:
        from .settings_store import load_settings
        settings = load_settings()
    out = dict(DEFAULTS)
    out.update(settings.get("stats_api") or {})
    out["clients"] = list(out.get("clients") or [])
    return out


# ── Institutions ──────────────────────────────────────────────────────────────

def institutions(db) -> List[dict]:
    """{"id", "name", "type", "parent", "branch_ids"} (branch_ids None = whole server)."""
    from ..models.database import LibrarySystem
    from .terms import config as terms_config
    whole = terms_config().get("operator") or "OpenOptOut"
    out = [{"id": "all", "name": whole, "type": "server", "parent": None, "branch_ids": None}]
    for s in db.query(LibrarySystem).order_by(LibrarySystem.name).all():
        out.append({"id": s.code, "name": s.name, "type": "system", "parent": "all",
                    "branch_ids": {b.id for b in s.branches}})
        for b in sorted(s.branches, key=lambda b: b.name):
            out.append({"id": f"{s.code}-{b.code}", "name": b.name, "type": "branch", "parent": s.code,
                        "branch_ids": {b.id}})
    return out


def public_institution(i: dict) -> dict:
    return {k: i[k] for k in ("id", "name", "type", "parent")}


# ── Keys ──────────────────────────────────────────────────────────────────────

def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_client(cfg: dict, name: str, allowed: List[str]) -> Tuple[dict, str]:
    """A client's key: "oos_<id>_<secret>". Shown once; only the hash is kept."""
    name = (name or "").strip()[:100]
    if not name:
        raise ValueError("Give the key a name, like the script or system that will use it.")
    allowed = [a for a in (allowed or ["*"]) if a] or ["*"]
    cid, secret = secrets.token_hex(6), secrets.token_urlsafe(32)
    c = {"id": cid, "name": name, "key_hash": _hash(secret), "institutions": allowed,
         "created_at": datetime.utcnow().isoformat(timespec="seconds"), "last_used": ""}
    cfg["clients"].append(c)
    return c, f"oos_{cid}_{secret}"


def public_client(c: dict) -> dict:
    return {k: c.get(k) for k in ("id", "name", "institutions", "created_at", "last_used")}


def authorize(cfg: dict, authorization: str) -> dict:
    token = authorization[7:].strip() if (authorization or "").lower().startswith("bearer ") else ""
    if not token:
        raise StatsError(401, "unauthorized", "Send the key as: Authorization: Bearer <key>.")
    m = KEY.match(token)
    c = next((c for c in cfg["clients"] if m and c["id"] == m.group(1)), None)
    if c is None or not hmac.compare_digest(c["key_hash"], _hash(m.group(2))):
        raise StatsError(401, "unauthorized", "That key isn't valid. Make a new one on Admin → Usage statistics.")
    return c


def allowed_institutions(db, client: dict) -> List[dict]:
    return [i for i in institutions(db) if "*" in client["institutions"] or i["id"] in client["institutions"]]


# ── Counting ──────────────────────────────────────────────────────────────────

def events(db, branch_ids, start: datetime, stop: datetime):
    """(metric, when) for everything counted between start and stop, for the
    people in these branches (None = everyone). Ids, dates and counts only."""
    from ..models.database import User, FamilyMember, DiscoveryResult, RemovalRequest
    q = db.query(FamilyMember.id, User.created_at).join(User, User.id == FamilyMember.user_id)
    if branch_ids is not None:
        if not branch_ids:
            return
        q = q.filter(User.branch_id.in_(list(branch_ids)))
    people = q.all()
    for _, created in people:
        if created and start <= created < stop:
            yield "people_added", created
    ids = [p[0] for p in people]
    for chunk in (ids[i:i + 500] for i in range(0, len(ids), 500)):
        seen = set()
        for mid, bid, at in (db.query(DiscoveryResult.member_id, DiscoveryResult.broker_id, DiscoveryResult.scanned_at)
                               .filter(DiscoveryResult.member_id.in_(chunk), DiscoveryResult.scanned_at >= start,
                                       DiscoveryResult.scanned_at < stop).all()):
            if (mid, bid, at.date()) not in seen:
                seen.add((mid, bid, at.date()))
                yield "listing_searches", at
        first = {}
        for mid, bid, at in (db.query(DiscoveryResult.member_id, DiscoveryResult.broker_id, DiscoveryResult.scanned_at)
                               .filter(DiscoveryResult.member_id.in_(chunk), DiscoveryResult.found.is_(True)).all()):
            if at and ((mid, bid) not in first or at < first[(mid, bid)]):
                first[(mid, bid)] = at
        for at in first.values():
            if start <= at < stop:
                yield "listings_found", at
        for sent, confirmed in (db.query(RemovalRequest.sent_at, RemovalRequest.confirmed_at)
                                  .filter(RemovalRequest.member_id.in_(chunk)).all()):
            if sent and start <= sent < stop:
                yield "optout_requests_sent", sent
            if confirmed and start <= confirmed < stop:
                yield "removals_confirmed", confirmed


def _period_start(d: date, granularity: str, begin: date) -> date:
    if granularity == "day":
        return d
    if granularity == "week":
        return d - timedelta(days=d.weekday())
    if granularity == "month":
        return d.replace(day=1)
    return begin


def _periods(begin: date, end: date, granularity: str) -> List[Tuple[date, date]]:
    """(start, end) of each period touching begin..end, clipped to the range."""
    if granularity == "total":
        return [(begin, end)]
    out, d = [], _period_start(begin, granularity, begin)
    while d <= end:
        if granularity == "day":
            nxt = d + timedelta(days=1)
        elif granularity == "week":
            nxt = d + timedelta(days=7)
        else:
            nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((max(d, begin), min(nxt - timedelta(days=1), end)))
        d = nxt
    return out


def usage(db, inst: dict, begin: date, end: date, granularity: str, metrics: List[str],
          today: Optional[date] = None) -> List[dict]:
    today = today or datetime.utcnow().date()
    periods = _periods(begin, end, granularity)
    index = {p[0]: i for i, p in enumerate(periods)}
    counts = [{m: 0 for m in metrics} for _ in periods]
    start = datetime.combine(begin, datetime.min.time())
    stop = datetime.combine(end + timedelta(days=1), datetime.min.time())
    for metric, when in events(db, inst["branch_ids"], start, stop):
        if metric in metrics:
            p = max(_period_start(when.date(), granularity, begin), begin)
            counts[index[p]][metric] += 1
    return [{"institution": inst["id"], "period_start": s.isoformat(), "period_end": e.isoformat(),
             "complete": e < today, **c} for (s, e), c in zip(periods, counts)]


# ── The API ───────────────────────────────────────────────────────────────────

def _date(value: str, name: str) -> date:
    try:
        return datetime.strptime(value or "", "%Y-%m-%d").date()
    except ValueError:
        raise StatsError(400, "bad_request", f"{name} must be a date like 2026-09-30.")


def handle(db, path: str, params: dict, authorization: str = "", cfg: Optional[dict] = None,
           today: Optional[date] = None) -> Tuple[int, object, str]:
    """Answer one request. Returns (HTTP status, body, media type). Never raises."""
    cfg = cfg if cfg is not None else config()
    today = today or datetime.utcnow().date()
    path = "/" + path.strip("/")
    try:
        if path == "/v1/status":
            return 200, {"service": "OpenOptOut usage statistics", "version": VERSION,
                         "enabled": bool(cfg["enabled"])}, "application/json"
        if path not in ("/v1/institutions", "/v1/metrics", "/v1/usage"):
            raise StatsError(404, "not_found", "Paths: /v1/status, /v1/institutions, /v1/metrics, /v1/usage.")
        if not cfg["enabled"]:
            raise StatsError(503, "off", "Usage statistics are turned off on this server.")
        client = authorize(cfg, authorization)
        allowed = allowed_institutions(db, client)
        if path == "/v1/institutions":
            return 200, {"institutions": [public_institution(i) for i in allowed]}, "application/json"
        if path == "/v1/metrics":
            return 200, {"metrics": [{"name": k, "description": v} for k, v in METRICS.items()]}, "application/json"
        return _usage(db, params, allowed, today)
    except StatsError as e:
        return e.status, e.body(), "application/json"
    except Exception as e:                   # never a traceback to a client
        import logging
        logging.getLogger(__name__).warning("usage statistics request failed: %s", type(e).__name__)
        return 500, {"error": "server_error", "message": "Something went wrong. Try again later."}, "application/json"


def _usage(db, params: dict, allowed: List[dict], today: date):
    known = {"from", "to", "granularity", "institution", "metrics", "format"}
    extra = sorted(set(params) - known)
    if extra:
        raise StatsError(400, "bad_request", f"Unknown parameter: {', '.join(extra)}.")
    begin, end = _date(params.get("from", ""), "from"), _date(params.get("to", ""), "to")
    if end < begin:
        raise StatsError(400, "bad_request", "to is before from.")
    if end > today:
        raise StatsError(400, "bad_request", "to is in the future.")
    granularity = params.get("granularity") or "day"
    if granularity not in GRANULARITIES:
        raise StatsError(400, "bad_request", "granularity must be day, week, month or total.")
    span = (end - begin).days + 1
    if span > (MAX_DAYS_DAILY if granularity == "day" else MAX_DAYS):
        raise StatsError(400, "bad_request", "That range is too long. Ask for at most about three years of days, "
                                             "or ten years of weeks or months.")
    metrics = [m for m in (params.get("metrics") or "").split(",") if m] or list(METRICS)
    bad = [m for m in metrics if m not in METRICS]
    if bad:
        raise StatsError(400, "bad_request", f"Unknown metric: {', '.join(bad)}. See /v1/metrics.")
    fmt = params.get("format") or "json"
    if fmt not in ("json", "csv"):
        raise StatsError(400, "bad_request", "format must be json or csv.")
    want = [w.strip() for w in (params.get("institution") or "all").split(",") if w.strip()]
    by_id = {i["id"].lower(): i for i in allowed}
    if want == ["*"]:
        chosen = allowed
    else:
        chosen = []
        for w in want:
            if w.lower() not in by_id:
                raise StatsError(403, "forbidden", f"This key can't see the institution {w!r}. See /v1/institutions.")
            chosen.append(by_id[w.lower()])
    rows = []
    for inst in chosen:
        rows += usage(db, inst, begin, end, granularity, metrics, today)
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        cols = ["institution", "period_start", "period_end", "complete"] + metrics
        w.writerow(cols)
        for r in rows:
            w.writerow([str(r[c]).lower() if isinstance(r[c], bool) else r[c] for c in cols])
        return 200, buf.getvalue(), "text/csv"
    return 200, {"from": begin.isoformat(), "to": end.isoformat(), "granularity": granularity, "timezone": "UTC",
                 "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                 "metrics": metrics, "institutions": [public_institution(i) for i in chosen], "rows": rows}, \
        "application/json"
