"""
Listings found on a broker that's turned off.

Discovery, web search and "Find your listings" can find someone on a broker
that's turned off: a built-in plugin nobody has checked yet (it ships off), or
a broker an admin hasn't turned on. A real listing answers the two worries
that kept it off: the site is alive, and the person is already on it, so an
opt-out can't create a record that wasn't there. What happens next is the
admin's choice (Admin → Settings, "When a listing is found on a broker that's
turned off"):

  auto   Turn the broker on once listings are found for at least `threshold`
         different people, and opt out automatically. Only for a broker with
         an installed plugin that nobody turned off on purpose: never one an
         admin switched off, the health monitor turned off after failures, or
         whose website is gone. Below the threshold, or when it can't turn on,
         `fallback` applies.
  ask    Tell admins on Broker updates: "Found for 3 people on X, which is
         turned off", with a Turn on button. Requests wait until it's on.
  tell   Put it on the person's checklist: their details were found on X,
         OpenOptOut can't remove them automatically yet, and here is the
         opt-out page. If the broker is turned on later, the request goes back
         to OpenOptOut.

Counts are of distinct people, never listings, and nothing here records who
was found: Broker updates name the broker and a number only.
Brokers imported from a state registry are left to core/broker_gate.py, which
already sends for a person with a listing while the broker is off.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

ACTIONS = ("auto", "ask", "tell")
FALLBACKS = ("ask", "tell")
DEFAULTS = {"action": "ask", "threshold": 1, "fallback": "ask"}
MAX_THRESHOLD = 100_000

TELL_TEXT = ("{name}'s details were found on {broker}. OpenOptOut can't remove them from this site "
             "automatically yet. Open the site's opt-out page, follow its steps, then press \"I've done this\". "
             "If an admin turns this site on later, OpenOptOut takes over.")
TELL_TEXT_NO_PAGE = ("{name}'s details were found on {broker}. OpenOptOut can't remove them from this site "
                     "automatically yet, and doesn't know its opt-out page. Look for a \"privacy\", "
                     "\"opt out\" or \"do not sell\" link at the bottom of the listing, follow its steps, then "
                     "press \"I've done this\". If an admin turns this site on later, OpenOptOut takes over.")


def settings_of(cfg: Optional[dict] = None) -> dict:
    if cfg is None:
        from .settings_store import load_settings
        cfg = load_settings()
    out = dict(DEFAULTS)
    out.update((cfg or {}).get("found_listings") or {})
    if out["action"] not in ACTIONS:
        out["action"] = DEFAULTS["action"]
    if out["fallback"] not in FALLBACKS:
        out["fallback"] = DEFAULTS["fallback"]
    try:
        out["threshold"] = max(1, min(MAX_THRESHOLD, int(out["threshold"])))
    except (TypeError, ValueError):
        out["threshold"] = 1
    return out


def clean(data: dict) -> dict:
    """Validate an admin's settings; raises ValueError in plain words."""
    out = settings_of({"found_listings": {}})
    if "action" in data:
        if data["action"] not in ACTIONS:
            raise ValueError("Choose one of: turn it on, ask an admin, or tell the person.")
        out["action"] = data["action"]
    if "fallback" in data:
        if data["fallback"] not in FALLBACKS:
            raise ValueError("Choose what happens until then: ask an admin, or tell the person.")
        out["fallback"] = data["fallback"]
    if "threshold" in data:
        try:
            n = int(data["threshold"])
        except (TypeError, ValueError):
            raise ValueError("The number of people must be a whole number.")
        if not 1 <= n <= MAX_THRESHOLD:
            raise ValueError("The number of people must be between 1 and 100,000.")
        out["threshold"] = n
    return out


def people_found(db, broker_id: int) -> int:
    """How many different people have a listing found on this broker."""
    from ..models.database import DiscoveryResult
    return (db.query(DiscoveryResult.member_id)
              .filter(DiscoveryResult.broker_id == broker_id, DiscoveryResult.found.is_(True))
              .distinct().count())


def can_turn_on(db, broker) -> tuple:
    """(ok, why not). Turning on automatically is only for a broker with an
    installed plugin that nobody turned off on purpose."""
    from ..models.database import BrokerHealth, InstalledPlugin
    if not broker.plugin_id:
        return False, "no_plugin"
    p = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == broker.plugin_id).first()
    if p is None or not p.enabled:
        return False, "no_plugin"
    h = db.query(BrokerHealth).filter(BrokerHealth.broker_id == broker.id).first()
    if h is not None:
        if h.defunct:
            return False, "defunct"
        if h.auto_disabled:
            return False, "failing"
        if h.auto_disabled_reason:          # an admin turned it off by hand
            return False, "turned_off"
    return True, ""


def handle(db, broker, member_id: int, cfg: Optional[dict] = None) -> str:
    """Call after recording a found listing (a DiscoveryResult with found=True)
    for this member on this broker. Returns what happened: "" (nothing to do),
    "turned_on", "asked" or "told". Never raises into the caller."""
    try:
        return _handle(db, broker, member_id, cfg)
    except Exception as e:
        log.warning("found-listing rule skipped for broker %s: %s", getattr(broker, "id", "?"), type(e).__name__)
        return ""


def _handle(db, broker, member_id: int, cfg: Optional[dict]) -> str:
    if broker is None or broker.enabled or getattr(broker, "is_test", False):
        return ""
    if (getattr(broker, "origin", None) or "curated") == "registry":
        return ""                                   # broker_gate.py handles these
    s = settings_of(cfg)
    n = people_found(db, broker.id)
    action = s["action"]
    if action == "auto":
        ok, why = can_turn_on(db, broker)
        if ok and n >= s["threshold"]:
            turn_on(db, broker, reason=f"listings were found for {n} {'person' if n == 1 else 'people'}")
            return "turned_on"
        action = s["fallback"]
        if ok:
            note = f" It turns on by itself at {s['threshold']} people."
        else:
            note = {"no_plugin": " It has no plugin, so it can't be turned on by itself.",
                    "defunct": " Its website looked gone, so it isn't turned on by itself.",
                    "failing": " It was turned off after failing, so it isn't turned on by itself.",
                    "turned_off": " An admin turned it off, so it isn't turned on by itself."}.get(why, "")
    else:
        note = ""
    if action == "ask":
        _ask(db, broker, n, note)
        return "asked"
    _tell(db, broker, member_id)
    return "told"


def _ask(db, broker, n: int, note: str) -> None:
    from .broker_updates import record
    from ..models.database import BrokerUpdate
    title = f"Listings found for {n} {'person' if n == 1 else 'people'} on {broker.name}, which is turned off"
    detail = ("Their opt-outs wait until it's turned on. A found listing shows the site is live and already "
              "lists them, so an opt-out can't add anyone new." + note)
    # Keep one entry per broker, with the count up to date, instead of one per listing.
    row = (db.query(BrokerUpdate).filter(BrokerUpdate.kind == "found_while_off",
                                         BrokerUpdate.broker_id == broker.id,
                                         BrokerUpdate.read_at.is_(None)).first())
    if row is not None:
        row.title, row.detail = title[:300], detail
        db.flush()
    else:
        row = record(db, "found_while_off", title, detail, broker_id=broker.id)
        if row is not None and row.title != title[:300]:    # an old, read entry within the dedupe window
            row.title, row.detail, row.read_at = title[:300], detail, None
            db.flush()
    db.commit()


def _tell(db, broker, member_id: int) -> None:
    from ..models.database import RemovalRequest, RequestStatus, FamilyMember
    member = db.query(FamilyMember).filter(FamilyMember.id == member_id).first()
    if member is None:
        return
    req = (db.query(RemovalRequest)
             .filter(RemovalRequest.member_id == member_id, RemovalRequest.broker_id == broker.id,
                     RemovalRequest.status == RequestStatus.pending)
             .order_by(RemovalRequest.created_at.desc()).first())
    if req is None:
        return
    text = TELL_TEXT if broker.opt_out_url else TELL_TEXT_NO_PAGE
    req.status = RequestStatus.needs_manual
    req.waiting_for = "broker_off"
    req.notes = text.format(name=member.full_name, broker=broker.name)
    db.commit()


def turn_on(db, broker, reason: str = "") -> int:
    """Turn a broker on and give back to OpenOptOut the requests people were
    told to do by hand while it was off. Returns how many went back."""
    from .broker_health import re_enable
    from .broker_updates import record
    re_enable(db, broker.id, clear_review=False)
    n = resume(db, broker)
    if reason:
        record(db, "turned_on_found", f"{broker.name} was turned on automatically: {reason}",
               "Change this under Admin → Settings, \"When a listing is found on a broker that's turned off\".",
               broker_id=broker.id)
        db.commit()
    return n


def resume(db, broker) -> int:
    """When a broker is turned on (by anyone), requests waiting for it go back
    to OpenOptOut."""
    from ..models.database import RemovalRequest, RequestStatus
    rows = (db.query(RemovalRequest)
              .filter(RemovalRequest.broker_id == broker.id, RemovalRequest.waiting_for == "broker_off",
                      RemovalRequest.status == RequestStatus.needs_manual).all())
    for r in rows:
        r.status, r.waiting_for, r.notes = RequestStatus.pending, None, None
    if rows:
        db.commit()
    return len(rows)


def apply_now(db, cfg: Optional[dict] = None) -> list:
    """After the rule changes: turn on the brokers already over the threshold
    (auto), or tell the people already found on the others (tell). Returns the
    names of the brokers turned on."""
    s = settings_of(cfg)
    from ..models.database import Broker, DiscoveryResult
    out = []
    for w in waiting(db):
        b = db.query(Broker).get(w["broker_id"])
        if s["action"] == "auto" and w["can_auto"] and w["people"] >= s["threshold"]:
            n = w["people"]
            turn_on(db, b, reason=f"listings were found for {n} {'person' if n == 1 else 'people'}")
            out.append(b.name)
            continue
        effective = s["action"] if s["action"] != "auto" else s["fallback"]
        if effective == "tell":
            # People already found there get the steps on their checklist now.
            for (mid,) in (db.query(DiscoveryResult.member_id)
                             .filter(DiscoveryResult.broker_id == b.id, DiscoveryResult.found.is_(True))
                             .distinct().all()):
                _tell(db, b, mid)
    return out


def waiting(db) -> list:
    """For the admin page: brokers that are off with listings found, and for
    how many people. Counts only."""
    from sqlalchemy import func
    from ..models.database import Broker, DiscoveryResult
    rows = (db.query(Broker.id, Broker.name, func.count(func.distinct(DiscoveryResult.member_id)))
              .join(DiscoveryResult, DiscoveryResult.broker_id == Broker.id)
              .filter(Broker.enabled.is_(False), Broker.is_test.isnot(True), DiscoveryResult.found.is_(True))
              .group_by(Broker.id, Broker.name).order_by(func.count(func.distinct(DiscoveryResult.member_id)).desc())
              .all())
    out = []
    for bid, name, n in rows:
        b = db.query(Broker).get(bid)
        if (getattr(b, "origin", None) or "curated") == "registry":
            continue
        ok, why = can_turn_on(db, b)
        out.append({"broker_id": bid, "name": name, "people": n, "can_auto": ok, "why_not": why})
    return out
