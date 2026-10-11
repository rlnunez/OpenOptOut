"""
Who shares with whom, and who to opt out of first.

1. Sharing signals. Every opt-out gets its own email address (core/mailboxes,
   ContactAddress). An address given only to broker A that later receives mail
   from company X means A (or someone it gave the address to) passed it on.
   sharing_edges() turns those records into "A → X" edges:

     possible   one opt-out address reached X
     likely     two different opt-out addresses given to A reached X
     strong     three or more

   Mail from free email services (gmail.com...) is shown but can't name a
   company; the broker's own domains and its parent's never count.

2. Aggregator-first targeting. upstream_scores() rates how much one opt-out
   is worth: known data wholesalers (catalog/aggregators.json), known
   "opting out here also removes you there" cascades (parent catalog), the
   size of a parent's family of sites, and observed sharing edges. The
   scheduler's "aggregators_first" dispatch order sends those first, so
   downstream sites have less to re-scrape.
"""

import json
import logging
import os
from collections import defaultdict

log = logging.getLogger(__name__)

CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog", "aggregators.json")
FREE_EMAIL = {"gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "outlook.com", "hotmail.com",
              "live.com", "msn.com", "aol.com", "icloud.com", "me.com", "proton.me", "protonmail.com",
              "gmx.com", "gmx.net", "mail.com", "zoho.com", "yandex.com", "fastmail.com"}


def load_aggregators() -> list:
    try:
        with open(CATALOG, encoding="utf-8") as f:
            return json.load(f).get("aggregators", [])
    except Exception as e:
        log.warning("aggregator catalog unreadable: %s", e)
        return []


def _reg(host: str) -> str:
    from .listing_finder import registrable_domain
    return registrable_domain((host or "").lower().strip("."))


def _broker_regs(broker) -> set:
    from .mailboxes import _broker_domains
    return {_reg(d) for d in _broker_domains(broker)} if broker is not None else set()


def _domain_index(db) -> dict:
    """registrable domain -> Broker, for naming the receiving company."""
    from ..models.database import Broker
    idx = {}
    for b in db.query(Broker).all():
        for d in _broker_regs(b):
            idx.setdefault(d, b)
    return idx


def confidence(addresses: int) -> str:
    return "strong" if addresses >= 3 else "likely" if addresses >= 2 else "possible"


def sharing_edges(db) -> list:
    """
    [{from_type, from_id, from_name, to_domain, to_broker_id, to_name, addresses,
      members, confidence, free_email}] from opt-out addresses that received mail
    from someone other than the company they were given to.
    """
    from ..models.database import ContactAddress, Broker, ParentCompany
    idx = _domain_index(db)
    brokers = {b.id: b for b in db.query(Broker).all()}
    parents = {p.id: p for p in db.query(ParentCompany).all()}
    agg = defaultdict(lambda: {"addresses": set(), "members": set()})
    for ca in db.query(ContactAddress).filter(ContactAddress.unexpected_senders.isnot(None)).all():
        if ca.parent_company_id:
            key_from = ("parent", ca.parent_company_id)
            p = parents.get(ca.parent_company_id)
            own = set()
            if p is not None:
                own |= {_reg(p.website or "")}
                for c in (p.children or []):
                    own |= _broker_regs(c)
        elif ca.broker_id:
            key_from = ("broker", ca.broker_id)
            b = brokers.get(ca.broker_id)
            own = _broker_regs(b)
            if b is not None and b.parent is not None:
                own |= {_reg(b.parent.website or "")}
                for c in (b.parent.children or []):
                    own |= _broker_regs(c)
        else:
            continue
        for dom in {d.strip().lower() for d in (ca.unexpected_senders or "").split(",") if d.strip()}:
            reg = _reg(dom)
            if not reg or reg in own:
                continue
            e = agg[(key_from, reg)]
            e["addresses"].add(ca.id)
            e["members"].add(ca.member_id)
    out = []
    for ((ftype, fid), reg), e in agg.items():
        frm = brokers.get(fid) if ftype == "broker" else parents.get(fid)
        to = idx.get(reg)
        n = len(e["addresses"])
        out.append({"from_type": ftype, "from_id": fid, "from_name": getattr(frm, "name", "?"),
                    "to_domain": reg, "to_broker_id": to.id if to else None,
                    "to_name": to.name if to else (None if reg in FREE_EMAIL else reg),
                    "addresses": n, "members": len(e["members"]),
                    "confidence": "unknown_sender" if reg in FREE_EMAIL else confidence(n),
                    "free_email": reg in FREE_EMAIL})
    order = {"strong": 0, "likely": 1, "possible": 2, "unknown_sender": 3}
    out.sort(key=lambda x: (order[x["confidence"]], -x["addresses"], x["from_name"]))
    return out


# ── How much an opt-out is worth ──────────────────────────────────────────────

def upstream_scores(db, edges=None) -> dict:
    """broker_id -> {"score": float, "reasons": [str]}. 0 for ordinary sites."""
    from ..models.database import Broker
    from .parent_catalog import load_catalog, normalize
    out = defaultdict(lambda: {"score": 0.0, "reasons": []})
    brokers = db.query(Broker).all()
    by_reg = defaultdict(list)
    for b in brokers:
        for d in _broker_regs(b):
            by_reg[d].append(b)

    for a in load_aggregators():
        for d in a.get("domains", []):
            for b in by_reg.get(_reg(d), []):
                out[b.id]["score"] += float(a.get("weight", 5))
                out[b.id]["reasons"].append(f"data wholesaler: {a.get('role', a['name'])}")
    try:
        cascades = load_catalog().get("cascades", [])
    except Exception:
        cascades = []
    for c in cascades:
        if c.get("confidence") == "historical":
            continue
        for f in c.get("from", []):
            for b in by_reg.get(_reg(normalize(f)), []):
                n = len(c.get("to", []))
                out[b.id]["score"] += 2.0 * n
                out[b.id]["reasons"].append(f"opting out also removes {', '.join(c.get('to', []))}")
    for b in brokers:
        if b.parent is not None:
            kids = len(b.parent.children or [])
            if kids > 1:
                out[b.id]["score"] += min(kids, 20) * 0.25
                out[b.id]["reasons"].append(f"part of {b.parent.name} ({kids} sites)")
    edges = sharing_edges(db) if edges is None else edges
    weight = {"strong": 3.0, "likely": 2.0, "possible": 1.0}
    for e in edges:
        if e["free_email"] or e["confidence"] not in weight:
            continue
        ids = [e["from_id"]] if e["from_type"] == "broker" else [b.id for b in brokers if b.parent_company_id == e["from_id"]]
        for bid in ids:
            out[bid]["score"] += weight[e["confidence"]]
            out[bid]["reasons"].append(f"shared opt-out addresses with {e['to_name'] or e['to_domain']} ({e['confidence']})")
    return {k: {"score": round(v["score"], 2), "reasons": v["reasons"]} for k, v in out.items()}


_CACHE = {"scores": None}


def scores_for_dispatch(db) -> dict:
    """broker_id -> score, cached per scheduler run (call reset_cache() to refresh)."""
    if _CACHE["scores"] is None:
        _CACHE["scores"] = {k: v["score"] for k, v in upstream_scores(db).items()}
    return _CACHE["scores"]


def reset_cache():
    _CACHE["scores"] = None


def ranking(db, limit: int = 100) -> list:
    from ..models.database import Broker
    sc = upstream_scores(db)
    names = {b.id: b for b in db.query(Broker).filter(Broker.id.in_(list(sc))).all()} if sc else {}
    rows = [{"broker_id": bid, "broker_name": names[bid].name, "enabled": bool(names[bid].enabled),
             "priority": names[bid].priority, "score": v["score"], "reasons": v["reasons"]}
            for bid, v in sc.items() if bid in names and v["score"] > 0]
    rows.sort(key=lambda r: -r["score"])
    return rows[:limit]
