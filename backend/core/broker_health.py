"""
Broker health tracking and auto-disable.

Every opt-out attempt reports its outcome here. The monitor keeps a rolling
per-broker record and, when a broker fails too many times in a row, automatically
disables it so it stops wasting runs and never takes down a batch. A disabled
broker is simply skipped by the batch runner until an admin reviews and re-enables
it.

Design notes:
  - Failure is *classified* (timeout / form_not_found / captcha / error) so the
    admin sees a meaningful "why", not just a count.
  - Auto-disable is driven by CONSECUTIVE failures, not total — a broker that
    works most of the time but fails occasionally shouldn't be disabled, while
    one that has broken (site changed, form moved, CAPTCHA wall) fails every time
    and trips the threshold quickly.
  - A single success resets the consecutive counter, so a broker that recovers
    heals itself.
  - This module never raises into the opt-out pipeline; health tracking must
    never be the reason a run fails.
"""

import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# Consecutive failures before a broker is automatically disabled. Tuned so a
# genuinely broken broker is caught quickly, but a couple of transient blips
# don't disable a working one.
AUTO_DISABLE_THRESHOLD = 5

# Recognized failure classifications (kept small and stable for the UI).
FAILURE_TIMEOUT        = "timeout"
FAILURE_FORM_NOT_FOUND = "form_not_found"
FAILURE_CAPTCHA        = "captcha"
FAILURE_ERROR          = "error"
FAILURE_UNREACHABLE    = "unreachable"   # the site itself is gone, not just its form

# A site that has answered with nothing (DNS failure, refused connection,
# 404/410 at its address) for this long is marked defunct.
DEFUNCT_AFTER = timedelta(days=30)

_UNREACHABLE_SIGNS = (
    "err_name_not_resolved", "name or service not known", "nodename nor servname",
    "getaddrinfo", "ns_error_unknown_host", "temporary failure in name resolution",
    "err_connection_refused", "connection refused", "ns_error_connection_refused",
    "err_address_unreachable", "no route to host", "network is unreachable",
    "status 404", "status 410", "http 404", "http 410", "err_cert_common_name_invalid",
)


def classify_failure(detail: str) -> str:
    """
    Best-effort classification of a failure from its error text, so the admin
    sees *why* a broker is failing. Falls back to a generic 'error'.
    """
    d = (detail or "").lower()
    if any(sign in d for sign in _UNREACHABLE_SIGNS):
        return FAILURE_UNREACHABLE
    if "timeout" in d or "timed out" in d:
        return FAILURE_TIMEOUT
    if "captcha" in d or "recaptcha" in d or "hcaptcha" in d or "challenge" in d:
        return FAILURE_CAPTCHA
    if ("no form" in d or "form not found" in d or "selector" in d
            or "no element" in d or "not found" in d):
        return FAILURE_FORM_NOT_FOUND
    return FAILURE_ERROR


def _get_or_create(db, broker_id: int):
    from ..models.database import BrokerHealth
    h = db.query(BrokerHealth).filter(BrokerHealth.broker_id == broker_id).first()
    if not h:
        h = BrokerHealth(broker_id=broker_id)
        db.add(h)
        db.flush()
    return h


def record_success(db, broker_id: int) -> None:
    """Record a successful opt-out attempt; resets the consecutive-failure count."""
    try:
        h = _get_or_create(db, broker_id)
        h.consecutive_failures = 0
        h.unreachable_since = None
        h.total_attempts  = (h.total_attempts or 0) + 1
        h.total_successes = (h.total_successes or 0) + 1
        h.last_success_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        log.error("broker_health.record_success failed for broker %s: %s", broker_id, e)
        db.rollback()


def record_failure(db, broker_id: int, detail: str = "") -> bool:
    """
    Record a failed opt-out attempt. Returns True if this failure caused the
    broker to be auto-disabled. Never raises into the caller.
    """
    try:
        from ..models.database import Broker
        h = _get_or_create(db, broker_id)
        h.consecutive_failures = (h.consecutive_failures or 0) + 1
        h.total_attempts = (h.total_attempts or 0) + 1
        h.total_failures = (h.total_failures or 0) + 1
        h.last_failure_at = datetime.utcnow()
        h.last_failure_reason = classify_failure(detail)
        h.last_failure_detail = (detail or "")[:2000]

        just_disabled = False
        if h.last_failure_reason == FAILURE_UNREACHABLE:
            just_disabled = _note_unreachable(db, h, broker_id, h.last_failure_detail) or just_disabled
        else:
            h.unreachable_since = None
        if h.consecutive_failures >= AUTO_DISABLE_THRESHOLD and not h.auto_disabled:
            broker = db.query(Broker).filter(Broker.id == broker_id).first()
            if broker and broker.enabled:
                broker.enabled = False
                h.auto_disabled = True
                h.auto_disabled_at = datetime.utcnow()
                h.auto_disabled_reason = (
                    f"{h.consecutive_failures} consecutive failures "
                    f"(last: {h.last_failure_reason})"
                )
                h.needs_review = True
                just_disabled = True
                log.warning(
                    "Broker %s AUTO-DISABLED after %d consecutive failures (%s)",
                    broker_id, h.consecutive_failures, h.last_failure_reason,
                )
        db.commit()
        return just_disabled
    except Exception as e:
        log.error("broker_health.record_failure failed for broker %s: %s", broker_id, e)
        db.rollback()
        return False


def re_enable(db, broker_id: int, clear_review: bool = True) -> None:
    """Admin action: turn a broker back on and reset its consecutive-failure count."""
    from ..models.database import Broker, BrokerHealth
    broker = db.query(Broker).filter(Broker.id == broker_id).first()
    if broker:
        broker.enabled = True
    h = db.query(BrokerHealth).filter(BrokerHealth.broker_id == broker_id).first()
    if h:
        h.consecutive_failures = 0
        h.auto_disabled = False
        h.auto_disabled_reason = None
        if clear_review:
            h.needs_review = False
    db.commit()


def disable(db, broker_id: int, reason: str = "manually disabled") -> None:
    """Admin action: turn a broker off by hand."""
    from ..models.database import Broker, BrokerHealth
    broker = db.query(Broker).filter(Broker.id == broker_id).first()
    if broker:
        broker.enabled = False
    h = _get_or_create(db, broker_id)
    h.auto_disabled = False           # this was a human decision, not the monitor
    h.auto_disabled_reason = reason
    db.commit()


# ── Dead sites ────────────────────────────────────────────────────────────────

def _note_unreachable(db, h, broker_id: int, detail: str, now=None) -> bool:
    """Track how long a site has been unreachable; mark it defunct after
    DEFUNCT_AFTER. Returns True if the broker was just turned off."""
    from ..models.database import Broker
    now = now or datetime.utcnow()
    if h.unreachable_since is None:
        h.unreachable_since = now
    if h.defunct or now - h.unreachable_since < DEFUNCT_AFTER:
        return False
    h.defunct = True
    h.needs_review = True
    broker = db.query(Broker).filter(Broker.id == broker_id).first()
    days = (now - h.unreachable_since).days
    reason = f"Site unreachable for {days} days (last: {(detail or '')[:120]})"
    if broker is not None and broker.registry_last_seen and now - broker.registry_last_seen < timedelta(days=120):
        reason += (". It is still on a state data broker registry, so it may have moved to a new "
                   "address — check the registry entry before removing it.")
    h.auto_disabled_reason = reason
    if broker is not None and broker.enabled:
        broker.enabled = False
        h.auto_disabled = True
        h.auto_disabled_at = now
        log.warning("Broker %s marked DEFUNCT: %s", broker_id, reason)
        return True
    return False


def record_probe(db, broker_id: int, reachable: bool, detail: str = "", now=None) -> None:
    """
    Result of a reachability check of the broker's site (no personal data is
    sent). Only affects dead-site tracking, not opt-out success counts. A
    defunct site that answers again is flagged for review, not turned back on.
    """
    try:
        now = now or datetime.utcnow()
        h = _get_or_create(db, broker_id)
        h.last_probe_at = now
        if reachable:
            h.unreachable_since = None
            if h.defunct:
                h.defunct = False
                h.needs_review = True
                h.auto_disabled_reason = "This site answers again. Check it, then turn it back on if it's real."
        else:
            _note_unreachable(db, h, broker_id, detail, now=now)
        db.commit()
    except Exception as e:
        log.error("broker_health.record_probe failed for broker %s: %s", broker_id, e)
        db.rollback()


def probe_sites(db, limit: int = 50, fetch=None) -> dict:
    """
    Check whether brokers' sites still exist: one plain request to each site's
    home page, oldest-checked first, at most `limit` per run. Sends no personal
    data. Private and local addresses are never contacted.
    """
    from ..models.database import Broker, BrokerHealth
    from .listing_finder import broker_domain
    checked = unreachable = 0
    rows = (db.query(Broker, BrokerHealth)
              .outerjoin(BrokerHealth, BrokerHealth.broker_id == Broker.id)
              .filter(Broker.is_test.isnot(True))
              .all())
    rows = [r for r in rows if (r[0].origin or "curated") != "state_program" and broker_domain(r[0])]
    rows.sort(key=lambda r: (r[1].last_probe_at if r[1] and r[1].last_probe_at else datetime.min))
    for b, _ in rows[:limit]:
        ok, detail = (fetch or _probe)(broker_domain(b))
        record_probe(db, b.id, ok, detail)
        checked += 1
        unreachable += 0 if ok else 1
    return {"checked": checked, "unreachable": unreachable}


def _probe(domain: str):
    import socket
    from .registry_sync import _public_host
    try:
        socket.getaddrinfo(domain, 443)
    except socket.gaierror as e:
        return False, f"getaddrinfo failed: {e}"
    if not _public_host(domain):
        return True, "skipped: not a public address"
    try:
        import requests
        r = requests.get(f"https://{domain}/", timeout=15, allow_redirects=False,
                         headers={"User-Agent": "OpenOptOut site check"})
        if r.status_code in (404, 410):
            return False, f"HTTP {r.status_code} at https://{domain}/"
        return True, f"HTTP {r.status_code}"
    except Exception as e:
        msg = str(e).lower()
        if "refused" in msg or "name or service not known" in msg or "no route" in msg:
            return False, f"connection refused or unreachable: {e}"
        return True, f"inconclusive: {type(e).__name__}"   # timeouts etc. aren't proof a site is gone
