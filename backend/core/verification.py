"""
Automated removal verification: did the listing actually go, and has it
come back?

After an opt-out, OpenOptOut looks again, in the most direct way available:

  1. listing_url    the person's own listing page, when we know it (pasted,
                    found by Discovery or web search, required by the broker)
  2. broker_search  the broker's own search page (spec `search_url`), reading
                    result links that match the spec's `listing_pattern`
  3. web_search     a site-restricted search through the bundled SearXNG,
                    then a look at each result page

Verdicts:
  gone       the page is gone (404/410), redirects away, or no longer shows
             the person; their search no longer finds them
  listed     a page on the broker still shows them (name plus city, phone,
             street or email, or their own listing page still names them)
  not_found  nothing turned up, but the check couldn't see the listing itself
             (e.g. only a web search, which can lag)
  blocked    the site refused automated visits (CAPTCHA wall, 403, 429)
  unknown    network trouble or nothing to check with

What happens next:
  * sent / submitted + gone      → confirmed ("checked: listing gone")
  * confirmed + listed           → back in the queue to be sent again
                                   (it reappeared, or the removal didn't stick)
  * sent + listed after the
    broker's response window     → sent again
  * confirmed + gone / not_found → next check pushed out
  * blocked / unknown            → left as is (the scheduled re-send still runs)

Runs daily on a budget (verification_job), at every scheduled re-check, and
whenever the weekly web search finds a page on a broker someone was already
removed from. Only the broker's own pages and the bundled search are
contacted; only public addresses; the URLs and search terms carry the
person's name, which the broker already has.
"""

import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

log = logging.getLogger(__name__)

DEFAULTS = {"enabled": True, "use_browser": True, "per_day": 40, "per_broker": 5,
            "sent_every_days": 7, "confirmed_every_days": 30}
GONE_TEXT = re.compile(r"(profile|record|listing|page|person)[^.\n]{0,40}(has been |was )?(removed|deleted|suppressed|"
                       r"opted out|no longer (available|exists))|no (results|records|matches) found|"
                       r"we couldn.?t find|not found|0 results", re.I)
BLOCK_TEXT = re.compile(r"verify you are (a )?human|are you a robot|checking your browser|access denied|"
                        r"attention required|captcha|unusual traffic|cf-chl|just a moment", re.I)
_TAGS = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.I | re.S)
_A = re.compile(r"<a\b[^>]*?\bhref\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", re.I | re.S)


def settings_of(cfg: dict) -> dict:
    out = dict(DEFAULTS)
    out.update((cfg or {}).get("verification") or {})
    return out


def _text(html: str) -> str:
    import html as _h
    return " ".join(_h.unescape(_TAGS.sub(" ", html or "")).split())


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().strip(".")


def _on(host: str, domain: str) -> bool:
    return bool(domain) and (host == domain or host.endswith("." + domain))


# ── Fetching ──────────────────────────────────────────────────────────────────

def http_get(url: str, domain: str):
    """(final_url, status, html). Public addresses on the broker's domain only."""
    import requests
    from urllib.parse import urljoin
    from .confirm_links import public_host
    cur = url
    for _ in range(5):
        u = urlparse(cur)
        if u.scheme not in ("http", "https") or not _on(_host(cur), domain) or not public_host(_host(cur)):
            return cur, 0, ""
        r = requests.get(cur, timeout=20, allow_redirects=False, stream=True,
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
                                  "Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.8"})
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            cur = urljoin(cur, r.headers["Location"])
            continue
        body = r.raw.read(2_000_000, decode_content=True).decode(r.encoding or "utf-8", "replace")
        return cur, r.status_code, body
    return cur, 0, ""


def browser_get(url: str, domain: str):
    """Same, through headless Chromium, for sites that only render with script."""
    import asyncio

    async def go():
        from playwright.async_api import async_playwright
        from .dns_guard import is_public_ip, public_host
        from .proxy import get_proxy_for_context
        from .gpc import apply_gpc_headers, apply_gpc_to_context
        async with async_playwright() as p:
            ctx_args = {}
            proxy = get_proxy_for_context()
            if proxy:
                ctx_args["proxy"] = proxy
            ctx_args = apply_gpc_headers(ctx_args)
            b = await p.firefox.launch(headless=True)
            try:
                ctx = await b.new_context(**ctx_args)
                await apply_gpc_to_context(ctx)

                async def guard(route):
                    h = _host(route.request.url)
                    if route.request.is_navigation_request() and not _on(h, domain):
                        return await route.abort()
                    if h and not public_host(h):
                        return await route.abort()
                    await route.continue_()
                await ctx.route("**/*", guard)
                page = await ctx.new_page()
                resp = await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                if resp:
                    try:
                        server = await resp.server_addr() if callable(getattr(resp, "server_addr", None)) else None
                        if server and server.get("ipAddress") and not is_public_ip(server["ipAddress"]):
                            return url, 0, ""
                    except Exception:
                        pass
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                return page.url, (resp.status if resp else 0), await page.content()
            finally:
                await b.close()
    try:
        return asyncio.run(go())
    except Exception as e:
        log.info("browser check of %s failed: %s", _host(url), type(e).__name__)
        return url, 0, ""


def fetcher(cfg: dict):
    s = settings_of(cfg)

    def fetch(url, domain):
        try:
            res = http_get(url, domain)
        except Exception as e:
            log.info("check of %s failed: %s", _host(url), type(e).__name__)
            res = (url, 0, "")
        final, status, body = res
        blocked = status in (403, 429, 503) or (status == 200 and BLOCK_TEXT.search(_text(body)[:3000]))
        if (blocked or (status == 200 and len(_text(body)) < 200)) and s["use_browser"]:
            b = browser_get(url, domain)
            if b[1]:
                return b
        return res
    return fetch


# ── Reading pages ─────────────────────────────────────────────────────────────

def _profile(member) -> dict:
    from .listing_finder import _profile as lf_profile
    return lf_profile(member)


def person_on_page(profile: dict, text: str) -> str:
    """'strong' | 'medium' | 'name' | '' for how clearly the page shows this person."""
    from .web_search import score
    strength, matched = score(profile, text)
    if strength in ("strong", "medium"):
        return strength
    return "name" if matched == "name" else ""


def check_listing_page(url: str, profile: dict, domain: str, fetch) -> tuple:
    """(verdict, detail) for the person's own listing page."""
    final, status, body = fetch(url, domain)
    if status in (404, 410):
        return "gone", f"the page answers {status}"
    if status in (403, 429, 503) or status == 0 and not body:
        return ("blocked", f"the site refused the check ({status})") if status else ("unknown", "the page didn't load")
    text = _text(body)
    if BLOCK_TEXT.search(text[:3000]) and not person_on_page(profile, text):
        return "blocked", "the site showed a robot check"
    if urlparse(final).path.rstrip("/") != urlparse(url).path.rstrip("/") and not person_on_page(profile, text):
        return "gone", "the listing now redirects elsewhere"
    seen = person_on_page(profile, text)
    if seen:
        return "listed", f"the listing page still shows them ({seen} match)"
    if GONE_TEXT.search(text):
        return "gone", "the page says the record was removed or not found"
    return "gone", "the page no longer shows them"


def check_broker_search(spec, fields: dict, profile: dict, domain: str, fetch) -> tuple:
    """(verdict, detail, evidence_url) from the broker's own search page."""
    from .interpreter.compiler import _render_url, CompileError
    try:
        url = _render_url(spec.search_url, {k: v for k, v in fields.items() if v})
    except CompileError as e:
        return "unknown", f"can't build the search ({e})", None
    final, status, body = fetch(url, domain)
    if status in (403, 429, 503):
        return "blocked", f"the site refused the search ({status})", None
    if status >= 400 or not body:
        return "unknown", "the search page didn't load", None
    text = _text(body)
    if BLOCK_TEXT.search(text[:3000]):
        return "blocked", "the site showed a robot check", None
    import html as _h
    from urllib.parse import urljoin
    pattern = re.compile(spec.listing_pattern, re.I) if spec.listing_pattern else None
    best, best_url = "", None
    order = {"strong": 3, "medium": 2, "name": 1, "": 0}
    # Each result: its link plus the text up to the next result link, so one
    # person's details never get credited to the namesake listed next to them.
    results = []
    for m in _A.finditer(body):
        href = urljoin(final, _h.unescape(m.group(2)))
        if (pattern and not pattern.search(href)) or not _on(_host(href), domain):
            continue
        results.append((m.start(), href))
    for k, (start, href) in enumerate(results):
        end = results[k + 1][0] if k + 1 < len(results) else start + 1500
        ctx = _text(body[start:min(end, start + 1500)])
        seen = person_on_page(profile, ctx)
        if order[seen] > order[best]:
            best, best_url = seen, href
    if best in ("strong", "medium"):
        return "listed", f"the broker's search still finds them ({best} match)", best_url
    if best == "name":
        return "not_found", "the search shows someone with the same name, but nothing else matches", best_url
    return "gone", "the broker's search no longer finds them", None


def check_keyed_search(spec, member, profile: dict, domain: str, fetch, key: str = "phone") -> tuple:
    """
    Search a site that files people by phone number or email once per saved
    number or address. Listed if any one still shows the person; gone only if
    every one was checked and none did.
    """
    from .interpreter.member_fields import resolve as resolve_fields
    from .combinations import build_keyed_optout_combos
    combos = build_keyed_optout_combos(member, key)
    what = "numbers" if key == "phone" else "email addresses"
    if not combos:
        return "unknown", f"no {what} saved to search with", None
    seen = []
    for combo in combos:
        # The results page repeats what was searched, so that alone isn't
        # evidence; the name or address next to it has to match.
        if key == "phone":
            searched = re.sub(r"\D", "", combo.phone or "")[-10:]
            prof = dict(profile, phones=[p for p in profile.get("phones", [])
                                         if re.sub(r"\D", "", p)[-10:] != searched])
            tag = f"number ending {(combo.phone or '')[-4:]}"
        else:
            searched = (combo.email or "").lower()
            prof = dict(profile, emails=[e for e in profile.get("emails", []) if e.lower() != searched])
            tag = f"email {searched.split('@')[0][:2]}…@{searched.split('@')[-1]}"
        v, d, ev = check_broker_search(spec, resolve_fields(member, combo), prof, domain, fetch)
        if v == "listed":
            return "listed", f"{d} ({tag})", ev
        seen.append(v)
    if all(v == "gone" for v in seen):
        return "gone", f"none of the {len(seen)} saved {what} show them any more", None
    if "blocked" in seen:
        return "blocked", "the site refused some of the searches", None
    if "not_found" in seen:
        return "not_found", f"the site shows someone else for these {what}", None
    return "unknown", f"couldn't check every one of the {what}", None


def check_web(db, req, profile: dict, domain: str, fetch, cfg: dict, search=None) -> tuple:
    """(verdict, detail, evidence_url) from a site-restricted web search, confirmed by visiting the hits."""
    from . import web_search as wsm
    ws = wsm.settings_of(cfg)
    if search is None:
        if not wsm.configured(ws):
            return "unknown", "web search isn't set up", None
        search = lambda q: wsm.PROVIDERS["searxng"](ws, q)   # noqa: E731
    names = profile["names"][:2] or [req.member.full_name]
    place = (profile["places"][0].split(",")[0] if profile["places"] else "")
    hits = []
    for n in names:
        q = f'site:{domain} "{n}"' + (f' "{place}"' if place else "")
        try:
            hits += search(q) or []
        except Exception as e:
            return "unknown", f"web search failed ({type(e).__name__})", None
    seen_urls = []
    for h in hits:
        url = h.get("url", "")
        if not _on(_host(url), domain) or url in seen_urls:
            continue
        seen_urls.append(url)
        hint = person_on_page(profile, f"{h.get('title', '')} {h.get('snippet', '')} {url}")
        if not hint:
            continue
        # Search engines lag behind removals: only a page that still shows them counts.
        verdict, detail = check_listing_page(url, profile, domain, fetch)
        if verdict == "listed":
            return "listed", "a web search found a page that still shows them", url
        if len(seen_urls) >= 4:
            break
    return "not_found", ("web search found nothing current" if hits else "web search found nothing"), None


# ── Checking one request ──────────────────────────────────────────────────────

def _spec(db, broker):
    try:
        from ..plugins.broker_addon import get_broker_spec_for_broker
        return get_broker_spec_for_broker(db, broker)
    except Exception:
        return None


def verify_request(db, req, cfg: dict, fetch=None, search=None, now=None) -> dict:
    """Check one request and act on the result. Returns {verdict, method, detail, evidence, action}."""
    from ..models.database import VerificationCheck, RequestStatus
    from .listing_finder import broker_domain, registrable_domain
    from .interpreter.member_fields import resolve as resolve_fields
    now = now or datetime.utcnow()
    fetch = fetch or fetcher(cfg)
    broker, member = req.broker, req.member
    domain = registrable_domain(broker_domain(broker) or "") if broker else ""
    if not domain or member is None:
        return {"verdict": "unknown", "method": "", "detail": "nothing to check with", "evidence": None, "action": ""}
    profile = _profile(member)
    spec = _spec(db, broker)
    verdict, detail, evidence, method = "unknown", "nothing to check with", None, ""

    if req.listing_url and _on(_host(req.listing_url), domain):
        method, evidence = "listing_url", req.listing_url
        verdict, detail = check_listing_page(req.listing_url, profile, domain, fetch)
    if verdict in ("unknown", "blocked") and spec is not None and getattr(spec, "search_url", ""):
        if getattr(spec, "lookup_by", "") in ("phone", "email"):
            v, d, ev = check_keyed_search(spec, member, profile, domain, fetch, spec.lookup_by)
        else:
            v, d, ev = check_broker_search(spec, resolve_fields(member), profile, domain, fetch)
        if v not in ("unknown",) or method == "":
            verdict, detail, evidence, method = v, d, ev, "broker_search"
    if verdict in ("unknown", "blocked"):
        v, d, ev = check_web(db, req, profile, domain, fetch, cfg, search=search)
        if v != "unknown" or method == "":
            verdict, detail, evidence, method = v, d, ev, "web_search"

    db.add(VerificationCheck(request_id=req.id, checked_at=now, method=method or "none", verdict=verdict,
                             evidence=(evidence or "")[:1000] or None, detail=detail[:500]))
    previous = req.last_verdict
    req.last_checked_at, req.last_verdict = now, verdict
    action = _act(req, verdict, detail, evidence, previous, cfg, spec, now)
    db.commit()
    log.info("Verification %s (request %s, %s): %s%s", verdict, req.id, method, detail,
             f" → {action}" if action else "")
    return {"verdict": verdict, "method": method, "detail": detail, "evidence": evidence, "action": action}


def _act(req, verdict, detail, evidence, previous, cfg, spec, now) -> str:
    from ..models.database import RequestStatus
    recheck_days = (cfg or {}).get("scheduler", {}).get("recheck_interval_days", 90)
    st = req.status
    if verdict == "gone":
        if st in (RequestStatus.sent, RequestStatus.submitted, RequestStatus.recheck_due):
            req.status = RequestStatus.confirmed
            req.confirmed_at = now
            req.notes = ((req.notes or "") + f"\nChecked {now:%Y-%m-%d}: the listing is gone.").strip()
            req.recheck_after = now + timedelta(days=recheck_days)
            return "confirmed"
        if st == RequestStatus.confirmed:
            req.recheck_after = max(req.recheck_after or now, now + timedelta(days=recheck_days))
        return ""
    if verdict == "not_found" and st == RequestStatus.confirmed:
        req.recheck_after = max(req.recheck_after or now, now + timedelta(days=min(recheck_days, 30)))
        return ""
    if verdict == "listed":
        if evidence and not req.listing_url:
            req.listing_url = evidence
        window = getattr(spec, "statutory_response_days", 0) or 45
        overdue = req.sent_at is not None and now - req.sent_at > timedelta(days=window)
        if st == RequestStatus.confirmed or (st in (RequestStatus.sent, RequestStatus.submitted) and overdue):
            came_back = st == RequestStatus.confirmed and previous == "gone"
            req.status = RequestStatus.pending
            req.confirmed_at = None
            req.sent_at = None
            what = "came back" if came_back else "is still up"
            req.notes = ((req.notes or "") + f"\nChecked {now:%Y-%m-%d}: the listing {what}"
                         + (f" ({evidence})" if evidence else "") + ". Sending the opt-out again.").strip()
            return "resend_reappeared" if came_back else "resend"
    return ""


# ── Choosing what to check ────────────────────────────────────────────────────

def due(db, cfg: dict, now=None) -> list:
    """Requests to check today, oldest check first, within the daily budget."""
    from ..models.database import RemovalRequest, RequestStatus
    now = now or datetime.utcnow()
    s = settings_of(cfg)
    rows = db.query(RemovalRequest).filter(RemovalRequest.status.in_(
        [RequestStatus.sent, RequestStatus.submitted, RequestStatus.confirmed])).all()
    picked = []
    for r in rows:
        last = r.last_checked_at
        if r.status == RequestStatus.confirmed:
            every = timedelta(days=s["confirmed_every_days"])
            if r.recheck_after and r.recheck_after <= now:
                every = timedelta(0)
        else:
            if not r.sent_at or now - r.sent_at < timedelta(days=s["sent_every_days"]):
                continue
            every = timedelta(days=s["sent_every_days"])
        if last is None or now - last >= every:
            picked.append(r)
    picked.sort(key=lambda r: r.last_checked_at or datetime.min)
    out, per_broker = [], {}
    for r in picked:
        if per_broker.get(r.broker_id, 0) >= s["per_broker"]:
            continue
        per_broker[r.broker_id] = per_broker.get(r.broker_id, 0) + 1
        out.append(r)
        if len(out) >= s["per_day"]:
            break
    return out


def run_daily(db, cfg: dict, fetch=None, search=None, pause: float = 2.0) -> dict:
    s = settings_of(cfg)
    stats = {"checked": 0, "gone": 0, "listed": 0, "not_found": 0, "blocked": 0, "unknown": 0, "resent": 0}
    if not s["enabled"]:
        return stats
    fetch = fetch or fetcher(cfg)
    last_domain = None
    for r in due(db, cfg):
        try:
            dom = r.broker_id
            if pause and last_domain == dom:
                time.sleep(pause)
            last_domain = dom
            res = verify_request(db, r, cfg, fetch=fetch, search=search)
        except Exception as e:
            db.rollback()
            log.info("verification of request %s failed: %s", r.id, e)
            continue
        stats["checked"] += 1
        stats[res["verdict"]] = stats.get(res["verdict"], 0) + 1
        stats["resent"] += 1 if res["action"].startswith("resend") else 0
    return stats


def on_web_hit(db, member, broker, url: str, cfg: dict, fetch=None):
    """
    The weekly web search found a page about this person on a broker. If they
    were already removed there, check whether this is the listing coming back.
    Returns the verify_request result, or None when there's no finished removal.
    """
    from ..models.database import RemovalRequest, RequestStatus
    req = (db.query(RemovalRequest)
             .filter(RemovalRequest.member_id == member.id, RemovalRequest.broker_id == broker.id,
                     RemovalRequest.status == RequestStatus.confirmed)
             .order_by(RemovalRequest.confirmed_at.desc()).first())
    if req is None:
        return None
    if not req.listing_url:
        req.listing_url = url
    return verify_request(db, req, cfg, fetch=fetch)


def summary(db, member_ids: list) -> dict:
    from ..models.database import RemovalRequest, VerificationCheck
    reqs = db.query(RemovalRequest).filter(RemovalRequest.member_id.in_(member_ids)).all() if member_ids else []
    counts = {"gone": 0, "listed": 0, "not_found": 0, "blocked": 0, "unknown": 0}
    for r in reqs:
        if r.last_verdict in counts:
            counts[r.last_verdict] += 1
    ids = [r.id for r in reqs]
    recent = []
    if ids:
        names = {r.id: (r.broker.name if r.broker else "", r.member.full_name if r.member else "") for r in reqs}
        for c in (db.query(VerificationCheck).filter(VerificationCheck.request_id.in_(ids))
                    .order_by(VerificationCheck.checked_at.desc()).limit(15).all()):
            b, m = names.get(c.request_id, ("", ""))
            recent.append({"broker_name": b, "member_name": m, "verdict": c.verdict, "method": c.method,
                           "detail": c.detail, "checked_at": c.checked_at.isoformat() if c.checked_at else None})
    last = max((r.last_checked_at for r in reqs if r.last_checked_at), default=None)
    return {"counts": counts, "recent": recent, "last_checked_at": last.isoformat() if last else None}
