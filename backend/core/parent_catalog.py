"""
Built-in parent-company catalog.

Many broker sites are run by one company: one PeopleConnect request covers
Intelius, TruthFinder, Instant Checkmate and more; one email to
privacy@staterecords.org covers ~95 state arrest-record sites. The catalog in
core/catalog/parent_companies.json records those families, plus "cascades"
(an opt-out on one site that is known to clear another).

apply_catalog() turns the catalog into ParentCompany rows and groups matching
brokers under them, so the existing email-first parent dispatch (and the
admin Parent Companies page) can use them. It is safe to run repeatedly:

  - it never overwrites what an admin has already set on a parent,
  - it never moves a broker that is already grouped under a different parent
    (those are reported as conflicts for a person to decide),
  - it never touches test brokers,
  - it only fills in an opt-out email the catalog marks as verified, unless
    the caller explicitly opts in to unverified addresses. A parent without an
    email still groups its children; they keep using their own opt-out flows.
"""

import json
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "catalog", "parent_companies.json")

_TLDS = (".com", ".org", ".net", ".us", ".info", ".io", ".name")


def load_catalog(path: Optional[str] = None) -> dict:
    with open(path or CATALOG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("parents"), list):
        raise ValueError("parent catalog must be an object with a 'parents' list")
    return data


def normalize(name: str) -> str:
    """'https://www.Spokeo.com/' -> 'spokeo.com';  'Instant Checkmate' -> 'instantcheckmate'."""
    n = (name or "").strip().lower()
    for prefix in ("https://", "http://"):
        if n.startswith(prefix):
            n = n[len(prefix):]
    n = n.split("/")[0]
    if n.startswith("www."):
        n = n[4:]
    return n.replace(" ", "")


def _strip_tld(n: str) -> str:
    for t in _TLDS:
        if n.endswith(t):
            return n[: -len(t)]
    return n


def matches_child(broker_name: str, children: list, suffixes: list) -> bool:
    """
    Does a broker (by its stored name) belong to this parent?

    - Exact domain match: 'Spokeo.com' matches child 'spokeo.com'.
    - Brand-name match only when the broker name has no domain at all:
      a broker named 'Instant Checkmate' matches 'instantcheckmate.com', but
      'Publicrecords.us' does NOT match 'publicrecords.com' — a different TLD
      is usually a different company.
    - Suffix match for networks of state sites: 'Texasarrests.org' matches
      suffix 'arrests.org'.
    """
    n = normalize(broker_name)
    if not n:
        return False
    for c in children:
        cn = normalize(c)
        if n == cn:
            return True
        if "." not in n and n == _strip_tld(cn):
            return True
    for s in suffixes:
        sn = normalize(s)
        if n == sn or n.endswith(sn):
            return True
    return False


def cascades_for(broker_name: str, catalog: Optional[dict] = None) -> list:
    """Known cascades starting from this broker (informational; the engine
    never skips a direct opt-out because of one)."""
    catalog = catalog or load_catalog()
    n = normalize(broker_name)
    out = []
    for c in catalog.get("cascades", []):
        if any(normalize(f) == n or ("." not in n and _strip_tld(normalize(f)) == n)
               for f in c.get("from", [])):
            out.append(c)
    return out


def apply_catalog(db, dry_run: bool = False, include_unverified_emails: bool = False,
                  catalog: Optional[dict] = None) -> dict:
    """
    Create or update ParentCompany rows from the catalog and group matching
    brokers under them. Returns a report; with dry_run=True nothing is written.
    """
    from ..models.database import ParentCompany, Broker

    catalog = catalog or load_catalog()
    brokers = db.query(Broker).all()
    report = {"dry_run": dry_run, "parents_created": [], "parents_updated": [],
              "assigned": {}, "already_grouped": {}, "conflicts": [],
              "emails_held_for_review": []}

    for entry in catalog["parents"]:
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        email = (entry.get("optout_email") or "").strip()
        verified = bool(entry.get("email_verified"))
        use_email = email if (email and (verified or include_unverified_emails)) else ""
        if email and not use_email:
            report["emails_held_for_review"].append({"parent": name, "email": email,
                                                     "source": entry.get("email_source", "")})

        provenance = f"Source: {entry.get('source', 'unknown')}."
        if entry.get("last_verified"):
            provenance += f" Last verified: {entry['last_verified']}."
        if email and not use_email:
            provenance += (f" Candidate opt-out email (not yet confirmed): {email}"
                           f" — from {entry.get('email_source') or 'unknown source'}.")
        notes = (entry.get("notes", "") + "\n\n" + provenance).strip()

        parent = db.query(ParentCompany).filter(ParentCompany.name.ilike(name)).first()
        if parent is None:
            report["parents_created"].append(name)
            if not dry_run:
                parent = ParentCompany(name=name, optout_email=use_email or None,
                                       website=entry.get("website") or None,
                                       notes=notes, locale="en")
                db.add(parent)
                db.flush()
        else:
            changed = []
            if use_email and not parent.optout_email:
                changed.append("optout_email")
                if not dry_run:
                    parent.optout_email = use_email
            if entry.get("website") and not parent.website:
                changed.append("website")
                if not dry_run:
                    parent.website = entry["website"]
            if not parent.notes:
                changed.append("notes")
                if not dry_run:
                    parent.notes = notes
            if changed:
                report["parents_updated"].append({"parent": name, "fields": changed})

        children = entry.get("children", [])
        suffixes = entry.get("child_suffixes", [])
        for b in brokers:
            if getattr(b, "is_test", False):
                continue
            if not matches_child(b.name, children, suffixes):
                continue
            pid = parent.id if parent is not None else None
            if b.parent_company_id is None:
                report["assigned"].setdefault(name, []).append(b.name)
                if not dry_run:
                    b.parent_company_id = pid
            elif pid is not None and b.parent_company_id == pid:
                report["already_grouped"].setdefault(name, []).append(b.name)
            else:
                report["conflicts"].append({"broker": b.name, "catalog_parent": name,
                                            "current_parent_id": b.parent_company_id})

    if not dry_run:
        db.commit()
    report["assigned_count"] = sum(len(v) for v in report["assigned"].values())
    log.info("Parent catalog %s: %d parents created, %d brokers grouped, %d conflicts",
             "previewed" if dry_run else "applied", len(report["parents_created"]),
             report["assigned_count"], len(report["conflicts"]))
    return report
