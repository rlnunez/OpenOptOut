"""
General web search: the server runs searches for a family member and sorts
what it finds.

The searches are the same ones "Find your listings" offers as links
(core/listing_finder.discovery_queries) — exact phone numbers, exact street
addresses, exact emails, name + city, people-search phrases — run through a
search provider the admin chose:

  - "searxng": a SearXNG instance (self-hosted, open source). Needs `json` in
    its settings.yml search.formats.
  - "brave":   the Brave Search API (paid per query, API key).

Each result is sorted by how sure we are that it's about this person:

  strong  — the page shows one of their exact phone numbers, street addresses
            or email addresses
  medium  — their name and their city
  weak    — anything else the searches turned up

A strong result on a site OpenOptOut knows as a broker goes straight into the
removal cycle (listing_finder.add_listing). Everything else waits in a review
list for the person: "Add to removals" or "Not me". "Not me" is remembered.

Privacy: these searches send the member's identifiers to the provider (and, for
SearXNG, to the engines it forwards to). That's inherent in web search, so the
feature is off until an admin turns it on, and the settings say so.
"""

import hashlib
import logging
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

DEFAULTS = {"enabled": False, "provider": "", "searxng_url": "", "brave_key_enc": "",
            "max_queries": 12, "weekly": False, "auto_add_strong": True}

PRIVACY_NOTE = ("Web searches send family members' names, phone numbers, addresses and email "
                "addresses to the search provider you choose (a SearXNG server also passes them "
                "on to the search engines it uses). Only turn this on if the family is "
                "comfortable with that.")

# Sites that show up in searches but aren't where a listing lives.
_SKIP_DOMAINS = {"google.com", "bing.com", "duckduckgo.com", "search.brave.com", "yahoo.com",
                 "wikipedia.org", "youtube.com"}

_STREET_ABBR = {"street": "st", "avenue": "ave", "road": "rd", "drive": "dr", "lane": "ln",
                "boulevard": "blvd", "court": "ct", "place": "pl", "terrace": "ter",
                "circle": "cir", "parkway": "pkwy", "highway": "hwy", "north": "n",
                "south": "s", "east": "e", "west": "w", "apartment": "apt", "suite": "ste"}


def settings_of(cfg: dict) -> dict:
    out = dict(DEFAULTS)
    out.update((cfg or {}).get("web_search") or {})
    return out


def configured(ws: dict) -> bool:
    return bool(ws.get("enabled") and (
        (ws.get("provider") == "searxng" and ws.get("searxng_url")) or
        (ws.get("provider") == "brave" and ws.get("brave_key_enc"))))


# ── Providers ─────────────────────────────────────────────────────────────────

def _searxng(ws: dict, query: str) -> list:
    import requests
    base = ws["searxng_url"].rstrip("/")
    url = base if base.endswith("/search") else base + "/search"
    r = requests.get(url, params={"q": query, "format": "json"}, timeout=20,
                     headers={"User-Agent": "OpenOptOut"})
    if r.status_code == 403:
        raise RuntimeError("SearXNG refused the request. Add `json` to search.formats in its settings.yml.")
    r.raise_for_status()
    return [{"url": x.get("url", ""), "title": x.get("title", ""), "snippet": x.get("content", "")}
            for x in (r.json().get("results") or [])]


def _brave(ws: dict, query: str) -> list:
    import requests
    from .oauth_engine import _decrypt
    r = requests.get("https://api.search.brave.com/res/v1/web/search",
                     params={"q": query, "count": 20}, timeout=20,
                     headers={"Accept": "application/json",
                              "X-Subscription-Token": _decrypt(ws["brave_key_enc"])})
    if r.status_code in (401, 403):
        raise RuntimeError("Brave Search rejected the API key.")
    if r.status_code == 429:
        raise RuntimeError("Brave Search rate limit or monthly limit reached.")
    r.raise_for_status()
    out = []
    for x in ((r.json().get("web") or {}).get("results") or []):
        snippet = x.get("description") or " ".join(x.get("extra_snippets") or [])
        out.append({"url": x.get("url", ""), "title": x.get("title", ""), "snippet": snippet})
    return out


PROVIDERS = {"searxng": _searxng, "brave": _brave}


# ── Matching ──────────────────────────────────────────────────────────────────

def _digits_runs(text: str) -> set:
    """Every phone-number-looking run in the text, as 10 digits."""
    out = set()
    for m in re.finditer(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}", text or ""):
        d = re.sub(r"\D", "", m.group(0))
        if len(d) == 11 and d.startswith("1"):
            d = d[1:]
        if len(d) == 10:
            out.add(d)
    return out


def norm_street(s: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()
    return " ".join(_STREET_ABBR.get(w, w) for w in words)


def score(member_profile: dict, text: str) -> tuple:
    """-> (strength, matched_on) for a result's title + snippet + url."""
    low = (text or "").lower()
    phones = {re.sub(r"\D", "", p)[-10:] for p in member_profile["phones"] if len(re.sub(r"\D", "", p)) >= 10}
    if phones & _digits_runs(text):
        return "strong", "phone"
    ntext = norm_street(text)
    for street in member_profile["streets"]:
        ns = norm_street(street)
        if ns and len(ns) > 6 and re.search(r"\b" + re.escape(ns) + r"\b", ntext):
            return "strong", "address"
    for e in member_profile["emails"]:
        if e and e.lower() in low:
            return "strong", "email"
    names = [n.lower() for n in member_profile["names"] if n]
    cities = [p.split(",")[0].strip().lower() for p in member_profile["places"] if p]
    for n in names:
        if n in low:
            if any(c and c in low for c in cities):
                return "medium", "name+city"
            return "weak", "name"
    return "weak", ""


# ── Running ───────────────────────────────────────────────────────────────────

def _url_hash(url: str) -> str:
    u = urlparse(url)
    key = f"{(u.hostname or '').lower()}{u.path.rstrip('/')}?{u.query}"
    return hashlib.sha256(key.encode()).hexdigest()


def run_for_member(db, member, cfg: dict, search=None, pause: float = 1.0) -> dict:
    """
    Run the member's searches, store new results, and add strong matches on
    known brokers to the removal cycle. `search(query) -> [ {url,title,snippet} ]`
    can be injected (tests); otherwise the configured provider is used.
    """
    from ..models.database import WebSearchHit
    from . import listing_finder as lf

    ws = settings_of(cfg)
    if search is None:
        if not configured(ws):
            raise RuntimeError("Web search isn't set up. An admin can turn it on under Admin → Web search.")
        provider = PROVIDERS[ws["provider"]]
        search = lambda q: provider(ws, q)   # noqa: E731

    profile = lf._profile(member)
    queries = lf.discovery_queries(member)[: int(ws.get("max_queries") or 12)]
    stats = {"queries": 0, "results": 0, "new": 0, "added": 0, "errors": []}
    now = datetime.utcnow()

    for i, q in enumerate(queries):
        try:
            results = search(q["query"])
        except Exception as e:
            stats["errors"].append(str(e))
            log.warning("Web search failed (%s): %s", q["label"], e)
            if "rejected" in str(e) or "limit" in str(e) or "refused" in str(e):
                break
            continue
        stats["queries"] += 1
        for r in results or []:
            url = (r.get("url") or "").strip()
            try:
                url = lf.validate_listing_url(url)
            except ValueError:
                continue
            host = lf._host(url)
            domain = lf.registrable_domain(host)
            if domain in _SKIP_DOMAINS:
                continue
            stats["results"] += 1
            h = _url_hash(url)
            hit = db.query(WebSearchHit).filter(WebSearchHit.member_id == member.id,
                                                WebSearchHit.url_hash == h).first()
            if hit is not None:
                hit.last_seen_at = now
                continue
            strength, matched_on = score(profile, " ".join([r.get("title", ""), r.get("snippet", ""), url]))
            broker = lf.resolve_broker(db, url)["broker"]
            hit = WebSearchHit(member_id=member.id, url=url, url_hash=h, domain=domain,
                               title=(r.get("title") or "")[:500], snippet=(r.get("snippet") or "")[:1000],
                               query_label=q["label"], strength=strength, matched_on=matched_on,
                               broker_id=broker.id if broker else None, found_at=now, last_seen_at=now)
            db.add(hit)
            db.flush()
            stats["new"] += 1
            if broker is not None and strength == "strong" and ws.get("auto_add_strong", True):
                res = lf.add_listing(db, member, url, create_unknown=False, source="web_search")
                if res.get("ok"):
                    hit.status = "added"
                    hit.request_id = res.get("request_id")
                    stats["added"] += 1
        db.commit()
        if pause and i < len(queries) - 1:
            time.sleep(pause)
    log.info("Web search for member_id=%s: %s", member.id, {k: v for k, v in stats.items() if k != "errors"})
    return stats


def add_hit(db, hit, member) -> dict:
    """The person says this page is about them: put it in the removal cycle."""
    from . import listing_finder as lf
    res = lf.add_listing(db, member, hit.url, source="web_search")
    hit.status = "added"
    hit.request_id = res.get("request_id")
    db.commit()
    return res


def dismiss_hit(db, hit, reason: str = "not_me") -> None:
    hit.status = "dismissed"
    hit.dismiss_reason = reason if reason in ("not_me", "not_broker") else "not_me"
    db.commit()


def run_weekly(db, cfg: dict) -> dict:
    """Scheduled run for every member, when the admin turned weekly searches on."""
    from ..models.database import FamilyMember
    ws = settings_of(cfg)
    if not (configured(ws) and ws.get("weekly")):
        return {}
    out = {}
    for m in db.query(FamilyMember).all():
        try:
            out[m.id] = run_for_member(db, m, cfg)
        except Exception as e:
            out[m.id] = {"error": str(e)}
    return out
