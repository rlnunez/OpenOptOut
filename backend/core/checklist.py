"""
The checklist: everything that needs a person, in one place, plus a progress
summary per family member.

Groups (in the order a person should tackle them):

  inbox     — family members with no email inbox (nothing can be sent for them)
  finish    — opt-outs OpenOptOut can't finish alone (needs_manual), with the
              plain-language instructions the engine wrote, incl. California DROP
  confirm   — brokers that emailed a confirmation link OpenOptOut couldn't
              click by itself (wrong site, expired, needed a button, ...)
  captcha   — opt-outs paused at a CAPTCHA
  review    — web search results waiting for "that's me / not me"
  overdue   — sent requests the broker hasn't answered within its legal window
              (the spec's statutory_response_days, else 45 days)
  recheck   — removals due for a check that the listing hasn't come back

Progress per member: removed (confirmed), in progress (pending, sent,
submitted), needs you (items above), other (failed/rejected).
"""

from datetime import datetime, timedelta

DEFAULT_RESPONSE_DAYS = 45


def _response_days(db, broker, cache: dict) -> int:
    if broker.id in cache:
        return cache[broker.id]
    days = DEFAULT_RESPONSE_DAYS
    try:
        from ..plugins.broker_addon import get_broker_spec_for_broker
        spec = get_broker_spec_for_broker(db, broker)
        if spec and spec.statutory_response_days:
            days = spec.statutory_response_days
    except Exception:
        pass
    cache[broker.id] = days
    return days


def build(db, member_ids: list, now=None) -> dict:
    from ..models.database import (FamilyMember, RemovalRequest, RequestStatus, CaptchaChallenge,
                                   WebSearchHit, ConfirmationLink)
    from .confirm_links import instruction as confirm_instruction
    from . import mailboxes as mbx
    now = now or datetime.utcnow()
    members = {m.id: m for m in db.query(FamilyMember).filter(FamilyMember.id.in_(member_ids)).all()}
    groups = {k: [] for k in ("inbox", "finish", "confirm", "captcha", "review", "overdue", "recheck")}

    for m in members.values():
        if mbx.resolve_mailbox(db, m) is None:
            groups["inbox"].append({"member_id": m.id, "member_name": m.full_name,
                                    "text": mbx.missing_mailbox_instruction(m), "link": "/inboxes"})

    reqs = db.query(RemovalRequest).filter(RemovalRequest.member_id.in_(list(members))).all()
    paused = {c.request_id for c in db.query(CaptchaChallenge).filter(
        CaptchaChallenge.member_id.in_(list(members)), CaptchaChallenge.status == "pending").all()}
    req_ids = [r.id for r in reqs]
    confirm = {}
    if req_ids:
        for c in (db.query(ConfirmationLink)
                    .filter(ConfirmationLink.request_id.in_(req_ids), ConfirmationLink.status == "needs_person")
                    .order_by(ConfirmationLink.found_at).all()):
            confirm[c.request_id] = c
    days_cache = {}
    progress = {mid: {"member_id": mid, "member_name": m.full_name, "removed": 0, "in_progress": 0,
                      "needs_you": 0, "other": 0} for mid, m in members.items()}

    for r in reqs:
        b = r.broker
        item = {"request_id": r.id, "member_id": r.member_id, "member_name": members[r.member_id].full_name,
                "broker_name": b.name if b else "", "site": (b.opt_out_url if b else None),
                "listing_url": r.listing_url, "text": r.notes or ""}
        p = progress[r.member_id]
        st = r.status
        if st == RequestStatus.needs_manual:
            cands = candidates(r)
            if cands:
                item = {**item, "candidates": cands}
            if getattr(r, "handoff_enc", None):
                item = {**item, "live": True}   # "Do it here": pick it up on the live page
            groups["finish"].append(item); p["needs_you"] += 1
        elif r.id in paused and st == RequestStatus.pending:
            groups["captcha"].append({**item, "text": f"{item['broker_name']} asked for a CAPTCHA.",
                                      "link": "/captcha"}); p["needs_you"] += 1
        elif st in (RequestStatus.sent, RequestStatus.submitted) and r.id in confirm:
            c = confirm[r.id]
            mb = mbx.resolve_mailbox(db, members[r.member_id])
            groups["confirm"].append({**item, "confirm_id": c.id,
                                      "confirm_url": c.url if (c.url and c.reason != "off_site") else None,
                                      "text": confirm_instruction(c, item["broker_name"],
                                                                  mbx.base_address(mb.address) if mb else "")})
            p["needs_you"] += 1
        elif st in (RequestStatus.sent, RequestStatus.submitted):
            days = _response_days(db, b, days_cache) if b else DEFAULT_RESPONSE_DAYS
            waited = (now - r.sent_at).days if r.sent_at else 0
            if b and r.sent_at and waited > days:
                groups["overdue"].append({**item, "days_waiting": waited, "text":
                    f"{item['broker_name']} hasn't answered in {waited} days (it had {days}). "
                    f"Send the request again, or mark it done if the listing is gone."})
                p["needs_you"] += 1
            else:
                p["in_progress"] += 1
        elif st == RequestStatus.confirmed:
            p["removed"] += 1
            if r.recheck_after and r.recheck_after <= now:
                groups["recheck"].append({**item, "text":
                    f"Check that {members[r.member_id].full_name}'s listing on {item['broker_name']} "
                    f"hasn't come back. If it has, send the request again."})
        elif st in (RequestStatus.pending, RequestStatus.recheck_due):
            p["in_progress"] += 1
        else:
            p["other"] += 1

    hits = db.query(WebSearchHit).filter(WebSearchHit.member_id.in_(list(members)),
                                         WebSearchHit.status == "new").all()
    per = {}
    for h in hits:
        per[h.member_id] = per.get(h.member_id, 0) + 1
    for mid, n in per.items():
        groups["review"].append({"member_id": mid, "member_name": members[mid].full_name, "count": n,
                                 "text": f"Web search found {n} page{'s' if n != 1 else ''} that might be "
                                         f"about {members[mid].full_name}. Say which ones are.",
                                 "link": "/discovery"})
        progress[mid]["needs_you"] += 1
    for item in groups["inbox"]:
        progress[item["member_id"]]["needs_you"] += 1

    groups["overdue"].sort(key=lambda i: -i["days_waiting"])
    total = sum(len(v) for k, v in groups.items() if k != "recheck") + len(groups["recheck"])
    return {"groups": groups, "progress": list(progress.values()), "total": total}


def candidates(req) -> list:
    """Possible listings a person needs to choose between (unclear matches), or []."""
    import json
    raw = getattr(req, "candidates_enc", None)
    if not raw:
        return []
    try:
        out = json.loads(raw)
    except Exception:
        return []
    return [{"url": c.get("url", ""), "text": (c.get("text") or "")[:400], "why": c.get("why", "")}
            for c in out if isinstance(c, dict) and str(c.get("url", "")).startswith(("http://", "https://"))]


def pick(db, req, urls: list, who: str, now=None) -> str:
    """
    The person chose which possible listings are theirs. Chosen ones are sent
    on the next run; choosing none marks the site skipped.
    """
    import json
    from ..models.database import RequestStatus
    now = now or datetime.utcnow()
    allowed = {c["url"] for c in candidates(req)}
    chosen = [u for u in dict.fromkeys(urls or []) if u in allowed]
    req.candidates_enc = None
    req.updated_at = now
    if not chosen:
        req.picked_enc = None
        req.status = RequestStatus.skipped
        req.notes = f"{who} said none of the possible listings were theirs, so this site was skipped."
        db.commit()
        return "skipped"
    req.picked_enc = json.dumps(chosen)
    req.status = RequestStatus.pending
    req.notes = f"{who} picked {len(chosen)} listing(s); OpenOptOut will ask for them to be removed."
    db.commit()
    return "queued"


def mark_done(db, req, who: str, recheck_days: int = 90, now=None):
    """The person finished an opt-out themselves."""
    from ..models.database import RequestStatus
    now = now or datetime.utcnow()
    req.status = RequestStatus.sent
    req.sent_at = req.sent_at or now
    req.recheck_after = now + timedelta(days=recheck_days)
    req.notes = ((req.notes or "") + f"\nDone by {who} on {now:%Y-%m-%d}.").strip()
    req.updated_at = now
    db.commit()


def mark_removed(db, req, who: str, recheck_days: int = 90, now=None):
    """The person checked: the listing is gone."""
    from ..models.database import RequestStatus
    now = now or datetime.utcnow()
    req.status = RequestStatus.confirmed
    req.confirmed_at = now
    req.recheck_after = now + timedelta(days=recheck_days)
    req.notes = ((req.notes or "") + f"\nListing gone, checked by {who} on {now:%Y-%m-%d}.").strip()
    req.updated_at = now
    db.commit()
