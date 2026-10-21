"""
Webhook notifications: short messages to ntfy, Gotify, Slack, Microsoft Teams,
Discord, Home Assistant, or any service that takes JSON.

What a message may hold is fixed here, not by the caller: an event's title, a
sentence in plain words, and counts or the names of brokers and plugins. Never
a family member's name, email, phone, address or date of birth, and never a
link that leads to one. notify() refuses any detail that isn't on the allowed
list for its event, and every message is checked against the saved personal
details before it leaves (the same check the AI helpers use).

Settings (settings.json "observability.webhooks"), set by a super admin:
  [{"id", "name", "kind", "url_enc", "secret_enc", "events": [...], "enabled",
    "last_status", "last_at"}]
The URL is stored encrypted: for Slack, Discord, Teams and Home Assistant the
address itself is the secret.

Sending happens on a background thread and never raises into the caller.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import queue
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

log = logging.getLogger(__name__)

KINDS = {
    "ntfy":          "ntfy",
    "gotify":        "Gotify",
    "slack":         "Slack",
    "teams":         "Microsoft Teams",
    "discord":       "Discord",
    "homeassistant": "Home Assistant",
    "json":          "Other (JSON)",
}

# event -> (title, allowed detail keys, minutes before the same event may be
# sent again for the same key; 0 = always)
EVENTS: Dict[str, tuple] = {
    "run_finished":        ("Opt-outs sent", {"sent", "failed", "needs_you"}, 0),
    "needs_you":           ("Something needs a person", {"captchas", "checklist"}, 240),
    "broker_turned_off":   ("A broker was turned off", {"broker", "failures"}, 0),
    "listing_back":        ("Listings came back", {"count"}, 0),
    "backup_failed":       ("A backup didn't work", {"destination"}, 60),
    "certificate_expiring": ("A certificate needs attention", {"source", "days"}, 0),
    "plugin_turned_off":   ("A plugin was turned off", {"plugin"}, 0),
    "health_problem":      ("OpenOptOut needs attention", {"checks"}, 0),
    "health_ok":           ("OpenOptOut is healthy again", set(), 0),
    "test":                ("Test message", set(), 0),
}
DEFAULT_EVENTS = ["run_finished", "needs_you", "broker_turned_off", "listing_back",
                  "backup_failed", "certificate_expiring", "plugin_turned_off",
                  "health_problem", "health_ok"]

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")
_SAFE_VALUE = re.compile(r"^[\w .,:;()'&/+-]{0,120}$")

_last_sent: Dict[tuple, float] = {}
_queue: "queue.Queue" = queue.Queue(maxsize=500)
_worker: Optional[threading.Thread] = None
_lock = threading.Lock()
STATS = {"sent": 0, "failed": 0, "dropped": 0, "refused": 0}

# Replaced in tests.
TRANSPORT: Optional[Callable] = None


def _encrypt(v: str) -> str:
    from .oauth_engine import _encrypt as e
    return e(v) if v else ""


def _decrypt(v: str) -> str:
    from .oauth_engine import _decrypt as d
    return d(v) if v else ""


def _settings() -> dict:
    from .settings_store import load_settings
    return load_settings()


def targets(settings: Optional[dict] = None) -> List[dict]:
    s = settings if settings is not None else _settings()
    return list(((s.get("observability") or {}).get("webhooks")) or [])


def public_view(t: dict) -> dict:
    """A target as the settings page shows it: the service's host, never the
    full address or the secret."""
    url = _decrypt(t.get("url_enc", ""))
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or re.sub(r"^https?://", "", url).split("/")[0]) if url else ""
    return {"id": t["id"], "name": t.get("name", ""), "kind": t.get("kind", "json"),
            "host": host, "has_secret": bool(t.get("secret_enc")), "events": t.get("events", []),
            "enabled": bool(t.get("enabled", True)),
            "last_status": t.get("last_status", ""), "last_at": t.get("last_at", "")}


def make_target(data: dict, old: Optional[dict] = None) -> dict:
    """A stored target from what the settings page sent. Raises ValueError
    in plain words."""
    old = old or {}
    kind = data.get("kind") or old.get("kind") or "json"
    if kind not in KINDS:
        raise ValueError("Choose a service from the list.")
    url = (data.get("url") or "").strip()
    if not url and not old.get("url_enc"):
        raise ValueError("Paste the address the service gave you.")
    if url and not re.match(r"^https?://[^\s/]+", url):
        raise ValueError("The address must start with https:// (or http:// on your own network).")
    if url:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower().strip()
        if host in {"169.254.169.254", "169.254.170.2", "metadata.google.internal", "metadata", "instance-data", "100.100.100.200"} or host.startswith("169.254."):
            raise ValueError("The webhook address cannot target cloud metadata endpoints.")
    events = data.get("events")
    events = [e for e in (events if events is not None else old.get("events", DEFAULT_EVENTS)) if e in EVENTS and e != "test"]
    secret = data.get("secret")
    return {
        "id": old.get("id") or uuid.uuid4().hex[:12],
        "name": (data.get("name") or old.get("name") or KINDS[kind])[:60],
        "kind": kind,
        "url_enc": _encrypt(url) if url else old.get("url_enc", ""),
        "secret_enc": (_encrypt(secret) if secret else "") if secret is not None else old.get("secret_enc", ""),
        "events": events,
        "enabled": bool(data.get("enabled", old.get("enabled", True))),
        "last_status": old.get("last_status", ""), "last_at": old.get("last_at", ""),
    }


# ── Building messages ─────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    return _PHONE.sub("[number]", _EMAIL.sub("[email]", str(text)))


_BLOCKED = {"at": 0.0, "values": []}


def _blocked() -> list:
    """Every saved name, email, phone and address (cached ten minutes, in
    memory only), to check messages against."""
    if time.monotonic() - _BLOCKED["at"] < 600:
        return _BLOCKED["values"]
    values = []
    try:
        from ..models.database import SessionLocal
        from .spec_drafter import blocked_values
        db = SessionLocal()
        try:
            values = list(blocked_values(db))
        finally:
            db.close()
    except Exception:
        values = []
    _BLOCKED.update(at=time.monotonic(), values=values)
    return values


def _pii_free(text: str) -> bool:
    from .ai_helpers import check_outgoing
    try:
        check_outgoing(text, _blocked())
        return True
    except Exception:
        return False


def payload(kind: str, event: str, title: str, message: str, details: dict, secret: Optional[str] = None) -> tuple:  # nosec B107
    """(body bytes, headers) for one service."""
    secret = secret or ""
    now = datetime.now(timezone.utc).isoformat()
    h = {"Content-Type": "application/json", "User-Agent": "OpenOptOut"}
    prio = "high" if event in ("health_problem", "broker_turned_off", "backup_failed", "plugin_turned_off") else "default"
    if kind == "ntfy":
        h = {"Content-Type": "text/plain; charset=utf-8", "Title": title, "Tags": "shield",
             "Priority": prio, "User-Agent": "OpenOptOut"}
        if secret:
            h["Authorization"] = f"Bearer {secret}"
        return message.encode("utf-8"), h
    if kind == "gotify":
        if secret:
            h["X-Gotify-Key"] = secret
        body = {"title": title, "message": message, "priority": 7 if prio == "high" else 4}
    elif kind == "slack":
        body = {"text": f"*{title}*\n{message}"}
    elif kind == "discord":
        body = {"content": f"**{title}**\n{message}", "username": "OpenOptOut",
                "allowed_mentions": {"parse": []}}
    elif kind == "teams":
        body = {"type": "message", "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard", "version": "1.4",
                        "body": [{"type": "TextBlock", "text": title, "weight": "Bolder", "wrap": True},
                                 {"type": "TextBlock", "text": message, "wrap": True}]}}]}
    else:   # homeassistant, json
        body = {"source": "openoptout", "event": event, "title": title, "message": message,
                "details": details, "time": now}
    raw = json.dumps(body).encode("utf-8")
    if kind == "json" and secret:
        h["X-OpenOptOut-Signature"] = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, h


# ── Sending ───────────────────────────────────────────────────────────────────

def _post(url: str, body: bytes, headers: dict) -> int:
    if TRANSPORT is not None:
        return TRANSPORT(url, body, headers)
    import httpx
    r = httpx.post(url, content=body, headers=headers, timeout=10.0, follow_redirects=False)
    return r.status_code


def _deliver(t: dict, event: str, title: str, message: str, details: dict) -> tuple:
    kind = t.get("kind", "json")
    secret = _decrypt(t.get("secret_enc", ""))
    url = _decrypt(t.get("url_enc", ""))
    if not url:
        return False, "no address"
    from urllib.parse import urlparse
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower().strip()
    if scheme not in ("http", "https"):
        return False, "unsupported URL scheme"
    host = (parsed.hostname or "").lower().strip()
    if not host:
        return False, "missing host in address"
    if host in {"169.254.169.254", "169.254.170.2", "metadata.google.internal", "metadata", "instance-data", "100.100.100.200"} or host.startswith("169.254."):
        return False, "prohibited address (cloud metadata)"
    if TRANSPORT is None:
        from .dns_guard import public_host, safe_dns_context
        if not public_host(host):
            return False, "prohibited address (private or non-public host)"
    else:
        from contextlib import nullcontext
        safe_dns_context = nullcontext
    body, headers = payload(kind, event, title, message, details, secret)
    try:
        with safe_dns_context():
            code = _post(url, body, headers)
    except Exception as e:
        return False, f"couldn't reach it ({type(e).__name__})"
    if 200 <= code < 300:
        return True, "delivered"
    return False, f"the service answered {code}"


def _record(tid: str, ok: bool, status: str) -> None:
    try:
        from .settings_store import load_settings, save_settings
        s = load_settings()
        for t in (s.get("observability") or {}).get("webhooks") or []:
            if t["id"] == tid:
                t["last_status"] = status
                t["last_at"] = datetime.now(timezone.utc).isoformat()
        save_settings(s)
    except Exception:
        pass


def _work():
    while True:
        item = _queue.get()
        if item is None:
            return
        t, event, title, message, details = item
        ok, status = False, "failed"
        for attempt in range(3):
            ok, status = _deliver(t, event, title, message, details)
            if ok or "prohibited" in status or "no address" in status:
                break
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
        STATS["sent" if ok else "failed"] += 1
        if not ok:
            log.warning("Webhook '%s' (%s) not delivered after retries: %s", t.get("name"), t.get("kind"), status)
        _record(t["id"], ok, status)


def _start():
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="webhooks", daemon=True)
            _worker.start()


def build(event: str, message: str, details: Optional[dict] = None) -> tuple:
    """(title, message, details) after the allowed-list and personal-detail
    checks; raises ValueError if anything isn't allowed."""
    if event not in EVENTS:
        raise ValueError(f"unknown event {event}")
    title, allowed, _ = EVENTS[event]
    details = dict(details or {})
    extra = set(details) - allowed
    if extra:
        raise ValueError(f"{event} may not carry {sorted(extra)}")
    for k, v in details.items():
        if not isinstance(v, (int, float)) and not _SAFE_VALUE.match(str(v)):
            raise ValueError(f"{event}.{k} isn't a plain short value")
    message = _clean(message)
    if not _pii_free(f"{title}\n{message}\n{json.dumps(details)}"):
        raise ValueError("the message contains a saved personal detail")
    return title, message, details


def notify(event: str, message: str, details: Optional[dict] = None, key: str = "",
           settings: Optional[dict] = None, sync: bool = False) -> int:
    """Send `event` to every enabled target that wants it. Returns how many
    were queued (or delivered, with sync=True). Never raises."""
    try:
        title, message, details = build(event, message, details)
    except Exception as e:
        STATS["refused"] += 1
        log.error("Webhook message for %s refused: %s", event, e)
        return 0
    try:
        wanted = [t for t in targets(settings) if t.get("enabled", True)
                  and (event == "test" or event in t.get("events", []))]
    except Exception:
        return 0
    if not wanted:
        return 0
    gap = EVENTS[event][2] * 60
    if gap:
        k = (event, key)
        if time.monotonic() - _last_sent.get(k, -1e9) < gap:
            return 0
        _last_sent[k] = time.monotonic()
    n = 0
    for t in wanted:
        if sync:
            ok, status = _deliver(t, event, title, message, details)
            STATS["sent" if ok else "failed"] += 1
            _record(t["id"], ok, status)
            n += 1 if ok else 0
            continue
        try:
            _queue.put_nowait((t, event, title, message, details))
            n += 1
        except queue.Full:
            STATS["dropped"] += 1
    if n and not sync:
        _start()
    return n


def safe_notify(*a, **k) -> None:
    """notify() for core jobs: imported lazily, never raises."""
    try:
        notify(*a, **k)
    except Exception:
        pass
