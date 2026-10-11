"""
Privacy score and removal reports.
  GET /api/reports/score            privacy score now, where it started, daily history
  GET /api/reports/removal.pdf      detailed removal report as a PDF

scope=family (default): the person's own family and profiles shared with them.
scope=all: everyone the viewer may see (a manager's branches, or everyone for a
super admin) — for staff reporting. Never more than get_accessible_member_ids.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.auth import get_current_user, get_accessible_member_ids
from ..core.compliance import own_member_ids
from ..core import privacy_score as ps

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _scope_ids(db, user, scope: str, member_id: Optional[int]) -> list:
    if scope not in ("family", "all"):
        raise HTTPException(400, "Choose your family or everyone you can see.")
    allowed = set(get_accessible_member_ids(db, user))
    ids = [i for i in own_member_ids(db, user) if i in allowed] if scope == "family" else sorted(allowed)
    if member_id is not None:
        if member_id not in allowed:
            raise HTTPException(403, "You don't have access to this person.")
        ids = [member_id]
    return ids


@router.get("/score")
def privacy_score(scope: str = Query("family"), member_id: Optional[int] = None,
                  db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return ps.report(db, _scope_ids(db, current_user, scope, member_id))


@router.get("/removal.pdf")
def removal_pdf(scope: str = Query("family"), member_id: Optional[int] = None,
                db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..core import removal_report as rr
    from ..core.privacy_record import log_access
    from ..models.database import FamilyMember
    ids = _scope_ids(db, current_user, scope, member_id)
    own = set(own_member_ids(db, current_user))
    for m in db.query(FamilyMember).filter(FamilyMember.id.in_([i for i in ids if i not in own])).all():
        log_access(db, current_user, m, "export", "removal report (PDF)")
    data = rr.gather(db, ids)
    title = "Removal report" if len(data["people"]) != 1 else f"Removal report: {data['people'][0]['name']}"
    pdf = rr.render(data, title=title)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="openoptout-removal-report.pdf"'})
