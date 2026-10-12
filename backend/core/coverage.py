"""
How many sites each broker's opt-out reaches.

One opt-out often clears more than one site: PeopleConnect's suppression
request covers Intelius, TruthFinder, Instant Checkmate and more, and one
email to InfoPay asks all seven of its sites. This module adds that up so the
Brokers page can say "also removes you from 10 other sites" and "the 74
brokers turned on cover 112 sites".

Where it comes from, in order:

  1. the broker plugin's own `covers` list (spec.json), written by whoever
     researched that broker;
  2. the parent-company catalog (core/catalog/parent_companies.json): when a
     family is marked `one_optout_covers`, a broker in it covers the others;
     `approx_sites` counts a network of look-alike state sites, and
     `not_covered` names family sites that need their own opt-out;
  3. catalog cascades: "confirmed" ones count as covered, "likely" ones are
     listed separately as "may also clear", and "historical" ones are left out.

"Covers" means the company says one request reaches those sites. OpenOptOut
hasn't checked each one, and the engine never skips a direct opt-out because
of it. Nothing here reads anyone's details.
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, Optional

from .parent_catalog import load_catalog, matches_child, normalize

log = logging.getLogger(__name__)


def site_of(value: str) -> str:
    """'https://suppression.peopleconnect.us/login' -> 'peopleconnect.us';
    a broker name without a dot stays as it is ('spokeo')."""
    n = normalize(value)
    if "." not in n:
        return n
    parts = n.split(".")
    return ".".join(parts[-2:]) if len(parts) > 2 else n


def broker_site(broker) -> str:
    """The broker's own site: its opt-out page's domain, else its name."""
    for v in (getattr(broker, "opt_out_url", "") or "", getattr(broker, "name", "") or ""):
        s = site_of(v)
        if "." in s:
            return s
    return site_of(getattr(broker, "name", "") or "")


def coverage(site: str, name: str = "", spec_covers: Iterable[str] = (),
             catalog: Optional[dict] = None) -> dict:
    """{"sites": [...], "maybe": [...], "network_sites": n, "count": n}.

    `count` is how many other sites the opt-out covers: the listed ones plus
    a network's approximate size. `maybe` is never counted."""
    catalog = catalog if catalog is not None else _catalog()
    own = {site, normalize(name)} - {""}
    sure = {site_of(d) for d in spec_covers if d}
    network, network_name = 0, ""
    for p in catalog.get("parents", []):
        if not p.get("one_optout_covers"):
            continue
        kids, sufs = p.get("children", []), p.get("child_suffixes", [])
        home = site_of(p.get("website", ""))
        if not any(matches_child(x, kids, sufs) for x in own) and site not in (home,):
            continue
        sure |= {site_of(c) for c in kids} - {site_of(c) for c in p.get("not_covered", [])}
        if int(p.get("approx_sites") or 0) > network:
            network, network_name = int(p["approx_sites"]), p.get("name", "")
    maybe = set()
    for c in catalog.get("cascades", []):
        if not any(site_of(f) in own for f in c.get("from", [])):
            continue
        to = {site_of(t) for t in c.get("to", [])}
        if c.get("confidence") == "confirmed":
            sure |= to
        elif c.get("confidence") == "likely":
            maybe |= to
    sure -= own
    maybe -= sure | own
    # A network of state sites counts by its size, less the ones listed by name.
    extra = max(0, network - len(sure)) if network else 0
    return {"sites": sorted(sure), "maybe": sorted(maybe), "network_sites": extra,
            "network": network_name if extra else "", "count": len(sure) + extra}


def _catalog() -> dict:
    try:
        return load_catalog()
    except Exception as e:                      # a broken catalog shouldn't break the page
        log.warning("Parent catalog unreadable: %s", type(e).__name__)
        return {"parents": [], "cascades": []}


def for_brokers(db, brokers) -> Dict[int, dict]:
    """Coverage for each broker, by id."""
    from ..plugins.broker_addon import get_broker_spec_for_broker
    catalog = _catalog()
    out = {}
    for b in brokers:
        spec = None
        if getattr(b, "plugin_id", None):
            try:
                spec = get_broker_spec_for_broker(db, b)
            except Exception:
                spec = None
        c = coverage(broker_site(b), b.name or "", getattr(spec, "covers", []) or [], catalog)
        c["site"] = broker_site(b)
        out[b.id] = c
    return out


def summary(db) -> dict:
    """Coverage for every broker, and how many distinct sites the turned-on
    ones reach between them (each site counted once)."""
    from ..models.database import Broker
    brokers = db.query(Broker).filter(Broker.is_test.isnot(True)).all()
    per = for_brokers(db, brokers)
    on = [b for b in brokers if b.enabled]
    sites, networks = set(), {}
    for b in on:
        c = per[b.id]
        sites.add(c["site"])
        sites.update(c["sites"])
        if c["network"]:            # one network counts once, however many of its sites are on
            networks[c["network"]] = max(networks.get(c["network"], 0), c["network_sites"])
    return {"brokers_on": len(on), "brokers": len(brokers),
            "sites_covered": len(sites) + sum(networks.values()),
            "coverage": {str(k): v for k, v in per.items()}}
