"""
Per-variant removal tracking and report.

Brokers list people under several versions of their details: old addresses,
other phone numbers, a maiden name, a nickname. OpenOptOut already sends
every saved variant (email opt-outs list them all; form opt-outs submit each
combination). This module records WHICH saved details each request sent, so
the family can see how far removal has reached:

  main details   — the primary full name, current (primary) address and
                   primary phone number
  other variants — everything else in the identity vault

For each saved detail: how many brokers it was sent to, and how many of those
have confirmed removal. Requests sent before tracking existed, or finished by
hand, have no record of which details they carried; the report counts them
separately instead of guessing.
"""

from .combinations import _get_values, _parse_address, get_vault_limits

MAIN_KINDS = ("name", "address", "phone")
_SENT = ("sent", "submitted", "confirmed", "recheck_due")


# ── Which identities a submission used ────────────────────────────────────────

def _norm(s: str) -> str:
    return " ".join((s or "").lower().replace(",", " ").split())


def identities_in_email(member, limit: int = 0) -> list:
    """Identities an exhaustive opt-out email lists (same limits as the email)."""
    limits = get_vault_limits()
    out = []
    for kind in ("name", "address", "phone", "email"):
        values = set(_get_values(member, kind, limit or limits[kind]))
        out.extend(i.id for i in member.identities if i.kind == kind and i.value in values)
    return out


def identities_for_combo(member, combo) -> list:
    """Identities one form submission used (its name, address, phone, email)."""
    out = []
    for i in member.identities:
        if i.kind == "name" and combo.name and _norm(i.value) == _norm(combo.name):
            out.append(i.id)
        elif i.kind == "phone" and combo.phone and i.value == combo.phone:
            out.append(i.id)
        elif i.kind == "email" and combo.email and i.value.lower() == combo.email.lower():
            out.append(i.id)
        elif i.kind == "address" and combo.address:
            if _norm(_parse_address(i.value).get("address", "")) == _norm(combo.address):
                out.append(i.id)
    return out


def record(db, request_id: int, identity_ids) -> int:
    """Remember that this request sent these identities. Idempotent."""
    from ..models.database import RequestVariant
    if not request_id:
        return 0
    have = {rv.identity_id for rv in db.query(RequestVariant).filter(RequestVariant.request_id == request_id).all()}
    added = 0
    for iid in set(identity_ids or []) - have:
        db.add(RequestVariant(request_id=request_id, identity_id=iid))
        added += 1
    return added


# ── Report ────────────────────────────────────────────────────────────────────

def main_identity_ids(member) -> set:
    """Primary full name, current address, primary phone (first saved if none is marked primary)."""
    out = set()
    for kind in MAIN_KINDS:
        of_kind = [i for i in member.identities if i.kind == kind]
        primary = next((i for i in of_kind if i.is_primary), of_kind[0] if of_kind else None)
        if primary is not None:
            out.add(primary.id)
    return out


def _mask(kind: str, value: str) -> str:
    v = value or ""
    if kind == "phone":
        digits = "".join(c for c in v if c.isdigit())
        return f"••• {digits[-4:]}" if len(digits) >= 4 else "•••"
    if kind == "email" and "@" in v:
        local, domain = v.split("@", 1)
        return f"{local[:1]}•••@{domain}"
    if kind == "address":
        street = _parse_address(v).get("address") or v
        return street if len(street) <= 28 else street[:27] + "…"
    return v


def member_report(db, member) -> dict:
    from ..models.database import RemovalRequest, RequestVariant, RequestStatus
    reqs = db.query(RemovalRequest).filter(RemovalRequest.member_id == member.id).all()
    by_id = {r.id: r for r in reqs}
    links = db.query(RequestVariant).filter(RequestVariant.request_id.in_(list(by_id))).all() if by_id else []

    sent_states = {RequestStatus(s) for s in _SENT}
    sent_to, removed_at = {}, {}
    tracked = set()
    for rv in links:
        r = by_id[rv.request_id]
        if r.status not in sent_states:
            continue
        tracked.add(r.id)
        sent_to.setdefault(rv.identity_id, set()).add(r.broker_id)
        if r.status == RequestStatus.confirmed:
            removed_at.setdefault(rv.identity_id, set()).add(r.broker_id)
    untracked = sum(1 for r in reqs if r.status in sent_states and r.id not in tracked)

    main_ids = main_identity_ids(member)
    rows, totals = [], {"main": {"sent": 0, "removed": 0, "count": 0, "never_sent": 0},
                        "variants": {"sent": 0, "removed": 0, "count": 0, "never_sent": 0}}
    for i in sorted(member.identities, key=lambda x: (x.id not in main_ids, MAIN_KINDS.index(x.kind)
                                                       if x.kind in MAIN_KINDS else 9, not x.is_primary, x.id)):
        group = "main" if i.id in main_ids else "variants"
        s, rm = len(sent_to.get(i.id, ())), len(removed_at.get(i.id, ()))
        t = totals[group]
        t["count"] += 1; t["sent"] += s; t["removed"] += rm
        if s == 0:
            t["never_sent"] += 1
        rows.append({"identity_id": i.id, "kind": i.kind, "label": _mask(i.kind, i.value),
                     "group": group, "brokers_sent": s, "brokers_removed": rm})
    for t in totals.values():
        t["percent_removed"] = round(100 * t["removed"] / t["sent"]) if t["sent"] else None
    return {"member_id": member.id, "member_name": member.full_name, "main": totals["main"],
            "variants": totals["variants"], "details": rows, "untracked_requests": untracked}


def family_report(db, member_ids: list) -> dict:
    from ..models.database import FamilyMember
    members = db.query(FamilyMember).filter(FamilyMember.id.in_(member_ids)).order_by(FamilyMember.created_at).all()
    per = [member_report(db, m) for m in members]
    agg = {}
    for g in ("main", "variants"):
        sent = sum(p[g]["sent"] for p in per)
        removed = sum(p[g]["removed"] for p in per)
        agg[g] = {"sent": sent, "removed": removed,
                  "percent_removed": round(100 * removed / sent) if sent else None,
                  "count": sum(p[g]["count"] for p in per),
                  "never_sent": sum(p[g]["never_sent"] for p in per)}
    return {"family": agg, "members": per,
            "untracked_requests": sum(p["untracked_requests"] for p in per)}
