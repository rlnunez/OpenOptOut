"""
Usage statistics for libraries and universities, over the COUNTER API
(SUSHI), Release 5.1.

Library and campus systems (ERMs, Celus, Alma Analytics and the like) harvest
monthly usage from the services they offer. This makes OpenOptOut one of them:

  GET {base}/r51/status              public: is the service up
  GET {base}/r51/members             the institutions this harvester may see
  GET {base}/r51/reports             the reports offered, with the months available
  GET {base}/r51/reports/pr          Platform Report (standard)
  GET {base}/r51/reports/pr_p1       Platform Usage (standard view)
  GET {base}/r51/reports/{ns}:oo1    OpenOptOut Usage (a custom report)

{base} is https://<server>/api/sushi. Every path but /status needs the
harvester's requestor_id and api_key (made on Admin → Usage statistics), and
reports need a customer_id: "all" for the whole server, a library system's
code, or "<system>-<branch>" for a branch.

What's counted, per month (counts only; never names or details):

  Listing_Searches      a person's listings looked for on one broker on one day
                        (also reported as the standard Searches_Platform)
  People_Added          people whose details were added
  Listings_Found        a person found on a broker for the first time
  Optout_Requests_Sent  opt-out requests sent (a re-sent request counts in its latest month)
  Removals_Confirmed    removals confirmed

A person belongs to the branch of their account; people added by a parent
belong to the parent's branch. This is SUSHI-compatible, not COUNTER-audited:
OpenOptOut doesn't serve journals or books, so it isn't in the COUNTER Registry
and its namespace isn't registered. Error codes and messages follow Appendix D
of the Code of Practice.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

RELEASE = "5.1"
DEFAULTS = {"enabled": False, "platform": "OpenOptOut", "namespace": "OpenOptOut",
            "registry_record": "", "harvesters": []}
NAMESPACE = re.compile(r"^[A-Za-z0-9_./]{1,17}$")
WORLD = "0000000000000000"

# Appendix D, Table D.1: exact messages and HTTP statuses.
EXC = {
    1000: ("Service Not Available", 503),
    1030: ("Insufficient Information to Process Request", 400),
    2000: ("Requestor Not Authorized to Access Service", 401),
    2010: ("Requestor is Not Authorized to Access Usage for Institution", 403),
    2011: ("Global Reports Not Supported", 403),
    2020: ("APIKey Invalid", 401),
    3000: ("Report Not Supported", 404),
    3020: ("Invalid Date Arguments", 400),
    3030: ("No Usage Available for Requested Dates", 200),
    3031: ("Usage Not Ready for Requested Dates", 200),
    3050: ("Parameter Not Recognized in this Context", 200),
    3060: ("Invalid ReportFilter Value", 200),
    3062: ("Invalid ReportAttribute Value", 200),
}

# Internal counts -> what each report calls them.
CUSTOM_METRICS = ("People_Added", "Listing_Searches", "Listings_Found", "Optout_Requests_Sent", "Removals_Confirmed")


def config(settings: Optional[dict] = None) -> dict:
    if settings is None:
        from .settings_store import load_settings
        settings = load_settings()
    out = dict(DEFAULTS)
    out.update(settings.get("sushi") or {})
    out["harvesters"] = list(out.get("harvesters") or [])
    if not NAMESPACE.match(out.get("namespace") or ""):
        out["namespace"] = DEFAULTS["namespace"]
    return out


def exception(code: int, data: str = "") -> dict:
    e = {"Code": code, "Message": EXC[code][0]}
    if data:
        e["Data"] = data
    return e


def _fatal(code: int, data: str = "") -> Tuple[int, dict]:
    return EXC[code][1], exception(code, data)


# ── Reports offered ───────────────────────────────────────────────────────────

def reports(cfg: dict) -> Dict[str, dict]:
    """Lower-case path id -> {id, name, description, metrics}."""
    ns = cfg["namespace"]
    return {
        "pr": {"id": "PR", "name": "Platform Report", "metrics": ("Searches_Platform",),
               "description": "Searches for people's listings on data-broker sites (Searches_Platform)."},
        "pr_p1": {"id": "PR_P1", "name": "Platform Usage", "metrics": ("Searches_Platform",),
                  "description": "Standard view of the Platform Report: searches for listings."},
        f"{ns.lower()}:oo1": {"id": f"{ns}:OO1", "name": f"{ns}:OpenOptOut Usage",
                              "metrics": tuple(f"{ns}:{m}" for m in CUSTOM_METRICS),
                              "description": "People added, listing searches, listings found, opt-out requests "
                                             "sent and removals confirmed."},
    }


# ── Institutions ──────────────────────────────────────────────────────────────

def customers(db, cfg: dict) -> List[dict]:
    """Every institution a harvester can ask about: {"id", "name", "branch_ids"}
    (None = the whole server)."""
    from ..models.database import LibrarySystem
    from .terms import config as terms_config
    whole = terms_config().get("operator") or cfg.get("platform") or "OpenOptOut"
    out = [{"id": "all", "name": whole, "branch_ids": None}]
    for s in db.query(LibrarySystem).order_by(LibrarySystem.name).all():
        out.append({"id": s.code, "name": s.name, "branch_ids": {b.id for b in s.branches}})
        for b in sorted(s.branches, key=lambda b: b.name):
            out.append({"id": f"{s.code}-{b.code}", "name": f"{s.name}: {b.name}", "branch_ids": {b.id}})
    return out


# ── Credentials ───────────────────────────────────────────────────────────────

def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_harvester(cfg: dict, name: str, allowed: List[str]) -> Tuple[dict, str]:
    """A harvester's credentials. The API key is shown once; only its hash is kept."""
    name = (name or "").strip()[:100]
    if not name:
        raise ValueError("Give the harvester a name, like the system that will collect the reports.")
    allowed = [a for a in (allowed or ["*"]) if a] or ["*"]
    key = secrets.token_urlsafe(32)
    h = {"id": secrets.token_hex(6), "name": name, "requestor_id": "oo-" + secrets.token_hex(8),
         "key_hash": _hash(key), "customers": allowed,
         "created_at": datetime.utcnow().isoformat(timespec="seconds"), "last_used": ""}
    cfg["harvesters"].append(h)
    return h, key


def public_harvester(h: dict) -> dict:
    return {k: h.get(k) for k in ("id", "name", "requestor_id", "customers", "created_at", "last_used")}


def _authorize(cfg: dict, params: dict) -> Tuple[Optional[dict], Optional[Tuple[int, dict]]]:
    rid, key = params.get("requestor_id") or "", params.get("api_key") or ""
    if not rid or not key:
        return None, _fatal(1030, "requestor_id and api_key are required")
    h = next((h for h in cfg["harvesters"] if hmac.compare_digest(h["requestor_id"], rid)), None)
    if h is None:
        return None, _fatal(2000)
    if not hmac.compare_digest(h["key_hash"], _hash(key)):
        return None, _fatal(2020)
    return h, None


def _customer(db, cfg: dict, h: dict, params: dict):
    cid = params.get("customer_id") or ""
    if not cid:
        return None, _fatal(1030, "customer_id is required")
    if cid == WORLD:
        return None, _fatal(2011)
    c = next((c for c in customers(db, cfg) if c["id"].lower() == cid.lower()), None)
    if c is None or ("*" not in h["customers"] and c["id"] not in h["customers"]):
        return None, _fatal(2010)
    return c, None


# ── Months ────────────────────────────────────────────────────────────────────

def _month(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _add_months(d: date, n: int) -> date:
    m = d.year * 12 + d.month - 1 + n
    return date(m // 12, m % 12 + 1, 1)


def _last_day(d: date) -> date:
    return _add_months(d, 1) - timedelta(days=1)


def _parse(s: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(s, fmt).date().replace(day=1)
        except (ValueError, TypeError):
            pass
    return None


def months_available(db, now: Optional[datetime] = None) -> Tuple[Optional[date], date]:
    """(first, last) months with data: from the first account to the last
    complete month."""
    from sqlalchemy import func
    from ..models.database import User
    now = now or datetime.utcnow()
    last = _add_months(now.date().replace(day=1), -1)
    first = db.query(func.min(User.created_at)).scalar()
    first = first.date().replace(day=1) if first else None
    if first and first > last:
        first = last
    return first, last


# ── Counting ──────────────────────────────────────────────────────────────────

def counts(db, branch_ids, begin: date, end: date) -> Dict[str, Dict[str, int]]:
    """{metric: {"YYYY-MM": n}} for the people in these branches (None = all),
    months begin..end inclusive. Zero months are left out."""
    from ..models.database import User, FamilyMember, DiscoveryResult, RemovalRequest
    start = datetime(begin.year, begin.month, 1)
    stop = datetime.combine(_add_months(end, 1), datetime.min.time())
    q = db.query(FamilyMember.id, User.created_at).join(User, User.id == FamilyMember.user_id)
    if branch_ids is not None:
        if not branch_ids:
            return {}
        q = q.filter(User.branch_id.in_(list(branch_ids)))
    people = q.all()
    ids = [p[0] for p in people]
    out: Dict[str, Dict[str, int]] = {m: {} for m in CUSTOM_METRICS}

    def add(metric, when):
        if when is not None and start <= when < stop:
            k = _month(when.date())
            out[metric][k] = out[metric].get(k, 0) + 1

    for _, created in people:
        add("People_Added", created)
    for chunk in (ids[i:i + 500] for i in range(0, len(ids), 500)):
        seen = set()
        for mid, bid, at in (db.query(DiscoveryResult.member_id, DiscoveryResult.broker_id, DiscoveryResult.scanned_at)
                               .filter(DiscoveryResult.member_id.in_(chunk), DiscoveryResult.scanned_at >= start,
                                       DiscoveryResult.scanned_at < stop).all()):
            key = (mid, bid, at.date())
            if key not in seen:
                seen.add(key)
                add("Listing_Searches", at)
        first_found = {}
        for mid, bid, at in (db.query(DiscoveryResult.member_id, DiscoveryResult.broker_id, DiscoveryResult.scanned_at)
                               .filter(DiscoveryResult.member_id.in_(chunk), DiscoveryResult.found.is_(True)).all()):
            k = (mid, bid)
            if at and (k not in first_found or at < first_found[k]):
                first_found[k] = at
        for at in first_found.values():
            add("Listings_Found", at)
        for sent, confirmed in (db.query(RemovalRequest.sent_at, RemovalRequest.confirmed_at)
                                  .filter(RemovalRequest.member_id.in_(chunk)).all()):
            add("Optout_Requests_Sent", sent)
            add("Removals_Confirmed", confirmed)
    return {m: v for m, v in out.items() if v}


# ── The API ───────────────────────────────────────────────────────────────────

KNOWN_PARAMS = {"customer_id", "requestor_id", "api_key", "platform", "begin_date", "end_date",
                "metric_type", "data_type", "access_method", "attributes_to_show", "granularity"}


def dispatch(db, path: str, params: dict, cfg: Optional[dict] = None,
             now: Optional[datetime] = None) -> Tuple[int, object]:
    """Answer one COUNTER API request. `path` is what follows {base}, e.g.
    "/r51/reports/pr". Returns (HTTP status, JSON body). Never raises."""
    cfg = cfg if cfg is not None else config()
    now = now or datetime.utcnow()
    path = "/" + path.strip("/")
    params = {k.lower(): (v if isinstance(v, str) else str(v)) for k, v in (params or {}).items()}
    try:
        if path == "/r51/status":
            return 200, [{"Description": f"{cfg['platform']} usage statistics (SUSHI-compatible, "
                                         f"not COUNTER-audited)",
                          "Service_Active": bool(cfg["enabled"]),
                          "Registry_Record": cfg.get("registry_record") or "",
                          "Alerts": []}]
        if not path.startswith("/r51/"):
            return 404, exception(3000, f"Unknown path {path}. Paths start with /r51/.")
        if not cfg["enabled"]:
            return _fatal(1000, "Usage statistics are turned off on this server.")
        h, err = _authorize(cfg, params)
        if err:
            return err
        if path == "/r51/members":
            allowed = [c for c in customers(db, cfg) if "*" in h["customers"] or c["id"] in h["customers"]]
            return 200, [{"Customer_ID": c["id"], "Requestor_ID": h["requestor_id"], "Name": c["name"],
                          "Institution_ID": {"Proprietary": [f"{cfg['namespace']}:{c['id']}"]}}
                         for c in allowed]
        c, err = _customer(db, cfg, h, params)
        if err:
            return err
        first, last = months_available(db, now)
        if path == "/r51/reports":
            return 200, [{"Report_Name": r["name"], "Report_ID": r["id"], "Release": RELEASE,
                          "Report_Description": r["description"], "Path": f"/r51/reports/{pid}",
                          **({"First_Month_Available": _month(first), "Last_Month_Available": _month(last)}
                             if first else {})}
                         for pid, r in reports(cfg).items()]
        m = re.fullmatch(r"/r51/reports/([^/]+)", path)
        rep = reports(cfg).get(m.group(1).lower()) if m else None
        if rep is None:
            return 404, exception(3000, f"Supported: {', '.join(r['id'] for r in reports(cfg).values())}")
        return _report(db, cfg, rep, c, params, first, last, now)
    except Exception as e:                       # never a traceback to a harvester
        import logging
        logging.getLogger(__name__).warning("SUSHI request failed: %s", type(e).__name__)
        return _fatal(1000)


def _report(db, cfg, rep, c, params, first, last, now):
    exc: List[dict] = []
    if not params.get("begin_date") or not params.get("end_date"):
        return _fatal(1030, "begin_date and end_date are required")
    begin, end = _parse(params["begin_date"]), _parse(params["end_date"])
    if begin is None or end is None:
        return _fatal(3020, "Use yyyy-mm or yyyy-mm-dd.")
    if end < begin:
        return _fatal(3020, "end_date is before begin_date.")
    this_month = now.date().replace(day=1)
    if begin >= this_month:
        return _fatal(3020, "begin_date is in the current month or later; usage is ready after a month ends.")
    if end > last:
        not_ready = []
        d = _add_months(last, 1)
        while d <= end and len(not_ready) < 24:
            not_ready.append(_month(d))
            d = _add_months(d, 1)
        exc.append(exception(3031, ", ".join(not_ready)))
        end = last

    unknown = sorted(set(params) - KNOWN_PARAMS)
    if rep["id"] == "PR_P1":
        unknown += [p for p in ("metric_type", "data_type", "access_method", "attributes_to_show") if p in params]
    if unknown:
        exc.append(exception(3050, ", ".join(sorted(set(unknown)))))

    def split(name):
        v = params.get(name) if rep["id"] != "PR_P1" else None
        return [x for x in (v or "").split("|") if x]

    metrics = list(rep["metrics"])
    filters: Dict[str, object] = {"Begin_Date": begin.isoformat(), "End_Date": _last_day(end).isoformat()}
    want = split("metric_type")
    if want:
        bad = [w for w in want if w not in rep["metrics"]]
        if bad:
            exc.append(exception(3060, "metric_type: " + ", ".join(bad)))
        metrics = [w for w in rep["metrics"] if w in want] or metrics
        filters["Metric_Type"] = metrics
    data_types = split("data_type")
    if data_types:
        bad = [d for d in data_types if d != "Platform"]
        if bad:
            exc.append(exception(3060, "data_type: " + ", ".join(bad)))
        filters["Data_Type"] = ["Platform"]
    access = split("access_method")
    if access:
        bad = [a for a in access if a not in ("Regular", "TDM")]
        if bad:
            exc.append(exception(3060, "access_method: " + ", ".join(bad)))
        filters["Access_Method"] = [a for a in access if a in ("Regular", "TDM")] or ["Regular"]
    if rep["id"] == "PR_P1":
        filters["Metric_Type"] = list(rep["metrics"])
        filters["Access_Method"] = ["Regular"]
    attrs = split("attributes_to_show")
    show_access = False
    if attrs:
        bad = [a for a in attrs if not (rep["id"] == "PR" and a == "Access_Method")]
        if bad:
            exc.append(exception(3062, "attributes_to_show: " + ", ".join(bad)))
        show_access = "Access_Method" in attrs and rep["id"] == "PR"
    if params.get("granularity") and params["granularity"] != "Month":
        exc.append(exception(3062, "granularity: only Month is supported"))
    if params.get("platform") and params["platform"].lower() != cfg["platform"].lower():
        metrics = []              # a different platform: nothing to report

    raw = counts(db, c["branch_ids"], begin, end)
    if "Access_Method" in filters and "Regular" not in filters["Access_Method"]:
        raw = {}                  # no text and data mining here
    ns = cfg["namespace"]
    perf = {}
    for metric in metrics:
        key = "Listing_Searches" if metric == "Searches_Platform" else metric.split(":", 1)[-1]
        if raw.get(key):
            perf[metric] = dict(sorted(raw[key].items()))
    items = []
    if perf:
        ap = {"Data_Type": "Platform"}
        if show_access:
            ap["Access_Method"] = "Regular"
        ap["Performance"] = perf
        items = [{"Platform": cfg["platform"], "Attribute_Performance": [ap]}]
    else:
        exc.append(exception(3030))

    header = {"Release": RELEASE, "Report_ID": rep["id"], "Report_Name": rep["name"],
              "Created": now.replace(microsecond=0).isoformat() + "Z",
              "Created_By": cfg["platform"],
              "Institution_ID": {"Proprietary": [f"{ns}:{c['id']}"]},
              "Institution_Name": c["name"],
              "Registry_Record": cfg.get("registry_record") or "",
              "Report_Filters": filters}
    if show_access:
        header["Report_Attributes"] = {"Attributes_To_Show": ["Access_Method"]}
    if exc:
        header["Exceptions"] = exc
    return 200, {"Report_Header": header, "Report_Items": items}
