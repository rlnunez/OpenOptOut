"""
Broker confirmation links: find them in replies, click them safely.

Many brokers (Radaris, Spokeo, BeenVerified, Clustrmaps, ...) don't act on an
opt-out until the person clicks a link they email back. Before this module a
reply like that was counted as "confirmed" even though nothing had happened.
Now:

  1. When a reply matches a request (by +address tag or tracking key), we look
     at it: does it ask to click a link, and does it carry one on that broker's
     own website?
  2. If so, the request stays "sent" and a ConfirmationLink is saved
     (encrypted). If it asks for a click but we can't see a usable link, the
     request goes on the checklist ("open the email from … and click the link").
  3. After each email check, saved links are clicked: a plain HTTPS visit
     first, a real browser only if the page has a "Confirm" button to press.
     The page must accept it before the request counts as confirmed.

Safety rules for clicking — a link is only followed when:
  * it's https;
  * its host is the broker's own domain, its parent company's, or a known
    email click-tracker (SendGrid, Mailgun, ...) that redirects to one;
  * every address it resolves to is public (no private, local or reserved
    IPs), checked again on every redirect;
  * it isn't an unsubscribe / preferences / privacy-policy style link.
No cookies, no personal data and no form fields are sent. The URL (it carries a
one-time token) is never written to logs; only its host is.
"""

import html as _html
import ipaddress
import logging
import re
import socket
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
MAX_REDIRECTS = 6
CLICKS_PER_RUN = 15

# Email service click-trackers that wrap links in broker emails. Following one
# is fine; it must still land on the broker's own site.
TRACKER_DOMAINS = (
    "sendgrid.net", "mailgun.org", "mailgun.net", "list-manage.com", "mandrillapp.com",
    "sparkpostmail.com", "mcsv.net", "awstrack.me", "hubspotlinks.com", "hs-sites.com",
    "mailjet.com", "sendibt3.com", "sendinblue.com", "brevo.com", "postmarkapp.com",
    "exacttarget.com", "rs6.net", "klclick.com", "ct.sendgrid.net", "mjt.lu",
)

# The message must ask to confirm/verify AND tell the person to click, or name
# a confirmation link outright. ("Questions? Click here" alone doesn't count.)
_VERIFY = re.compile(r"\b(confirm|verify|validate|activate|complete)\w*\b", re.I)
_CLICK = re.compile(r"\b(click|tap|follow|visit|open|press)\w*\b[^.]{0,60}\b(link|button|below|here|url)\b", re.I)
_NAMED = re.compile(r"\b(confirmation|verification|activation) (link|url|button)\b", re.I)

# A link worth clicking says so in its address or its text.
GOOD_LINK = re.compile(r"confirm|verif|validat|activat|optout|opt-out|opt_out|remov|suppress|delet|token|ticket", re.I)
BAD_LINK = re.compile(
    r"unsubscrib|preferenc|privacy[-_ ]?policy|/privacy/?$|terms|/legal|/help|/faq|support|"
    r"/login|/signin|sign-in|/account|/pricing|/subscribe|facebook\.|twitter\.|instagram\.|linkedin\.|"
    r"\.(png|jpe?g|gif|svg|css|js)(\?|$)|/manage|/report-abuse|mailto:",
    re.I)

SUCCESS_TEXT = re.compile(
    r"(has|have) been (confirmed|verified|removed|processed|received|suppressed|opted out)|"
    r"(request|removal|opt[- ]?out|e-?mail)[^.]{0,30}\b(confirmed|verified|complete|successful|processed)|"
    r"\bsuccess(fully)?\b|\bthank you\b[^.]{0,40}\b(confirm|verif|request|removal)|already (been )?(confirmed|verified|removed)",
    re.I)
FAIL_TEXT = re.compile(
    r"\b(link|token|request)\b[^.]{0,30}\b(expired|invalid|not valid|no longer valid)|"
    r"\bexpired\b|\binvalid (link|token|request)\b|\bsomething went wrong\b|\berror occurred\b|page not found",
    re.I)
CONFIRM_BUTTON = re.compile(r"<(button|input)[^>]*>|<a[^>]+class=\"[^\"]*btn", re.I)
BUTTON_WORDS = re.compile(r"confirm|verify|remove|opt[- ]?out|submit|continue|yes", re.I)

REASONS = {
    "no_link":       "The email asks for a click, but OpenOptOut couldn't see the link in it.",
    "off_site":      "The link goes to a different website than {broker}, so OpenOptOut won't open it for you.",
    "unreachable":   "{broker}'s confirmation page didn't load after a few tries.",
    "rejected":      "{broker}'s page said the link didn't work (it may have expired).",
    "needs_button":  "{broker}'s page needs a button pressed that OpenOptOut couldn't find.",
    "unclear":       "{broker}'s page loaded, but didn't say whether it worked.",
    "turned_off":    "Clicking confirmation links automatically is turned off.",
}


def settings_of(cfg: dict) -> dict:
    s = dict((cfg or {}).get("confirm_links") or {})
    s.setdefault("auto_click", True)
    s.setdefault("use_browser", True)
    return s


# ── Reading the email ─────────────────────────────────────────────────────────

_HREF = re.compile(r"<a\b[^>]*?\bhref\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", re.I | re.S)
_BARE = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.I)
_TAGS = re.compile(r"<[^>]+>")


def extract_links(text: str = "", html: str = "") -> list:
    """[{url, text}] from an email's HTML anchors and plain-text URLs, in order, de-duplicated."""
    out, seen = [], set()

    def add(url, label=""):
        url = _html.unescape((url or "").strip()).rstrip(".,;:!>")
        if not url.lower().startswith(("http://", "https://")) or url in seen:
            return
        seen.add(url)
        out.append({"url": url[:2000], "text": " ".join(_TAGS.sub(" ", _html.unescape(label or "")).split())[:200]})

    for _, href, label in _HREF.findall(html or ""):
        add(href, label)
    for u in _BARE.findall(_TAGS.sub(" ", html or "")) + _BARE.findall(text or ""):
        add(u)
    return out[:60]


def asks_for_click(subject: str, text: str) -> bool:
    t = f"{subject or ''} \n {text or ''}"
    return bool(_NAMED.search(t) or (_VERIFY.search(t) and _CLICK.search(t)))


def _host(url: str) -> str:
    h = (urlparse(url).hostname or "").lower().strip(".")
    return h


def _registrable(host: str) -> str:
    from .listing_finder import registrable_domain
    return registrable_domain(host)


def _on(host: str, domains) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains if d)


def allowed_domains(db, req) -> set:
    """The broker's own domains for this request: its site, its parent's site
    and opt-out inbox, and the listing the person pasted."""
    from .listing_finder import _host as lf_host
    out = set()
    b = req.broker
    cands = [getattr(req, "listing_url", "")]
    if b is not None:
        cands += [b.opt_out_url, b.name]
        if b.parent is not None:
            cands += [b.parent.website, (b.parent.optout_email or "").split("@")[-1]]
        try:
            from ..plugins.broker_addon import get_broker_spec_for_broker
            spec = get_broker_spec_for_broker(db, b)
            if spec is not None:
                cands += [getattr(spec, "contact_email", "").split("@")[-1],
                          getattr(spec, "search_url", ""), getattr(spec, "opt_out_url", "")]
        except Exception:
            pass
        # Hosted privacy forms (OneTrust, TrustArc) send their own verification links.
        try:
            from ..models.database import PrivacyPage
            cands += [p.url for p in db.query(PrivacyPage).filter(
                PrivacyPage.broker_id == b.id, PrivacyPage.status.in_(("active", "approved")),
                PrivacyPage.kind.in_(("hosted_onetrust", "hosted_trustarc", "request_form"))).all()]
        except Exception:
            pass
    for c in cands:
        h = lf_host(c or "")
        if h:
            out.add(_registrable(h))
    return out


def pick_link(links: list, domains: set):
    """
    Best confirmation link among `links`, or (None, reason). A link must be on
    the broker's domains (or a click-tracker) and look like a confirmation link.
    """
    best, best_score, saw_offsite = None, -1, False
    for ln in links or []:
        url, label = ln.get("url", ""), ln.get("text", "")
        host = _host(url)
        if not host or BAD_LINK.search(url) or BAD_LINK.search(label):
            continue
        good = bool(GOOD_LINK.search(url) or GOOD_LINK.search(label))
        if not good:
            continue
        if not url.lower().startswith("https://"):
            continue
        if _on(host, domains):
            score = 10
        elif _on(host, TRACKER_DOMAINS):
            score = 5
        else:
            saw_offsite = True
            continue
        score += 1 if GOOD_LINK.search(label) else 0
        if score > best_score:
            best, best_score = url, score
    if best:
        return best, None
    return None, ("off_site" if saw_offsite else "no_link")


# ── Recording what a reply asked for ──────────────────────────────────────────

def handle_reply(db, reqs: list, subject: str, text: str, links: list, sender: str = "",
                 links_known: bool = True, now=None) -> bool:
    """
    A broker reply matched these requests. If it's asking for a confirmation
    click, save the link (or a checklist item) for each request and return True
    so the caller does NOT mark them confirmed. Returns False for a normal
    reply ("we've removed you", "we received your request").

    `links_known` is False when the inbox plugin couldn't give us the links
    (older plugins send only a snippet); then a "please click" email goes on
    the checklist instead of being clicked.
    """
    from ..models.database import ConfirmationLink
    now = now or datetime.utcnow()
    if not reqs:
        return False
    domains = set()
    for r in reqs:
        domains |= allowed_domains(db, r)
    url, why = pick_link(links, domains) if links else (None, "no_link")
    on_site = url is not None and _on(_host(url), domains)
    asking = asks_for_click(subject, text)
    # A clear confirmation link on the broker's own site counts even when the
    # wording is unusual; anything else needs the email to actually ask.
    if not asking and not on_site:
        return False
    for r in reqs:
        existing = (db.query(ConfirmationLink)
                      .filter(ConfirmationLink.request_id == r.id,
                              ConfirmationLink.status.in_(("pending", "needs_person"))).first())
        row = existing or ConfirmationLink(request_id=r.id)
        row.sender = (sender or "")[:255]
        row.found_at = now
        row.attempts = 0
        if url:
            row.url, row.host, row.status, row.reason = url, _host(url), "pending", None
        else:
            row.url, row.host, row.status = None, None, "needs_person"
            row.reason = why if links_known else "no_link"
        if existing is None:
            db.add(row)
    db.commit()
    log.info("Confirmation %s for %d request(s) (host=%s)", "link saved" if url else "needed by hand",
             len(reqs), _host(url) if url else "-")
    return True


# ── Clicking ──────────────────────────────────────────────────────────────────

from .dns_guard import is_public_ip, public_host, safe_dns_context


def _verdict(status: int, body: str):
    """'ok' | 'rejected' | 'needs_button' | 'unclear' from a landing page."""
    text = _TAGS.sub(" ", body or "")
    if status >= 400 or FAIL_TEXT.search(text):
        return "rejected" if status < 500 else "unreachable"
    if SUCCESS_TEXT.search(text):
        return "ok"
    for m in CONFIRM_BUTTON.finditer(body or ""):
        tail = (body or "")[m.start(): m.start() + 300]
        if BUTTON_WORDS.search(_TAGS.sub(" ", tail) + " " + m.group(0)):
            return "needs_button"
    return "unclear"


def http_visit(url: str, domains: set, get=None, resolve=None):
    """
    Follow `url` with plain GETs. Returns (verdict, final_url). Every hop must
    be https, public, and on the broker's domains or a click-tracker; the final
    page must be on the broker's domains.
    DNS resolution at socket connection is pinned to public addresses via safe_dns_context.
    """
    resolve = resolve or public_host
    if get is None:
        import requests

        def get(u):
            with safe_dns_context():
                r = requests.get(u, timeout=15, allow_redirects=False, stream=True,
                                 headers={"User-Agent": "Mozilla/5.0 (OpenOptOut confirmation)",
                                          "Accept": "text/html,*/*"})
                body = r.raw.read(400_000, decode_content=True).decode(r.encoding or "utf-8", "replace") \
                    if r.status_code < 300 else ""
                return r.status_code, r.headers.get("Location", ""), body
    cur = url
    for _ in range(MAX_REDIRECTS + 1):
        host = _host(cur)
        if urlparse(cur).scheme != "https" or not host:
            return "off_site", cur
        if not (_on(host, domains) or _on(host, TRACKER_DOMAINS)):
            return "off_site", cur
        if not resolve(host):
            return "off_site", cur
        try:
            status, location, body = get(cur)
        except Exception as e:
            log.info("Confirmation visit to %s failed: %s", host, type(e).__name__)
            return "unreachable", cur
        if status in (301, 302, 303, 307, 308) and location:
            cur = urljoin(cur, location)
            continue
        if not _on(host, domains):
            return "off_site", cur      # ended on a tracker, not the broker
        return _verdict(status, body), cur
    return "unreachable", cur


async def _browser_press(url: str, domains: set) -> str:
    """Open the page in a headless browser and press its confirm button."""
    from playwright.async_api import async_playwright
    from .proxy import get_proxy_for_context

    async def guard(route):
        req = route.request
        host = _host(req.url)
        if req.is_navigation_request() and not (_on(host, domains) or _on(host, TRACKER_DOMAINS)):
            return await route.abort()
        try:
            if host and not public_host(host):
                return await route.abort()
        except Exception:
            return await route.abort()
        await route.continue_()

    from .gpc import apply_gpc_headers, apply_gpc_to_context
    async with async_playwright() as p:
        ctx_args = {}
        proxy = get_proxy_for_context()
        if proxy:
            ctx_args["proxy"] = proxy
        ctx_args = apply_gpc_headers(ctx_args)
        browser = await p.firefox.launch(headless=True)
        try:
            ctx = await browser.new_context(**ctx_args)
            await apply_gpc_to_context(ctx)
            await ctx.route("**/*", guard)
            page = await ctx.new_page()
            resp = await page.goto(url, timeout=20000, wait_until="domcontentloaded")
            if resp:
                try:
                    server = await resp.server_addr() if callable(getattr(resp, "server_addr", None)) else None
                    if server and server.get("ipAddress") and not is_public_ip(server["ipAddress"]):
                        return "unreachable"
                except Exception:
                    pass
            body = await page.content()
            if SUCCESS_TEXT.search(_TAGS.sub(" ", body)):
                return "ok"
            loc = page.get_by_role("button", name=re.compile(r"confirm|verify|remove|opt.?out|submit|yes", re.I))
            if await loc.count() == 0:
                loc = page.locator("input[type=submit], a.btn, a.button").filter(
                    has_text=re.compile(r"confirm|verify|remove|opt.?out|submit|yes", re.I))
            if await loc.count() == 0:
                return "needs_button"
            await loc.first.click(timeout=8000)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            if not _on(_host(page.url), domains):
                return "off_site"
            return _verdict(200, await page.content())
        finally:
            await browser.close()


def browser_press(url: str, domains: set) -> str:
    import asyncio
    try:
        return asyncio.run(_browser_press(url, domains))
    except ImportError:
        return "needs_button"
    except Exception as e:
        log.info("Browser confirmation on %s failed: %s", _host(url), type(e).__name__)
        return "unreachable"


def _confirm_request(db, req, cfg: dict, now):
    from ..models.database import RequestStatus, EmailLog
    if req.status not in (RequestStatus.sent, RequestStatus.submitted):
        return
    req.status = RequestStatus.confirmed
    req.confirmed_at = now
    days = (cfg or {}).get("scheduler", {}).get("recheck_interval_days", 90)
    req.recheck_after = now + timedelta(days=days)
    db.add(EmailLog(request_id=req.id, direction="received",
                    subject="Confirmation link clicked", body_snippet="", matched_key=req.request_key))
    try:
        if req.broker and req.broker.parent_company_id:
            from . import parent_company as pcmod
            pcmod.record_confirmation(db, req.broker.parent_company_id)
    except Exception:
        pass
    try:
        from ..plugins.hooks import fire_event
        fire_event("confirmation_received", entity_id=str(req.id),
                   data={"broker": req.broker.name if req.broker else "", "via": "link_click"})
    except Exception:
        pass


def click_pending(db, cfg: dict, visit=None, press=None, now=None) -> dict:
    """Click saved confirmation links. Called after every email check."""
    from ..models.database import ConfirmationLink, RemovalRequest, RequestStatus
    now = now or datetime.utcnow()
    s = settings_of(cfg)
    stats = {"clicked": 0, "needs_person": 0, "retry": 0}
    rows = (db.query(ConfirmationLink).filter(ConfirmationLink.status == "pending")
              .order_by(ConfirmationLink.found_at).limit(CLICKS_PER_RUN).all())
    # Several requests (a parent company's sites) can share one link: click once.
    done_urls = {}
    for row in rows:
        req = db.query(RemovalRequest).filter(RemovalRequest.id == row.request_id).first()
        if req is None or req.status not in (RequestStatus.sent, RequestStatus.submitted):
            row.status = "done"; continue
        if not s["auto_click"]:
            row.status, row.reason = "needs_person", "turned_off"
            stats["needs_person"] += 1; continue
        domains = allowed_domains(db, req)
        url = row.url or ""
        if url in done_urls:
            verdict = done_urls[url]
        else:
            row.attempts = (row.attempts or 0) + 1
            verdict, _ = (visit or http_visit)(url, domains)
            if verdict == "needs_button" and s["use_browser"]:
                verdict = (press or browser_press)(url, domains)
            done_urls[url] = verdict
        if verdict == "ok":
            row.status, row.clicked_at, row.reason = "clicked", now, None
            _confirm_request(db, req, cfg, now)
            stats["clicked"] += 1
        elif verdict == "unreachable" and (row.attempts or 0) < MAX_ATTEMPTS:
            stats["retry"] += 1
        else:
            row.status, row.reason = "needs_person", verdict if verdict in REASONS else "unclear"
            stats["needs_person"] += 1
    db.commit()
    return stats


# ── For the checklist ─────────────────────────────────────────────────────────

def instruction(row, broker_name: str, inbox: str = "") -> str:
    why = REASONS.get(row.reason or "", REASONS["unclear"]).format(broker=broker_name)
    where = f" in {inbox}" if inbox else ""
    who = f"from {row.sender}" if row.sender else f"from {broker_name}"
    if row.url and row.reason != "off_site":
        return f"{why} Open the link below and follow what the page says, then press \"I've confirmed it\"."
    return (f"{why} Find the email {who}{where}, click the confirmation link in it, "
            f"then press \"I've confirmed it\".")


def mark_done(db, row, cfg: dict, who: str, now=None):
    from ..models.database import RemovalRequest
    now = now or datetime.utcnow()
    row.status, row.clicked_at = "done", now
    req = db.query(RemovalRequest).filter(RemovalRequest.id == row.request_id).first()
    if req is not None:
        _confirm_request(db, req, cfg, now)
        req.notes = ((req.notes or "") + f"\nConfirmation link clicked by {who} on {now:%Y-%m-%d}.").strip()
    db.commit()
