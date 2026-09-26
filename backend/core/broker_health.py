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
from datetime import datetime

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


def classify_failure(detail: str) -> str:
    """
    Best-effort classification of a failure from its error text, so the admin
    sees *why* a broker is failing. Falls back to a generic 'error'.
    """
    d = (detail or "").lower()
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
