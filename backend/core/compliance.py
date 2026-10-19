"""
Deadline report: which sites missed the time the law gives them, and which put
people's details back after removing them.

Every broker spec records the law that applies and the days it has to answer
(CCPA 45, GDPR 30, ...). With the removal timeline (core/timeline.py) that
gives, for each request: when it was sent, when the answer was due, and when
(or whether) the site replied and removed the listing.

Scope: callers pass the member ids the viewer may already see
(auth.get_accessible_member_ids): a person sees their own family, a scoped
manager their branches, a super admin everyone. Nothing outside that is read.

Notices: a person can opt in to an email when a site misses its deadline or
puts their details back. Each notice is sent once per round (NoticeSent).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Iterable, Optional

log = logging.getLogger(__name__)

KINDS = ("overdue", "relisted")


def classify(cycle: dict, now: datetime) -> str:
    """on_time | late | overdue | waiting | no_deadline | not_sent for one round."""
    from datetime import datetime as _dt
    p = lambda v: _dt.fromisoformat(v) if isinstance(v, str) else v
    sent, due = p(cycle.get("sent_at")), p(cycle.get("due_by"))
    answered = p(cycle.get("replied_at")) or p(cycle.get("removed_at"))
    if not sent:
        return "not_sent"
    if not due:
        return "no_deadline"
    if answered:
        return "on_time" if answered <= due else "late"
    return "overdue" if now > due else "waiting"


def report(db, member_ids: Iterable[int], now: Optional[datetime] = None, mask=None) -> dict:
    """Per-site summary plus one evidence row per round, for the given people only."""
    from ..models.database import RemovalRequest
    from .timeline import build
    now = now or datetime.utcnow()
    ids = list(member_ids)
    if not ids:
        return {"generated_at": now.isoformat(), "sites": [], "rows": [], "totals": _empty()}
    reqs = db.query(RemovalRequest).filter(RemovalRequest.member_id.in_(ids)).all()
    sites, rows = {}, []
    for r in reqs:
        t = build(db, r, now=now)
        if not t["cycles"]:
            continue
        name = t["broker"]
        s = sites.setdefault(name, {"site": name, "response_days": t["response_days"], **_empty(), "_days": []})
        for n, c in enumerate(t["cycles"], 1):
            verdict = classify(c, now)
            if verdict == "not_sent":
                continue
            s["rounds"] += 1
            s[verdict] = s.get(verdict, 0) + 1
            if c.get("found_again_at"):
                s["relisted"] += 1
            if c.get("sent_at") and c.get("removed_at"):
                s["_days"].append((datetime.fromisoformat(c["removed_at"]) - datetime.fromisoformat(c["sent_at"])).days)
            rows.append({
                "site": name, "person": t["member"] if mask is None else mask(r),
                "request_id": r.id, "round": n, "law_days": t["response_days"] or None,
                "sent": c.get("sent_at"), "due": c.get("due_by"), "replied": c.get("replied_at"),
                "removed": c.get("removed_at"), "found_again": c.get("found_again_at"),
                "follow_ups": len(c.get("follow_ups") or []), "verdict": verdict,
            })
    out_sites = []
    for s in sites.values():
        d = sorted(s.pop("_days"))
        s["median_days_to_remove"] = d[len(d) // 2] if d else None
        s["missed"] = s["overdue"] + s["late"]
        out_sites.append(s)
    out_sites.sort(key=lambda s: (-(s["missed"] + s["relisted"]), s["site"]))
    totals = _empty()
    for s in out_sites:
        for k in totals:
            totals[k] += s.get(k, 0)
    rows.sort(key=lambda r: (r["verdict"] != "overdue", r["site"], r["person"], r["round"]))
    return {"generated_at": now.isoformat(), "sites": out_sites, "rows": rows, "totals": totals}


def _empty() -> dict:
    return {"rounds": 0, "on_time": 0, "late": 0, "overdue": 0, "waiting": 0, "no_deadline": 0, "relisted": 0}


CSV_COLUMNS = ["site", "person", "round", "law_days", "sent", "due", "replied", "removed",
               "found_again", "follow_ups", "verdict"]


def to_csv(rep: dict) -> str:
    import csv, io
    from .csv_safety import csv_safe
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rep["rows"]:
        w.writerow({k: csv_safe(v) for k, v in r.items()})
    return buf.getvalue()


# ── Notices ───────────────────────────────────────────────────────────────────

def prefs(user) -> dict:
    try:
        p = json.loads(getattr(user, "notification_prefs", None) or "{}")
    except Exception:
        p = {}
    return {"overdue": bool(p.get("overdue")), "relisted": bool(p.get("relisted"))}


def own_member_ids(db, user) -> list:
    """The people a notice is about: the user's own family and profiles shared
    with them, never a whole branch (a manager isn't emailed about patrons)."""
    from ..models.database import FamilyMember, ProfileAccess
    users = {user.id} | {g.managed_id for g in db.query(ProfileAccess)
                         .filter(ProfileAccess.manager_id == user.id, ProfileAccess.can_view == True).all()}  # noqa: E712
    return [m.id for m in db.query(FamilyMember).filter(FamilyMember.user_id.in_(users)).all()]


def pending_notices(db, user, now: Optional[datetime] = None) -> list:
    """Notices this user has asked for and hasn't been sent yet."""
    from ..models.database import NoticeSent
    want = prefs(user)
    if not (want["overdue"] or want["relisted"]):
        return []
    rep = report(db, own_member_ids(db, user), now=now)
    sent = {(n.request_id, n.kind, n.round_key) for n in db.query(NoticeSent).filter(NoticeSent.user_id == user.id).all()}
    out = []
    for r in rep["rows"]:
        if want["overdue"] and r["verdict"] == "overdue":
            key = (r["request_id"], "overdue", r["sent"] or "")
            if key not in sent:
                out.append({**r, "kind": "overdue", "round_key": key[2]})
        if want["relisted"] and r["found_again"]:
            key = (r["request_id"], "relisted", r["found_again"])
            if key not in sent:
                out.append({**r, "kind": "relisted", "round_key": key[2]})
    return out


def _fmt(v):
    from .regional import format_date
    return format_date(v)


def notice_email(items: list) -> tuple:
    overdue = [i for i in items if i["kind"] == "overdue"]
    relisted = [i for i in items if i["kind"] == "relisted"]
    lines = ["Hello,", ""]
    if overdue:
        lines += ["These sites haven't answered within the time the law gives them:", ""]
        lines += [f"  - {i['site']} ({i['person']}): sent {_fmt(i['sent'])}, due {_fmt(i['due'])}" for i in overdue]
        lines += [""]
    if relisted:
        lines += ["These sites put details back after removing them. OpenOptOut will ask again on its next run:", ""]
        lines += [f"  - {i['site']} ({i['person']}): removed {_fmt(i['removed'])}, found again {_fmt(i['found_again'])}"
                  for i in relisted]
        lines += [""]
    lines += ["The Deadline report in OpenOptOut has the full history for each one, and a file",
              "you can attach to a complaint to your state attorney general or privacy regulator.",
              "", "You can turn these emails off on the Deadline report page."]
    n = len(items)
    subject = f"OpenOptOut: {n} site{'s' if n != 1 else ''} need{'s' if n == 1 else ''} attention"
    return subject, "\n".join(lines)


def run_notices(db, cfg: dict, send=None, now: Optional[datetime] = None) -> dict:
    """Daily: email each opted-in person their new notices. Never raises per user."""
    from ..models.database import User, NoticeSent
    if send is None:
        from .email_send import send_email
        send = lambda to, subject, body: send_email(cfg, to=[to], cc=[], subject=subject, body=body)
    stats = {"users": 0, "emails": 0, "items": 0, "errors": 0}
    for u in db.query(User).filter(User.notification_prefs.isnot(None)).all():
        try:
            items = pending_notices(db, u, now=now)
            if not items or not u.email:
                continue
            stats["users"] += 1
            subject, body = notice_email(items)
            r = send(u.email, subject, body) or {}
            if r.get("ok", True) is False:
                stats["errors"] += 1
                continue
            for i in items:
                db.add(NoticeSent(user_id=u.id, request_id=i["request_id"], kind=i["kind"], round_key=i["round_key"]))
            db.commit()
            stats["emails"] += 1
            stats["items"] += len(items)
        except Exception as e:
            db.rollback()
            stats["errors"] += 1
            log.warning("Notice for user %s failed: %s", u.id, e)
    return stats
