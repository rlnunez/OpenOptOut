"""
Privacy-request page finder.

For brokers nobody has written opt-out steps for, look at the broker's own
website and find where a person asks it to delete their data:

  hosted_onetrust   a OneTrust privacy-request web form
  hosted_trustarc   a TrustArc privacy-request form
  hosted_other      another hosted privacy platform (Osano, Securiti, Ketch,
                    Transcend, DataGrail...): recorded, filled by a person
  request_form      the company's own page with a form that asks for an email
                    address and talks about deleting / opting out
  optout_page       a page about opting out or "Do Not Sell", without a form
                    we can see (often it links on to one)
  policy            the privacy policy, as a last resort for the checklist
  email             a privacy / opt-out email address found on those pages;
                    only used for email opt-outs after an admin approves it

How it looks: the home page's links (footers carry "Do Not Sell or Share",
"Your Privacy Choices", "Privacy Request"), then the few best candidates, then
well-known addresses (/privacy, /opt-out, /do-not-sell, ...) if nothing
turned up. Only public https pages on the broker's own domain (or a known
hosted privacy platform) are fetched; no personal data is sent, no forms are
submitted, at most MAX_FETCHES pages per broker.

What uses the results: interpreter/hosted_forms.py builds opt-out steps for
hosted and in-house forms; the checklist names the page for everything else.
"""

import html as _html
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

log = logging.getLogger(__name__)

MAX_FETCHES = 8
MAX_BYTES = 1_500_000
RECHECK_DAYS = 30

KINDS = ("hosted_onetrust", "hosted_trustarc", "hosted_other", "request_form",
         "optout_page", "policy", "email")
# Which finding the opt-out uses, best first.
PRIORITY = {k: i for i, k in enumerate(KINDS)}
FILLABLE = ("hosted_onetrust", "hosted_trustarc", "request_form")

HOSTED = (
    ("hosted_onetrust", re.compile(r"(^|\.)(privacyportal(-[a-z0-9]+)?\.onetrust\.com|my\.onetrust\.com|onetrust\.com)$", re.I),
     re.compile(r"/webform/|/request|/dsar|privacyportal", re.I)),
    ("hosted_trustarc", re.compile(r"(^|\.)(submit-irm\.trustarc\.com|trustarc\.com)$", re.I),
     re.compile(r"/services/validation/|/irm|/dsr|submit-irm", re.I)),
    ("hosted_other", re.compile(r"(^|\.)(osano\.com|securiti\.ai|ketch\.com|transcend\.io|datagrail\.io|"
                                r"truyo\.com|privacy\.ketch\.com|mineos\.ai|didomi\.io|wirewheel\.io)$", re.I),
     re.compile(r".", re.I)),
)

LINK_WORDS = [
    (re.compile(r"do[\s-]*not[\s-]*sell|don.?t[\s-]*sell|do[\s-]*not[\s-]*share", re.I), 9),
    (re.compile(r"your[\s-]*privacy[\s-]*choices|privacy[\s-]*choices", re.I), 9),
    (re.compile(r"privacy[\s-]*request|data[\s-]*request|consumer[\s-]*request|dsar|data[\s-]*subject", re.I), 9),
    (re.compile(r"opt[\s-]*out|optout|suppress", re.I), 8),
    (re.compile(r"remove[\s-]*my|removal|delete[\s-]*my|deletion|erase", re.I), 8),
    (re.compile(r"ccpa|cpra|privacy[\s-]*rights|consumer[\s-]*rights|your[\s-]*rights", re.I), 6),
    (re.compile(r"privacy[\s-]*(policy|notice|center|centre)|/privacy\b", re.I), 3),
]
NOT_THIS = re.compile(r"cookie[\s-]*(policy|settings|preferences)|terms|careers|login|sign[\s-]*in|"
                      r"blog|press|facebook|twitter|instagram|linkedin|youtube|apple\.com|google\.com", re.I)
WELL_KNOWN = ("/opt-out", "/optout", "/do-not-sell", "/privacy-request", "/ccpa", "/removal",
              "/privacy", "/privacy-policy")

FORM_TALK = re.compile(r"delet|remov|opt[\s-]*out|do not sell|do not share|privacy request|"
                       r"data request|suppress|erase", re.I)
EMAIL_RE = re.compile(r"\b([a-z0-9._%+-]+)@([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b", re.I)
PRIVACY_LOCAL = re.compile(r"privacy|optout|opt-out|opt_out|dsar|ccpa|gdpr|dpo|removal|remove|"
                           r"suppress|delete|dataprotection|data\.protection|legal", re.I)

_A = re.compile(r"<a\b[^>]*?\bhref\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", re.I | re.S)
_IFRAME = re.compile(r"<iframe\b[^>]*?\bsrc\s*=\s*([\"'])(.*?)\1", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _text(s: str) -> str:
    return " ".join(_TAGS.sub(" ", _html.unescape(s or "")).split())


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().strip(".")


def hosted_kind(url: str) -> str:
    """'hosted_onetrust' / 'hosted_trustarc' / 'hosted_other', or ''."""
    host = _host(url)
    for kind, host_re, path_re in HOSTED:
        if host and host_re.search(host) and path_re.search(url):
            return kind
    return ""


def _same_site(url: str, domain: str) -> bool:
    h = _host(url)
    return h == domain or h.endswith("." + domain)


def links_in(page_html: str, base_url: str) -> list:
    """[(absolute url, text)] for every link and iframe on a page."""
    out, seen = [], set()
    for _, href, label in _A.findall(page_html or ""):
        href = _html.unescape(href.strip())
        if href.lower().startswith(("javascript:", "#", "tel:")):
            continue
        url = href if href.lower().startswith("mailto:") else urljoin(base_url, href)
        if url not in seen:
            seen.add(url); out.append((url, _text(label)[:200]))
    for _, src in _IFRAME.findall(page_html or ""):
        url = urljoin(base_url, _html.unescape(src.strip()))
        if url not in seen:
            seen.add(url); out.append((url, "embedded form"))
    return out


def score_link(url: str, label: str) -> int:
    hk = hosted_kind(url)
    if hk:
        return 20 if hk != "hosted_other" else 12
    hay = f"{label} {urlparse(url).path}"
    if NOT_THIS.search(hay) and not re.search(r"do not sell|opt.?out", hay, re.I):
        return 0
    return max([w for rx, w in LINK_WORDS if rx.search(hay)] or [0])


def privacy_emails(page_html: str, domain: str) -> list:
    """Privacy-looking addresses on the broker's own domain."""
    found = []
    for local, dom in EMAIL_RE.findall(_html.unescape(page_html or "")):
        addr = f"{local}@{dom}".lower()
        if (dom.lower() == domain or dom.lower().endswith("." + domain)) and PRIVACY_LOCAL.search(local) \
                and addr not in found:
            found.append(addr)
    return found


def classify_page(url: str, page_html: str) -> str:
    """What a fetched page is: a hosted form, a request form, an opt-out page, a policy, or ''."""
    hk = hosted_kind(url)
    if hk:
        return hk
    body = page_html or ""
    text = _text(body)
    has_form = bool(re.search(r"<form\b", body, re.I)) or "type=\"email\"" in body.lower()
    asks_email = bool(re.search(r"type\s*=\s*[\"']email|name\s*=\s*[\"'][^\"']*e-?mail", body, re.I))
    if has_form and asks_email and FORM_TALK.search(text):
        return "request_form"
    if re.search(r"do not sell|do not share|opt[\s-]*out|privacy request|delete your|request (the )?deletion",
                 text, re.I):
        return "optout_page"
    if re.search(r"privacy (policy|notice)", text, re.I):
        return "policy"
    return ""


# ── Fetching ──────────────────────────────────────────────────────────────────

def _allowed(url: str, domain: str) -> bool:
    if urlparse(url).scheme != "https":
        return False
    return _same_site(url, domain) or bool(hosted_kind(url))


def http_get(url: str, domain: str):
    """(final_url, status, html) — https, public addresses only, redirects re-checked."""
    import requests
    from .confirm_links import public_host
    cur = url
    for _ in range(5):
        if not _allowed(cur, domain) or not public_host(_host(cur)):
            return cur, 0, ""
        r = requests.get(cur, timeout=15, allow_redirects=False, stream=True,
                         headers={"User-Agent": "Mozilla/5.0 (OpenOptOut privacy-page finder)",
                                  "Accept": "text/html,*/*"})
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            cur = urljoin(cur, r.headers["Location"])
            continue
        body = r.raw.read(MAX_BYTES, decode_content=True).decode(r.encoding or "utf-8", "replace") \
            if r.status_code < 400 else ""
        return cur, r.status_code, body
    return cur, 0, ""


def find(domain: str, fetch=None) -> dict:
    """
    Look at one broker website. Returns {"findings": [{url, kind, label, score}],
    "fetched": n, "blocked": bool}. `fetch(url, domain) -> (final_url, status, html)`.
    """
    fetch = fetch or http_get
    findings, seen_pages, fetched, blocked = {}, set(), 0, False

    def add(url, kind, label, score):
        key = (url.split("#")[0].rstrip("/"), kind)
        if key not in findings or findings[key]["score"] < score:
            findings[key] = {"url": url.split("#")[0], "kind": kind, "label": (label or "")[:300], "score": score}

    def visit(url):
        nonlocal fetched, blocked
        if fetched >= MAX_FETCHES or url in seen_pages:
            return None
        seen_pages.add(url)
        fetched += 1
        try:
            final, status, body = fetch(url, domain)
        except Exception as e:
            log.info("privacy finder: %s unreachable (%s)", _host(url), type(e).__name__)
            return None
        if status in (403, 429, 503):
            blocked = True
        if status >= 400 or not body:
            return None
        m = _TITLE.search(body)
        title = _text(m.group(1)) if m else ""
        kind = classify_page(final, body)
        if kind:
            add(final, kind, title, 15 if kind in FILLABLE else 5)
        for addr in privacy_emails(body, domain):
            add("mailto:" + addr, "email", addr, 4)
        return final, body

    home = visit(f"https://{domain}/") or visit(f"https://www.{domain}/")
    candidates = []
    if home:
        for url, label in links_in(home[1], home[0]):
            if url.lower().startswith("mailto:"):
                addr = url[7:].split("?")[0].lower()
                if addr.split("@")[-1].endswith(domain) and PRIVACY_LOCAL.search(addr.split("@")[0]):
                    add("mailto:" + addr, "email", addr, 4)
                continue
            s = score_link(url, label)
            if s and (_allowed(url, domain)):
                hk = hosted_kind(url)
                if hk:
                    add(url, hk, label, s)
                candidates.append((s, url, label))
    candidates.sort(key=lambda c: -c[0])
    for s, url, label in candidates[:4]:
        res = visit(url)
        if not res:
            continue
        for sub, sub_label in links_in(res[1], res[0]):
            hk = hosted_kind(sub)
            if hk:
                add(sub, hk, sub_label or label, 20)
            elif _allowed(sub, domain) and score_link(sub, sub_label) >= 8 and len(seen_pages) < MAX_FETCHES:
                visit(sub)
    if not any(f["kind"] != "email" for f in findings.values()):
        for path in WELL_KNOWN:
            if fetched >= MAX_FETCHES:
                break
            visit(f"https://{domain}{path}")
    out = sorted(findings.values(), key=lambda f: (PRIORITY.get(f["kind"], 9), -f["score"]))
    return {"findings": out, "fetched": fetched, "blocked": blocked}


# ── Saving and using results ──────────────────────────────────────────────────

def run_for_broker(db, broker, fetch=None, now=None) -> dict:
    from ..models.database import PrivacyPage
    from .listing_finder import broker_domain, registrable_domain
    now = now or datetime.utcnow()
    host = broker_domain(broker)
    if not host:
        return {"findings": [], "fetched": 0, "blocked": False, "error": "no website for this broker"}
    domain = registrable_domain(host)
    res = find(domain, fetch=fetch)
    existing = {(p.url, p.kind): p for p in db.query(PrivacyPage).filter(PrivacyPage.broker_id == broker.id).all()}
    new = []
    for f in res["findings"]:
        row = existing.get((f["url"], f["kind"]))
        if row is None:
            db.add(PrivacyPage(broker_id=broker.id, url=f["url"][:1000], kind=f["kind"],
                               label=f["label"], score=f["score"], found_at=now))
            new.append(f)
        elif row.status != "dismissed":
            row.label, row.score, row.found_at = f["label"], f["score"], now
    broker.privacy_checked_at = now
    _note_found(db, broker, new)
    db.commit()
    return res


FOUND_WORDS = {
    "hosted_onetrust": "a privacy request form (OneTrust)",
    "hosted_trustarc": "a privacy request form (TrustArc)",
    "hosted_other": "a privacy request form",
    "request_form": "a privacy request form",
    "optout_page": "an opt-out page",
    "email": "a privacy email address",
}


def _note_found(db, broker, new: list) -> None:
    """Tell admins (Broker updates) what the finder newly found on this
    broker's website: forms OpenOptOut can fill, opt-out pages, and privacy
    email addresses that wait for an admin's approval. A privacy policy alone
    isn't worth a note."""
    kinds = sorted({f["kind"] for f in new if f["kind"] in FOUND_WORDS}, key=lambda k: PRIORITY.get(k, 9))
    if not kinds:
        return
    from .broker_updates import record
    what = [FOUND_WORDS[k] for k in kinds]
    seen = []
    what = [w for w in what if not (w in seen or seen.append(w))]
    title = f"Found {' and '.join(what) if len(what) < 3 else ', '.join(what[:-1]) + ' and ' + what[-1]} on {broker.name}'s website"
    notes = []
    if any(k in FILLABLE for k in kinds):
        notes.append("OpenOptOut can fill in the request form for this broker's opt-outs.")
    if "email" in kinds:
        notes.append("A found email address is only used after an admin approves it (Brokers page, \"Privacy pages found on brokers' websites\").")
    record(db, "privacy_found", title, " ".join(notes) or "See \"Privacy pages found on brokers' websites\" on the Brokers page.",
           broker_id=broker.id)


def best(db, broker, kinds=None):
    """The best active finding for this broker (optionally of these kinds)."""
    from ..models.database import PrivacyPage
    rows = db.query(PrivacyPage).filter(PrivacyPage.broker_id == broker.id,
                                        PrivacyPage.status.in_(("active", "approved"))).all()
    rows = [r for r in rows if r.kind != "email" and (kinds is None or r.kind in kinds)]
    rows.sort(key=lambda r: (PRIORITY.get(r.kind, 9), -(r.score or 0)))
    return rows[0] if rows else None


def needs_check(db, limit: int = 20, now=None) -> list:
    """Brokers with no opt-out steps whose site hasn't been looked at lately."""
    from ..models.database import Broker, BrokerScript, BrokerHealth, OptOutMethod
    now = now or datetime.utcnow()
    scripted = {s.broker_id for s in db.query(BrokerScript).all()}
    defunct = {h.broker_id for h in db.query(BrokerHealth).filter(BrokerHealth.defunct.is_(True)).all()}
    out = []
    for b in db.query(Broker).filter(Broker.is_test.isnot(True)).all():
        if b.plugin_id or b.id in scripted or b.id in defunct or (b.origin or "") == "state_program":
            continue
        if b.method == OptOutMethod.email:
            continue
        if b.privacy_checked_at and now - b.privacy_checked_at < timedelta(days=RECHECK_DAYS):
            continue
        out.append(b)
    out.sort(key=lambda b: (b.privacy_checked_at or datetime.min, -(b.priority or 3)))
    return out[:limit]


def run_daily(db, limit: int = 20, fetch=None) -> dict:
    stats = {"checked": 0, "found": 0}
    for b in needs_check(db, limit=limit):
        try:
            res = run_for_broker(db, b, fetch=fetch)
            stats["checked"] += 1
            stats["found"] += 1 if any(f["kind"] != "email" for f in res["findings"]) else 0
        except Exception as e:
            db.rollback()
            log.info("privacy finder failed for broker %s: %s", b.id, e)
    return stats


def check_new_site(db, broker, fetch=None) -> dict:
    """
    A broker OpenOptOut created from a pasted listing: look at its website
    right away. With a request form it can fill, its waiting opt-outs go back
    into the queue as automated; otherwise their checklist items name the page.
    """
    from ..models.database import RemovalRequest, RequestStatus, OptOutMethod
    from .listing_finder import UNKNOWN_BROKER_NOTE
    res = run_for_broker(db, broker, fetch=fetch)
    ours = (broker.notes or "").startswith(UNKNOWN_BROKER_NOTE[:40])
    page = best(db, broker)
    if page is None:
        return res
    waiting = db.query(RemovalRequest).filter(RemovalRequest.broker_id == broker.id,
                                              RemovalRequest.status == RequestStatus.needs_manual).all()
    if page.kind in FILLABLE and ours:
        broker.method = OptOutMethod.form
        broker.opt_out_url = page.url
        for r in waiting:
            r.status = RequestStatus.pending
            r.notes = f"OpenOptOut found {broker.name}'s privacy request form and will fill it in."
    else:
        for r in waiting:
            what = "privacy policy" if page.kind == "policy" else "privacy request page"
            r.notes = ((r.notes or "") + f"\nOpenOptOut found {broker.name}'s {what}: {page.url}").strip()
    db.commit()
    res["used"] = page.kind
    return res


def approve_email(db, page, who: str):
    """An admin confirmed a found address: use it for this broker's email opt-outs."""
    from ..models.database import Broker
    addr = page.url[7:] if page.url.startswith("mailto:") else page.url
    b = db.query(Broker).filter(Broker.id == page.broker_id).first()
    note = f"Opt-out email {addr} (found on its website, approved by {who} on {datetime.utcnow():%Y-%m-%d})"
    # The engine reads the first address in a broker's notes, so this one goes first.
    b.notes = note + ("\n" + b.notes if b.notes else "")
    page.status = "approved"
    db.commit()
    return addr
