"""
Listing finder: help a family find where their information is published, and
turn a listing URL they found into an opt-out.

Two halves:

1. Search links (search_plan). Ready-made web searches built from every
   variant in the member's identity vault — exact phone numbers in common
   formats, exact addresses, name + city, and the phrases people-search pages
   use ("possible relatives", "background check", "reverse phone") — plus one
   search per known broker: the broker's own search page when its spec has a
   `search_url`, otherwise a site-restricted web search. The person opens the
   links in their own browser; OpenOptOut never fetches them, so nothing about
   the member is sent anywhere until they click.

2. Listing intake (add_listing). The person pastes a URL they found. The
   broker is worked out from the domain — exact, subdomain, the parent
   company catalog (an instantcheckmate.com page is handled by the
   PeopleConnect opt-out), or a network of state sites — and the listing joins
   the removal cycle as a pending request carrying its URL (several brokers'
   forms ask for it). A domain we don't know becomes a new broker marked for
   research and a checklist item for the person. The URL is never fetched.

The search patterns are adapted from Opt-Out Desk (patrickomatic/opt-out,
src/search.rs), translated from Rust and extended to every identity variant
and to OpenOptOut's broker catalog. Opt-Out Desk's license notice:

    MIT License

    Copyright (c) 2026 Patrick Carroll

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""

import ipaddress
import logging
import re
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus, urlparse

log = logging.getLogger(__name__)

# How many of each identity kind go into searches, so a large vault doesn't
# produce hundreds of links.
LIMITS = {"name": 3, "phone": 3, "address": 3, "email": 3, "place": 3}

ENGINES = {
    "google": "https://www.google.com/search?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
}

# Multi-part public suffixes we may see; everything else uses the last two labels.
_TWO_LEVEL_SUFFIXES = {"co.uk", "org.uk", "com.au", "net.au", "co.nz", "com.br", "co.za"}

UNKNOWN_BROKER_NOTE = ("Added from a listing URL someone found. How to opt out of this site "
                       "hasn't been researched yet.")


# ── Identity variants ─────────────────────────────────────────────────────────

def phone_variants(raw: str) -> list:
    """'+1 (555) 123-4567' -> ['(555) 123-4567', '555-123-4567', '555.123.4567', '5551234567']."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return [raw.strip()] if raw and raw.strip() else []
    a, b, c = digits[:3], digits[3:6], digits[6:]
    return [f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"{a}.{b}.{c}", digits]


def _profile(member) -> dict:
    """Names, places (city, ST), street addresses, phones and emails from the vault."""
    from .combinations import _get_values, _parse_address
    names = _get_values(member, "name", LIMITS["name"]) or ([member.full_name] if member.full_name else [])
    raw_addrs = _get_values(member, "address", 10)
    streets, places = [], []
    for raw in raw_addrs:
        p = _parse_address(raw)
        street = (p.get("address") or "").strip()
        if street and street not in streets:
            streets.append(street)
        place = ", ".join(x for x in (p.get("city", "").strip(), p.get("state", "").strip()) if x)
        if place and place not in places:
            places.append(place)
    phones = _get_values(member, "phone", LIMITS["phone"])
    emails = _get_values(member, "email", LIMITS["email"])
    return {
        "names": names[:LIMITS["name"]],
        "streets": streets[:LIMITS["address"]],
        "places": places[:LIMITS["place"]],
        "phones": phones,
        "emails": emails,
    }


def _links(query: str) -> dict:
    q = quote_plus(query)
    return {k: v.format(q=q) for k, v in ENGINES.items()}


def discovery_queries(member) -> list:
    """
    Broad web searches across identity variants. Each item:
    {"label", "query", "links": {"google", "bing", "duckduckgo"}}.
    """
    p = _profile(member)
    out, seen = [], set()

    def add(label, query):
        if query and query not in seen:
            seen.add(query)
            out.append({"label": label, "query": query, "links": _links(query)})

    for phone in p["phones"]:
        variants = phone_variants(phone)
        for v in variants[:2]:     # the two formats people-search pages use most
            add("Exact phone number", f'"{v}"')
        if variants:
            add("Reverse phone lookup pages", f'"{variants[1] if len(variants) > 1 else variants[0]}" "reverse phone"')
    for street in p["streets"]:
        add("Exact street address", f'"{street}"')
        add("Public records pages for your address", f'"{street}" "public records"')
    for name in p["names"]:
        for place in p["places"] or [""]:
            if place:
                add("Name and city", f'"{name}" "{place}"')
                add("People-search pages listing age", f'"{name}" "{place}" "age"')
        add("People-search pages listing relatives", f'"{name}" "possible relatives"')
        add("Background-check pages", f'"{name}" "background check"')
    for email in p["emails"]:
        add("Exact email address", f'"{email}"')
    return out


# ── Per-broker searches ───────────────────────────────────────────────────────

def _host(url_or_name: str) -> str:
    v = (url_or_name or "").strip().lower()
    if not v:
        return ""
    host = urlparse(v if "://" in v else f"https://{v}").hostname or ""
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host if "." in host else ""


def registrable_domain(host: str) -> str:
    parts = (host or "").lower().strip(".").split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _TWO_LEVEL_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def broker_domain(broker) -> str:
    return _host(getattr(broker, "opt_out_url", "") or "") or _host(getattr(broker, "name", "") or "")


def _fill(template: str, fields: dict) -> str:
    def sub(m):
        return quote_plus(str(fields.get(m.group(1), "") or ""))
    return re.sub(r"\{([a-z_]+)\}", sub, template)


def broker_searches(db, member, include_disabled: bool = False) -> list:
    """
    One search per known broker: its own search page when the broker's spec
    has a `search_url`, otherwise a site-restricted web search.
    """
    from ..models.database import Broker
    p = _profile(member)
    name = p["names"][0] if p["names"] else ""
    first, _, last = name.partition(" ")
    place = p["places"][0] if p["places"] else ""
    city, _, state = place.partition(", ")
    phone = p["phones"][0] if p["phones"] else ""
    fields = {"first_name": first, "last_name": last.split(" ")[-1] if last else "",
              "full_name": name, "city": city, "state": state, "phone": re.sub(r"\D", "", phone)}

    q = db.query(Broker).filter(Broker.is_test.isnot(True))
    if not include_disabled:
        q = q.filter(Broker.enabled.isnot(False))
    out, seen_domains = [], set()
    for b in q.order_by(Broker.priority.desc(), Broker.name).all():
        domain = broker_domain(b)
        if not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        direct = ""
        try:
            from ..plugins.broker_addon import get_broker_spec_for_broker
            spec = get_broker_spec_for_broker(db, b)
            if spec and spec.search_url:
                direct = _fill(spec.search_url, fields)
        except Exception:
            pass
        needle = " ".join(x for x in (f'"{name}"' if name else "", f'"{place}"' if place else "") if x)
        site_query = f"{needle} site:{domain}".strip() if needle else f"site:{domain}"
        out.append({
            "broker_id": b.id, "broker_name": b.name, "domain": domain,
            "search_url": direct or _links(site_query)["google"],
            "kind": "broker_search" if direct else "site_search",
        })
    return out


def search_plan(db, member) -> dict:
    return {"queries": discovery_queries(member), "brokers": broker_searches(db, member)}


# ── URL → broker ──────────────────────────────────────────────────────────────

def validate_listing_url(url: str) -> str:
    """Return a cleaned https/http URL or raise ValueError with a plain message."""
    u = (url or "").strip()
    if not u:
        raise ValueError("Paste the web address of the page that shows your information.")
    if "://" not in u:
        u = "https://" + u
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("That doesn't look like a web address. It should start with https://")
    host = parsed.hostname.lower()
    is_ip = True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        is_ip = False
    if is_ip:
        raise ValueError("Please paste the site's web address, not a numeric IP address.")
    if "." not in host or host.endswith((".local", ".internal", ".localhost")) or host == "localhost":
        raise ValueError("That address isn't a public website.")
    if host.endswith(("google.com", "bing.com", "duckduckgo.com")) and parsed.path.startswith(("/search", "/url")):
        raise ValueError("That's a search results page. Open the result and paste the address of the page itself.")
    if len(u) > 2000:
        raise ValueError("That web address is too long.")
    return u


def resolve_broker(db, url: str) -> dict:
    """
    Work out which broker a listing URL belongs to.
    Returns {"broker": Broker|None, "domain", "match": exact|subdomain|parent|network|none,
             "note": plain-language explanation}.
    """
    from ..models.database import Broker, ParentCompany
    host = _host(url)
    reg = registrable_domain(host)
    brokers = db.query(Broker).filter(Broker.is_test.isnot(True)).all()
    by_domain = {}
    for b in brokers:
        d = broker_domain(b)
        if d:
            by_domain.setdefault(d, b)

    if host in by_domain:
        return {"broker": by_domain[host], "domain": host, "match": "exact", "note": ""}
    if reg in by_domain:
        return {"broker": by_domain[reg], "domain": reg, "match": "subdomain", "note": ""}
    for d, b in by_domain.items():
        if registrable_domain(d) == reg:
            return {"broker": b, "domain": reg, "match": "subdomain", "note": ""}

    # Parent-company catalog: a site owned by a family whose opt-out we handle.
    try:
        from .parent_catalog import load_catalog, matches_child
        for entry in load_catalog()["parents"]:
            if not matches_child(reg, entry.get("children", []), entry.get("child_suffixes", [])):
                continue
            parent = db.query(ParentCompany).filter(ParentCompany.name.ilike(entry["name"])).first()
            child = None
            if parent is not None:
                kids = [b for b in parent.children or [] if not getattr(b, "is_test", False)]
                child = next((b for b in kids if registrable_domain(broker_domain(b)) == reg), None) \
                    or next((b for b in kids if b.enabled), None)
            if child is not None:
                match = "network" if entry.get("child_suffixes") and not entry.get("children") else "parent"
                return {"broker": child, "domain": reg, "match": match,
                        "note": f"{reg} is part of {entry['name']}; its opt-out covers this site."}
    except Exception as e:
        log.debug("parent catalog lookup skipped: %s", e)

    return {"broker": None, "domain": reg, "match": "none", "note": ""}


# ── Listing → removal cycle ───────────────────────────────────────────────────

_OPEN_STATUSES = ("pending", "sent", "submitted", "needs_manual", "recheck_due")


def add_listing(db, member, url: str, create_unknown: bool = True, source: str = "manual") -> dict:
    """
    Record a listing the person found and make sure it's in the removal cycle.
    Returns a result dict with a plain-language `message`.
    """
    from ..models.database import Broker, DiscoveryResult, RemovalRequest, RequestStatus, OptOutMethod

    clean = validate_listing_url(url)
    hit = resolve_broker(db, clean)
    broker, created = hit["broker"], False

    if broker is None:
        if not create_unknown:
            return {"ok": False, "domain": hit["domain"], "match": "none",
                    "message": f"OpenOptOut doesn't know {hit['domain']} yet."}
        broker = Broker(name=hit["domain"], opt_out_url=None, method=OptOutMethod.manual,
                        notes=UNKNOWN_BROKER_NOTE, enabled=True, priority=3)
        db.add(broker)
        db.flush()
        created = True

    db.add(DiscoveryResult(member_id=member.id, broker_id=broker.id, found=True,
                           listing_url=clean, source=source,
                           snippet=("Added by a family member" if source == "manual"
                                    else "Found by web search"), scanned_at=datetime.utcnow()))

    open_statuses = [RequestStatus(s) for s in _OPEN_STATUSES if s in RequestStatus.__members__]
    req = db.query(RemovalRequest).filter(
        RemovalRequest.member_id == member.id,
        RemovalRequest.broker_id == broker.id,
        RemovalRequest.status.in_(open_statuses),
    ).order_by(RemovalRequest.created_at.desc()).first()

    if req is None:
        # A finished request (confirmed/failed/rejected) doesn't stop a new one:
        # the listing is back, or the last attempt didn't work.
        req = RemovalRequest(member_id=member.id, broker_id=broker.id,
                             request_key=str(uuid.uuid4()), listing_url=clean,
                             status=RequestStatus.pending)
        db.add(req)
        state = "added"
    else:
        if not req.listing_url:
            req.listing_url = clean
        elif clean not in (req.listing_url or "") and clean not in (req.notes or ""):
            req.notes = ((req.notes or "") + f"\nAnother listing: {clean}").strip()
        state = "already_open"

    if not created and broker.method == OptOutMethod.manual and req.status == RequestStatus.pending \
            and (broker.origin or "curated") != "state_program":
        # No automated opt-out for this site yet: tell the person what to do.
        where = broker.opt_out_url or f"https://{hit['domain']}"
        how = f"Ask {broker.name} to delete your information at {where}"
        if broker.registry_contact_email:
            how += (f", or email {broker.registry_contact_email} (the contact address it gave the "
                    f"state registry)")
        req.status = RequestStatus.needs_manual
        req.notes = f"{how}. Include the address of your listing: {clean}"

    if created:
        req.status = RequestStatus.needs_manual
        req.notes = (f"OpenOptOut doesn't know how to opt out of {hit['domain']} yet. On that site, "
                     f"look for a link at the bottom of the page called \"Opt out\", \"Remove my "
                     f"information\", \"Do not sell\" or \"Privacy\". Your listing: {clean}")
    elif not broker.enabled:
        req.notes = ((req.notes or "") + f"\n{broker.name} is turned off by your administrator, "
                     "so this listing will wait until it's turned back on.").strip()

    db.commit()

    if created:
        msg = (f"Added. {hit['domain']} is new to OpenOptOut, so it's on your checklist with "
               f"instructions, and your administrator will see it as a site to research.")
    elif state == "already_open":
        msg = f"{broker.name} is already in the removal cycle for {member.full_name}; the link was saved with it."
    else:
        msg = f"Added. {broker.name} will be included in the next opt-out run for {member.full_name}."
    if hit["note"] and not created:
        msg += " " + hit["note"]
    return {"ok": True, "broker_id": broker.id, "broker_name": broker.name, "domain": hit["domain"],
            "match": "new" if created else hit["match"], "request_id": req.id,
            "state": "new_broker" if created else state, "message": msg}
