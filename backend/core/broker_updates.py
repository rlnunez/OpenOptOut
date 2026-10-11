"""
Broker update notifications for administrators.

Things worth an admin's attention about the broker list, recorded as they
happen and shown on **Broker updates** (with a sidebar badge), then emailed to
super administrators as a digest:

  auto_disabled    turned off after repeated failed opt-outs
  defunct          site unreachable for 30 days, turned off
  back_online      a defunct site answers again (left off until checked)
  new_brokers      a state registry import added brokers (they start off)
  delisted         brokers that dropped off a state registry
  new_site         someone pasted a listing on a site OpenOptOut didn't know
  contact_changed  a registry gave a broker a contact address

The same thing about the same broker isn't recorded twice within
DEDUPE_DAYS. Nothing here contains family members' personal details: titles
name the broker and what happened, never who found a listing.
"""

import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

DEDUPE_DAYS = 7
KINDS = {
    "auto_disabled":   ("urgent", "Turned off after failing"),
    "defunct":         ("urgent", "Website gone"),
    "back_online":     ("review", "Website back"),
    "new_brokers":     ("info", "New brokers"),
    "delisted":        ("review", "Left a registry"),
    "new_site":        ("review", "New site from a listing"),
    "contact_changed": ("info", "New contact address"),
}
DEFAULT_SETTINGS = {"email_digest": "daily"}     # off | daily | weekly


def settings_of(cfg: dict) -> dict:
    out = dict(DEFAULT_SETTINGS)
    out.update((cfg or {}).get("broker_updates") or {})
    return out


def record(db, kind: str, title: str, detail: str = "", broker_id=None, now=None):
    """Remember one update. Never raises into the caller."""
    from ..models.database import BrokerUpdate
    try:
        now = now or datetime.utcnow()
        if broker_id is not None:
            dup = (db.query(BrokerUpdate)
                     .filter(BrokerUpdate.kind == kind, BrokerUpdate.broker_id == broker_id,
                             BrokerUpdate.created_at >= now - timedelta(days=DEDUPE_DAYS)).first())
            if dup is not None:
                return dup
        row = BrokerUpdate(kind=kind, broker_id=broker_id, title=title[:300],
                           detail=(detail or "")[:4000] or None, created_at=now)
        db.add(row)
        db.flush()
        return row
    except Exception as e:
        log.warning("broker update not recorded (%s): %s", kind, e)
        return None


def unread_count(db) -> int:
    from ..models.database import BrokerUpdate
    return db.query(BrokerUpdate).filter(BrokerUpdate.read_at.is_(None)).count()


def listing(db, limit: int = 200, unread_only: bool = False) -> list:
    from ..models.database import BrokerUpdate, Broker
    q = db.query(BrokerUpdate)
    if unread_only:
        q = q.filter(BrokerUpdate.read_at.is_(None))
    rows = q.order_by(BrokerUpdate.created_at.desc()).limit(limit).all()
    names = {b.id: b.name for b in db.query(Broker).filter(
        Broker.id.in_({r.broker_id for r in rows if r.broker_id})).all()} if rows else {}
    return [{"id": r.id, "kind": r.kind, "level": KINDS.get(r.kind, ("info",))[0],
             "label": KINDS.get(r.kind, (None, r.kind))[1], "title": r.title, "detail": r.detail,
             "broker_id": r.broker_id, "broker_name": names.get(r.broker_id),
             "created_at": r.created_at.isoformat() if r.created_at else None,
             "read": r.read_at is not None} for r in rows]


def mark_read(db, ids=None, now=None) -> int:
    from ..models.database import BrokerUpdate
    now = now or datetime.utcnow()
    q = db.query(BrokerUpdate).filter(BrokerUpdate.read_at.is_(None))
    if ids:
        q = q.filter(BrokerUpdate.id.in_(list(ids)))
    n = 0
    for r in q.all():
        r.read_at = now
        n += 1
    db.commit()
    return n


def digest(db, cfg: dict, send=None, now=None) -> dict:
    """
    Email super administrators the updates they haven't been sent yet, at most
    once a day (or week). `send(subject, body, db)` defaults to
    admin_notify.send_admin_email.
    """
    from ..models.database import BrokerUpdate
    now = now or datetime.utcnow()
    s = settings_of(cfg)
    if s["email_digest"] not in ("daily", "weekly"):
        return {"sent": False, "reason": "off"}
    every = timedelta(days=7 if s["email_digest"] == "weekly" else 1) - timedelta(minutes=30)
    last = (cfg or {}).get("broker_updates_last_digest")
    if last:
        try:
            if now - datetime.fromisoformat(last.rstrip("Z")) < every:
                return {"sent": False, "reason": "not due"}
        except ValueError:
            pass
    rows = (db.query(BrokerUpdate).filter(BrokerUpdate.emailed_at.is_(None))
              .order_by(BrokerUpdate.created_at).all())
    if not rows:
        return {"sent": False, "reason": "nothing new"}
    order = {"urgent": 0, "review": 1, "info": 2}
    rows.sort(key=lambda r: (order.get(KINDS.get(r.kind, ("info",))[0], 3), r.created_at))
    urgent = sum(1 for r in rows if KINDS.get(r.kind, ("info",))[0] == "urgent")
    subject = f"OpenOptOut: {len(rows)} broker update{'s' if len(rows) != 1 else ''}" + \
              (f" ({urgent} need attention)" if urgent else "")
    lines = ["Here's what changed in your broker list.", ""]
    for r in rows:
        lines.append(f"- {KINDS.get(r.kind, (None, r.kind))[1]}: {r.title}")
        if r.detail:
            lines.append(f"  {r.detail}")
    lines += ["", "See them all, and mark them read, under Admin → Broker updates.",
              "To change how often this email comes, open Admin → Broker updates → Email digest."]
    if send is None:
        from .admin_notify import send_admin_email as send
    res = send(subject, "\n".join(lines), db)
    if res.get("sent"):
        for r in rows:
            r.emailed_at = now
        db.commit()
    return {"sent": bool(res.get("sent")), "count": len(rows), "error": res.get("error", "")}
