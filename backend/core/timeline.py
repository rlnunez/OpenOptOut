"""
Removal timeline: the history of one opt-out (one person × one site), cycle
after cycle.

A cycle starts when a request goes out. Within it: any follow-up sends, the
site's reply, the removal, and the later checks. If a check finds the listing
again (or the check-again date comes round and it's sent again), a new cycle
starts. The page shows the latest cycle as a progress bar and the earlier ones
underneath.

Built from what's already recorded: status changes (RequestEvent), automation
attempts, emails, confirmation links, CAPTCHAs and removal checks. Nothing
here shows personal details: only dates, what happened, and the site's name.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

SENT_ACTIONS = {"form_fill", "email_send"}
LABELS = {
    "sent": "Request sent",
    "follow_up": "Sent again (follow-up)",
    "sent_again": "Sent again (found again)",
    "reply": "The site replied",
    "link_clicked": "Confirmation link clicked",
    "removed": "Removed",
    "checked_gone": "Checked: still gone",
    "still_listed": "Checked: still listed",
    "found_again": "Found again",
    "check_due": "Time to check again",
    "needs_you": "Needs you",
    "captcha": "Stopped at a CAPTCHA",
    "captcha_done": "CAPTCHA finished",
    "refused": "The site refused",
    "failed": "Didn't work",
    "queued": "Waiting to send",
}
STAGES = ["sent", "reply", "removed", "watching"]
STAGE_LABELS = {"sent": "Sent", "reply": "Reply", "removed": "Removed", "watching": "Staying gone"}


def _ev(at, kind, note=""):
    return {"at": at, "kind": kind, "label": LABELS[kind], "note": note}


def raw_events(db, req) -> list:
    """Every recorded step for this request, oldest first (before grouping into cycles)."""
    from ..models.database import (AutomationLog, EmailLog, ConfirmationLink, VerificationCheck,
                                   CaptchaChallenge, RequestEvent)
    out = []
    for e in db.query(RequestEvent).filter(RequestEvent.request_id == req.id).all():
        kind = {"sent": "sent", "submitted": "sent", "confirmed": "removed", "recheck_due": "check_due",
                "needs_manual": "needs_you", "rejected": "refused", "failed": "failed",
                "pending": "queued"}.get(e.to_status)
        if kind == "sent" and e.from_status == "needs_manual":
            out.append(_ev(e.at, "sent", "done by a person"))
        elif kind:
            out.append(_ev(e.at, kind))
    for a in db.query(AutomationLog).filter(AutomationLog.request_id == req.id).all():
        if a.action in SENT_ACTIONS and a.status == "success":
            out.append(_ev(a.created_at, "sent", "web form" if a.action == "form_fill" else "email"))
    for m in db.query(EmailLog).filter(EmailLog.request_id == req.id).all():
        if m.direction == "received":
            out.append(_ev(m.received_at, "reply"))
        elif m.direction == "sent":
            out.append(_ev(m.received_at, "sent", "email"))
    for c in db.query(ConfirmationLink).filter(ConfirmationLink.request_id == req.id).all():
        if c.clicked_at:
            out.append(_ev(c.clicked_at, "link_clicked", "by you" if c.status == "done" else "automatically"))
    for c in db.query(CaptchaChallenge).filter(CaptchaChallenge.request_id == req.id).all():
        out.append(_ev(c.created_at, "captcha"))
        if c.resolved_at and c.status == "resolved":
            out.append(_ev(c.resolved_at, "captcha_done"))
    for v in db.query(VerificationCheck).filter(VerificationCheck.request_id == req.id).all():
        if v.verdict == "gone":
            out.append(_ev(v.checked_at, "checked_gone", v.method.replace("_", " ")))
        elif v.verdict == "listed":
            out.append(_ev(v.checked_at, "still_listed", v.method.replace("_", " ")))
    out = [e for e in out if e["at"] is not None]
    out.sort(key=lambda e: e["at"])
    # The same send is often recorded twice (the attempt and the status
    # change); keep one per 10 minutes.
    deduped = []
    for e in out:
        if deduped and e["kind"] in ("sent", "removed", "reply") and any(
                d["kind"] == e["kind"] and abs((e["at"] - d["at"]).total_seconds()) < 600 for d in deduped[-4:]):
            continue
        deduped.append(e)
    return deduped


def cycles(events: list, response_days: int = 0) -> list:
    """Group events into cycles; each starts with a send."""
    out, cur = [], None
    for e in events:
        if e["kind"] == "sent" and cur is not None and cur["sent_at"] is None:
            cur["sent_at"] = e["at"]          # first send after older, unsent steps
        elif e["kind"] == "sent":
            if cur is None or cur["removed_at"] or cur["found_again_at"]:
                if cur is not None and (cur["removed_at"] or cur["found_again_at"]):
                    e = dict(e, kind="sent_again", label=LABELS["sent_again"])
                cur = {"sent_at": e["at"], "follow_ups": [], "replied_at": None, "removed_at": None,
                       "found_again_at": None, "last_checked_gone_at": None, "events": []}
                out.append(cur)
            else:
                e = dict(e, kind="follow_up", label=LABELS["follow_up"])
                cur["follow_ups"].append(e["at"])
        elif cur is None:
            # Something happened before any recorded send (older data).
            cur = {"sent_at": None, "follow_ups": [], "replied_at": None, "removed_at": None,
                   "found_again_at": None, "last_checked_gone_at": None, "events": []}
            out.append(cur)
        k = e["kind"]
        if k in ("reply", "link_clicked") and not cur["replied_at"]:
            cur["replied_at"] = e["at"]
        if k in ("removed", "checked_gone") and not cur["removed_at"]:
            cur["removed_at"] = e["at"]
        if k == "checked_gone":
            cur["last_checked_gone_at"] = e["at"]
        if k == "still_listed" and cur["removed_at"] and not cur["found_again_at"]:
            e = dict(e, kind="found_again", label=LABELS["found_again"])
            cur["found_again_at"] = e["at"]
        cur["events"].append(e)
    for c in out:
        c["due_by"] = (c["sent_at"] + timedelta(days=response_days)) if (c["sent_at"] and response_days) else None
        c["stage"] = stage_of(c)
    return out


def stage_of(c: dict) -> str:
    if c["found_again_at"]:
        return "found_again"
    if c["removed_at"] and c["last_checked_gone_at"] and c["last_checked_gone_at"] > c["removed_at"]:
        return "watching"
    if c["removed_at"]:
        return "removed"
    if c["replied_at"]:
        return "reply"
    if c["sent_at"]:
        return "sent"
    return "not_sent"


def _iso(d):
    return d.isoformat() if isinstance(d, datetime) else d


def build(db, req, now: Optional[datetime] = None) -> dict:
    """The timeline for one request, ready to send to the page."""
    now = now or datetime.utcnow()
    days = 0
    try:
        from ..plugins.broker_addon import get_broker_spec_for_broker
        spec = get_broker_spec_for_broker(db, req.broker)
        days = int(getattr(spec, "statutory_response_days", 0) or 0)
    except Exception:
        pass
    evs = raw_events(db, req)
    cs = cycles(evs, days)
    latest = cs[-1] if cs else None
    overdue = bool(latest and latest["due_by"] and now > latest["due_by"]
                   and not latest["replied_at"] and not latest["removed_at"])

    def ser(c):
        return {**{k: _iso(v) for k, v in c.items() if k not in ("events", "follow_ups")},
                "follow_ups": [_iso(x) for x in c["follow_ups"]],
                "events": [{**e, "at": _iso(e["at"])} for e in c["events"]]}
    return {
        "request_id": req.id,
        "broker": req.broker.name if req.broker else "",
        "member": req.member.full_name if req.member else "",
        "status": getattr(req.status, "value", req.status),
        "next_check": _iso(req.recheck_after),
        "response_days": days,
        "overdue": overdue,
        "stages": [{"key": s, "label": STAGE_LABELS[s]} for s in STAGES],
        "cycles": [ser(c) for c in cs],
    }
