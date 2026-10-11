"""
State data-broker registries → broker records (turned off by default).

California, Vermont, Texas and Oregon require data brokers to register. Their
registries are the most complete public lists of who sells personal data, so
importing them keeps OpenOptOut's broker list current. But most registered
brokers are advertising or business-data companies that will never have a page
about a particular family, so imported brokers start TURNED OFF:

  - they appear in the broker list, the admin's registry page, and in "Find
    your listings" matching (a pasted page on a registered site is recognized),
  - a person who finds a listing about themselves on one gets an opt-out for it
    (see core/broker_gate.py),
  - an admin can turn them on, after a warning (REGISTRY_ENABLE_WARNING).

Input is the registry's own export: an uploaded CSV (or XLSX when openpyxl is
installed), or a URL an admin saved for that state. Column names differ by
state, so headers are matched by alias. Every import is previewed before it is
applied, and applying never deletes a broker, never turns one on, and never
overwrites what an admin or a plugin set — it only adds registry details.
"""

import csv
import io
import ipaddress
import logging
import re
import socket
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

SOURCES = {
    "CA": {"label": "California", "page": "https://cppa.ca.gov/data_broker_registry/",
           "how": "On the registry page, choose \"Download CSV\".", "default_url": ""},
    "VT": {"label": "Vermont",
           "page": "https://bizfilings.vermont.gov/online/DatabrokerInquire/",
           "how": "Use the registry's export, or the saved address below.",
           "default_url": "https://bizfilings.vermont.gov/online/DatabrokerInquire/DatabrokerExport"},
    "TX": {"label": "Texas", "page": "https://texas-sos.appianportalsgov.com/data-broker-registry",
           "how": "Search the registry and export the results, if the portal offers it; "
                  "otherwise save the list as a CSV with name and website columns.",
           "default_url": ""},
    "OR": {"label": "Oregon", "page": "https://dfr.oregon.gov/business/licensing/data-broker-registry",
           "how": "Download the published registry list, or save it as a CSV with name "
                  "and website columns.", "default_url": ""},
}

REGISTRY_ENABLE_WARNING = (
    "Turning on brokers from state registries can do more harm than good. Each one you turn "
    "on is sent every family member's names, addresses, phone numbers and email addresses — "
    "including companies that probably have no record about your family. Most registered "
    "brokers are advertising or business-data companies. An opt-out request can confirm to "
    "them that your details are real and current, and some keep the request itself. Turn on "
    "only brokers you have reason to think hold your family's data. Brokers where someone "
    "found a listing about themselves are already handled for that person without being "
    "turned on."
)

MAX_BYTES = 20 * 1024 * 1024

_HEADERS = {
    "name": ["data broker name", "business name", "legal name", "company name", "name",
             "registrant", "entity name", "data broker"],
    "website": ["website url", "website", "primary website", "url", "web address",
                "internet address", "company website"],
    "email": ["email address", "contact email", "email", "e-mail", "consumer contact email",
              "privacy email"],
    "opt_out_url": ["opt-out url", "opt out url", "opt-out link", "opt out link",
                    "opt-out website", "how to opt out", "privacy url", "privacy policy url",
                    "deletion request url", "consumer rights url"],
}


# ── Parsing ───────────────────────────────────────────────────────────────────

def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_\*\:]", " ", (h or "").strip().lower())).strip()


def map_headers(headers: list) -> dict:
    """{'name': index, 'website': index, ...} using the alias lists, best match first."""
    normed = [_norm(h) for h in headers]
    out = {}
    for field, aliases in _HEADERS.items():
        for alias in aliases:                     # exact matches first
            if alias in normed and normed.index(alias) not in out.values():
                out[field] = normed.index(alias)
                break
        if field not in out:
            for alias in aliases:                 # then "contains"
                hit = next((i for i, h in enumerate(normed)
                            if alias in h and i not in out.values()), None)
                if hit is not None:
                    out[field] = hit
                    break
    return out


def _cells_from_upload(data: bytes, filename: str) -> list:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl
        except ImportError:
            raise ValueError("This server can't read Excel files. Open the file and save it as CSV, then upload that.")
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        return [["" if c is None else str(c) for c in row] for row in ws.iter_rows(values_only=True)]
    if name.endswith(".xls"):
        raise ValueError("Old .xls files aren't supported. Save the file as CSV and upload that.")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    # Registries differ in delimiter, and a title line above the header can
    # fool a single guess, so try each common delimiter and keep the first that
    # yields recognisable columns (parse_registry checks), else commas.
    tables = {d: [row for row in csv.reader(io.StringIO(text), delimiter=d)] for d in (",", ";", "\t", "|")}
    for d, rows in tables.items():
        for row in rows[:10]:
            m = map_headers(row)
            if "name" in m and ("website" in m or "opt_out_url" in m):
                return rows
    return tables[","]


def parse_registry(data: bytes, filename: str = "registry.csv") -> dict:
    """
    -> {"rows": [{name, website, domain, email, opt_out_url}], "mapped": {...},
        "unmapped": [header,...], "skipped": int}
    """
    if len(data) > MAX_BYTES:
        raise ValueError("That file is larger than 20 MB, which is more than any registry export should be.")
    cells = [r for r in _cells_from_upload(data, filename) if any((c or "").strip() for c in r)]
    if not cells:
        raise ValueError("The file is empty.")
    # The header is the first row (within the first 10) that maps a name column.
    header_i, mapping = None, {}
    for i, row in enumerate(cells[:10]):
        m = map_headers(row)
        if "name" in m and ("website" in m or "opt_out_url" in m):
            header_i, mapping = i, m
            break
    if header_i is None:
        raise ValueError("Couldn't find the columns. The file needs a column for the broker's "
                         "name and one for its website.")
    headers = cells[header_i]
    from .listing_finder import _host, registrable_domain
    rows, skipped = [], 0
    for r in cells[header_i + 1:]:
        def get(f):
            i = mapping.get(f)
            return (r[i] if i is not None and i < len(r) else "").strip()
        name = get("name")
        website = get("website") or get("opt_out_url")
        host = _host(website)
        if not name or not host:
            skipped += 1
            continue
        email = get("email")
        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            email = ""
        opt = get("opt_out_url")
        rows.append({"name": name[:200], "website": website[:500],
                     "domain": registrable_domain(host), "email": email.lower(),
                     "opt_out_url": opt[:500] if _host(opt) else ""})
    return {"rows": rows, "mapped": {k: headers[v] for k, v in mapping.items()},
            "unmapped": [h for i, h in enumerate(headers) if i not in mapping.values() and h],
            "skipped": skipped}


# ── Fetching (only URLs an admin saved) ───────────────────────────────────────

def _public_host(host: str) -> bool:
    try:
        for fam, _, _, _, addr in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(addr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False


def fetch_registry(url: str, timeout: int = 60) -> tuple:
    """Download a registry export. https only, public hosts only, 20 MB cap."""
    u = urlparse(url or "")
    if u.scheme != "https" or not u.hostname:
        raise ValueError("Registry addresses must start with https://")
    if not _public_host(u.hostname):
        raise ValueError("That address doesn't point to a public website.")
    import requests
    r = requests.get(url, timeout=timeout, stream=True, allow_redirects=False,
                     headers={"User-Agent": "OpenOptOut registry sync"})
    if r.status_code in (301, 302, 303, 307, 308):
        raise ValueError(f"The registry moved (to {r.headers.get('Location', 'somewhere else')}). "
                         "Update the saved address.")
    if r.status_code != 200:
        raise ValueError(f"The registry answered with error {r.status_code}.")
    buf = bytearray()
    for chunk in r.iter_content(65536):
        buf.extend(chunk)
        if len(buf) > MAX_BYTES:
            raise ValueError("The download is larger than 20 MB; that isn't a registry export.")
    ctype = (r.headers.get("Content-Type") or "").lower()
    name = "registry.xlsx" if "spreadsheetml" in ctype or u.path.lower().endswith(".xlsx") else "registry.csv"
    if "text/html" in ctype:
        raise ValueError("That address returns a web page, not a file. Save the download link instead.")
    return bytes(buf), name


# ── Plan / apply ──────────────────────────────────────────────────────────────

def _states(b) -> set:
    return {s for s in (b.registry_states or "").split(",") if s}


def plan(db, state: str, rows: list) -> dict:
    """What an import would do. Nothing is written."""
    from ..models.database import Broker
    from .listing_finder import broker_domain, registrable_domain
    state = state.upper()
    existing = {}
    for b in db.query(Broker).filter(Broker.is_test.isnot(True)).all():
        d = broker_domain(b)
        if d:
            existing.setdefault(registrable_domain(d), b)

    try:
        from .parent_catalog import load_catalog, matches_child
        catalog = load_catalog()["parents"]
    except Exception:
        catalog = []

    new, matched, seen = [], [], set()
    for r in rows:
        if r["domain"] in seen:
            continue
        seen.add(r["domain"])
        b = existing.get(r["domain"])
        if b is not None:
            matched.append({"broker_id": b.id, "broker_name": b.name, "domain": r["domain"],
                            "registry_name": r["name"], "enabled": bool(b.enabled)})
            continue
        family = next((e["name"] for e in catalog
                       if matches_child(r["domain"], e.get("children", []), e.get("child_suffixes", []))), None)
        new.append({**r, "family": family})

    gone = []
    for b in db.query(Broker).filter(Broker.registry_states.isnot(None)).all():
        if state in _states(b) and registrable_domain(broker_domain(b) or "") not in seen:
            gone.append({"broker_id": b.id, "broker_name": b.name})
    return {"state": state, "new": new, "matched": matched, "no_longer_listed": gone,
            "counts": {"rows": len(rows), "new": len(new), "matched": len(matched),
                       "no_longer_listed": len(gone)}}


def apply(db, state: str, rows: list, settings_update=None) -> dict:
    """
    Import: create new brokers TURNED OFF, add registry details to existing
    ones, and mark brokers missing from this state's list. Returns the plan.
    """
    from ..models.database import Broker, OptOutMethod, Difficulty, BrokerStatus
    state = state.upper()
    p = plan(db, state, rows)
    now = datetime.utcnow()
    by_domain = {r["domain"]: r for r in rows}

    from .broker_updates import record as _update
    label = SOURCES.get(state, {}).get("label", state)
    for m in p["matched"]:
        b = db.query(Broker).get(m["broker_id"])
        st = _states(b) | {state}
        b.registry_states = ",".join(sorted(st))
        b.registry_last_seen = now
        r = by_domain.get(m["domain"]) or {}
        if r.get("email") and not b.registry_contact_email:
            b.registry_contact_email = r["email"]
            _update(db, "contact_changed", f"{b.name} gave the {label} registry a contact address: {r['email']}",
                    "It isn't used for opt-outs until someone confirms it.", broker_id=b.id, now=now)

    for r in p["new"]:
        note = f"Imported from the {SOURCES.get(state, {}).get('label', state)} data broker registry " \
               f"as \"{r['name']}\". How to opt out hasn't been researched yet."
        if r.get("family"):
            note += f" Its domain is in the {r['family']} family in the parent-company catalog."
        name = r["domain"] if db.query(Broker).filter(Broker.name.ilike(r["name"])).first() else r["name"]
        db.add(Broker(
            name=name, opt_out_url=r.get("opt_out_url") or f"https://{r['domain']}",
            method=OptOutMethod.manual, difficulty=Difficulty.medium,
            status=BrokerStatus.compliant, notes=note, enabled=False, priority=2,
            origin="registry", registry_states=state, registry_contact_email=r.get("email") or None,
            registry_last_seen=now,
        ))
    if p["new"]:
        names = ", ".join(r["name"] for r in p["new"][:25]) + (" …" if len(p["new"]) > 25 else "")
        _update(db, "new_brokers",
                f"{len(p['new'])} new broker{'s' if len(p['new']) != 1 else ''} from the {label} registry",
                f"They start turned off. {names}", now=now)
    if p["no_longer_listed"]:
        gone = p["no_longer_listed"]
        names = ", ".join(g["broker_name"] for g in gone[:25]) + (" …" if len(gone) > 25 else "")
        _update(db, "delisted",
                f"{len(gone)} broker{'s' if len(gone) != 1 else ''} no longer on the {label} registry",
                f"They may have closed, renamed, or stopped registering: {names}", now=now)
    db.commit()
    if settings_update:
        settings_update(state, p["counts"], now)
    log.info("Registry %s imported: %d new (off), %d matched, %d no longer listed",
             state, p["counts"]["new"], p["counts"]["matched"], p["counts"]["no_longer_listed"])
    return p


def record_import(settings: dict, state: str, counts: dict, when: datetime) -> dict:
    src = settings.setdefault("registry_sources", {}).setdefault(state, {})
    src["last_import_at"] = when.isoformat() + "Z"
    src["last_counts"] = counts
    return settings


def refresh_saved_sources(db, settings: dict) -> dict:
    """Scheduled refresh: import every state that has a saved URL."""
    results = {}
    for state in SOURCES:
        url = ((settings.get("registry_sources") or {}).get(state) or {}).get("url")
        if not url:
            continue
        try:
            data, name = fetch_registry(url)
            parsed = parse_registry(data, name)
            results[state] = apply(db, state, parsed["rows"])["counts"]
            record_import(settings, state, results[state], datetime.utcnow())
        except Exception as e:
            results[state] = {"error": str(e)}
            log.warning("Registry refresh for %s failed: %s", state, e)
    return results


def enable_brokers(db, broker_ids: Optional[list] = None, all_registry: bool = False) -> int:
    from ..models.database import Broker
    q = db.query(Broker).filter(Broker.origin == "registry", Broker.enabled.is_(False))
    if not all_registry:
        q = q.filter(Broker.id.in_(broker_ids or []))
    n = 0
    for b in q.all():
        b.enabled = True
        n += 1
    db.commit()
    return n
