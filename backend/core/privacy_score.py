"""
Privacy score: how much of a person's known exposure has been cleaned up,
from 0 (every known listing still up) to 100 (none left).

For each site with a request for the person:
  gone        removed, or a check found nothing there        → 0 exposure
  waiting     request sent, no answer yet                     → half exposure
  exposed     still listed, found again, refused, failed,
              not sent yet, or waiting on the person          → full exposure
Each site counts by its priority (1–5; data wholesalers and big networks are
set higher), so getting off a site that feeds dozens of others moves the
score more than a small one.

    score = 100 × (1 − exposure ÷ total weight)

A daily snapshot is kept for each person (privacy_score_snapshots), so the
page and the PDF report can show where they started and how it's changed.
Nothing personal is stored in a snapshot: only counts and the score.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional

GONE, WAITING, EXPOSED = "gone", "waiting", "exposed"
EXPOSURE = {GONE: 0.0, WAITING: 0.5, EXPOSED: 1.0}


def site_state(req) -> str:
    st = getattr(req.status, "value", req.status)
    verdict = getattr(req, "last_verdict", None)
    if verdict == "listed":
        return EXPOSED
    if st == "confirmed" or verdict in ("gone", "not_found"):
        return GONE
    if st in ("sent", "submitted", "recheck_due"):
        return WAITING
    return EXPOSED


def _weight(broker) -> float:
    p = getattr(broker, "priority", None) or 3
    try:
        return float(max(1, min(5, int(p))))
    except (TypeError, ValueError):
        return 3.0


def compute(db, member) -> dict:
    """Score and counts for one person, from their requests as they are now."""
    from ..models.database import RemovalRequest
    reqs = db.query(RemovalRequest).filter(RemovalRequest.member_id == member.id).all()
    counts = {GONE: 0, WAITING: 0, EXPOSED: 0}
    total = exposure = 0.0
    for r in reqs:
        if r.broker is not None and getattr(r.broker, "is_test", False):
            continue
        s = site_state(r)
        w = _weight(r.broker)
        counts[s] += 1
        total += w
        exposure += w * EXPOSURE[s]
    score = None if total == 0 else round(100 * (1 - exposure / total))
    return {"member_id": member.id, "score": score, "sites": sum(counts.values()), **counts}


def combine(parts: list) -> Optional[int]:
    """Family score: each person's score weighted by how many sites they have."""
    have = [p for p in parts if p["score"] is not None and p["sites"]]
    if not have:
        return None
    return round(sum(p["score"] * p["sites"] for p in have) / sum(p["sites"] for p in have))


def snapshot(db, today: Optional[date] = None) -> int:
    """Record today's score for every person (one row per person per day). Returns rows written."""
    from ..models.database import FamilyMember, PrivacyScoreSnapshot
    today = today or datetime.utcnow().date()
    n = 0
    for m in db.query(FamilyMember).all():
        c = compute(db, m)
        if c["score"] is None:
            continue
        row = db.query(PrivacyScoreSnapshot).filter(PrivacyScoreSnapshot.member_id == m.id,
                                                    PrivacyScoreSnapshot.day == today).first()
        if row is None:
            row = PrivacyScoreSnapshot(member_id=m.id, day=today)
            db.add(row)
        row.score, row.sites = c["score"], c["sites"]
        row.gone, row.waiting, row.exposed = c[GONE], c[WAITING], c[EXPOSED]
        n += 1
    db.commit()
    return n


def report(db, member_ids: Iterable[int], today: Optional[date] = None) -> dict:
    """Now, where each person started, and the daily history, for the given people only."""
    from ..models.database import FamilyMember, PrivacyScoreSnapshot
    ids = list(member_ids)
    people = []
    by_day = {}
    for m in db.query(FamilyMember).filter(FamilyMember.id.in_(ids)).order_by(FamilyMember.id).all() if ids else []:
        now = compute(db, m)
        snaps = db.query(PrivacyScoreSnapshot).filter(PrivacyScoreSnapshot.member_id == m.id) \
            .order_by(PrivacyScoreSnapshot.day).all()
        first = snaps[0] if snaps else None
        people.append({
            "member_id": m.id, "name": m.full_name, "now": now,
            "start": {"day": first.day.isoformat(), "score": first.score, "sites": first.sites,
                      "exposed": first.exposed} if first else None,
            "history": [{"day": s.day.isoformat(), "score": s.score} for s in snaps],
        })
        for s in snaps:
            by_day.setdefault(s.day.isoformat(), []).append({"score": s.score, "sites": s.sites})
    family_history = [{"day": d, "score": combine(v)} for d, v in sorted(by_day.items())]
    starts = [p["start"] for p in people if p["start"]]
    return {
        "family": {
            "now": combine([p["now"] for p in people]),
            "start": family_history[0]["score"] if family_history else None,
            "start_day": family_history[0]["day"] if family_history else None,
            "history": family_history,
            "sites_now": sum(p["now"]["sites"] for p in people),
            "exposed_now": sum(p["now"][EXPOSED] for p in people),
            "exposed_start": sum(s["exposed"] for s in starts) if starts else None,
        },
        "people": people,
    }
