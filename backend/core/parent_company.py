"""
Parent-company effectiveness tracking.

Records the outcome of email opt-outs per parent company and derives an
honor_status so operators learn which parents actually respond. This is what
turns "we sent emails into the void" into "we know these 12 parents honor
requests and these 3 ignore them" — real signal for where the tool is effective.

Called by the email opt-out path (on send) and by the confirmation matcher
(when a removal is later verified). Never raises into the pipeline.
"""

import logging
from datetime import datetime

log = logging.getLogger(__name__)

# How honor_status is derived from the counters. Thresholds are deliberately
# forgiving early (few data points) and firm once there's a track record.
MIN_SENDS_FOR_JUDGEMENT = 3


def _derive_status(sent, confirmed, failed):
    from ..models.database import EmailHonorStatus
    if sent == 0:
        return EmailHonorStatus.unknown
    # If most sends bounce/fail, the address itself is bad.
    if failed and failed >= max(1, sent * 0.5):
        return EmailHonorStatus.bounces
    if sent < MIN_SENDS_FOR_JUDGEMENT:
        # Not enough data to judge; reflect any early confirmation optimistically.
        return EmailHonorStatus.honors if confirmed else EmailHonorStatus.unknown
    rate = confirmed / sent
    if rate >= 0.75:
        return EmailHonorStatus.honors
    if rate >= 0.25:
        return EmailHonorStatus.partial
    return EmailHonorStatus.ignores


def record_send(db, parent_id: int, failed: bool = False) -> None:
    """Record that an opt-out email was sent (or failed to send) to a parent."""
    from ..models.database import ParentCompany
    try:
        p = db.query(ParentCompany).filter(ParentCompany.id == parent_id).first()
        if not p:
            return
        if failed:
            p.emails_failed = (p.emails_failed or 0) + 1
        else:
            p.emails_sent = (p.emails_sent or 0) + 1
            p.last_sent_at = datetime.utcnow()
        p.honor_status = _derive_status(p.emails_sent or 0, p.emails_confirmed or 0, p.emails_failed or 0)
        db.commit()
    except Exception as e:
        log.error("record_send failed for parent %s: %s", parent_id, e)
        db.rollback()


def record_confirmation(db, parent_id: int) -> None:
    """Record that a removal was verified/confirmed for a parent (raises honor)."""
    from ..models.database import ParentCompany
    try:
        p = db.query(ParentCompany).filter(ParentCompany.id == parent_id).first()
        if not p:
            return
        p.emails_confirmed = (p.emails_confirmed or 0) + 1
        p.last_confirmed_at = datetime.utcnow()
        p.honor_status = _derive_status(p.emails_sent or 0, p.emails_confirmed or 0, p.emails_failed or 0)
        db.commit()
    except Exception as e:
        log.error("record_confirmation failed for parent %s: %s", parent_id, e)
        db.rollback()


def parent_stats(p) -> dict:
    """Serializable effectiveness summary for the UI."""
    sent = p.emails_sent or 0
    conf = p.emails_confirmed or 0
    return {
        "id": p.id, "name": p.name,
        "honor_status": p.honor_status.value if p.honor_status else "unknown",
        "emails_sent": sent, "emails_confirmed": conf, "emails_failed": p.emails_failed or 0,
        "confirm_rate": round(100.0 * conf / sent, 1) if sent else None,
        "last_sent_at": p.last_sent_at.isoformat() if p.last_sent_at else None,
        "last_confirmed_at": p.last_confirmed_at.isoformat() if p.last_confirmed_at else None,
        "child_count": len(p.children) if p.children is not None else 0,
    }


def discovered_urls_for_parent(db, parent, member_id: int) -> dict:
    """
    Build the {broker_name: listing_url} map for a parent's child sites, drawn
    from stored discovery results for this member. This is what lets the opt-out
    email cite the exact URL of the person's record on each child site — the
    strongest form of record-matching. Returns only sites where a URL was found;
    the email lists the rest by name.
    """
    from ..models.database import DiscoveryResult
    urls = {}
    child_ids = {c.id: c.name for c in (parent.children or [])}
    if not child_ids:
        return urls
    try:
        rows = (db.query(DiscoveryResult)
                .filter(DiscoveryResult.member_id == member_id,
                        DiscoveryResult.broker_id.in_(list(child_ids.keys())),
                        DiscoveryResult.listing_url.isnot(None))
                .all())
        for r in rows:
            name = child_ids.get(r.broker_id)
            if name and r.listing_url:
                urls[name] = r.listing_url
    except Exception as e:
        log.error("discovered_urls_for_parent failed: %s", e)
    return urls
