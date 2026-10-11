"""
Per-variant removal report. See core/variant_report.py.

  GET /api/variants/report?member_id=   main details vs other variants, per family member
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.auth import get_current_user, get_accessible_member_ids
from ..core import variant_report as vr

router = APIRouter(prefix="/api/variants", tags=["variants"])


@router.get("/report")
def report(member_id: Optional[int] = Query(None), db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    ids = get_accessible_member_ids(db, user)
    if member_id is not None:
        if member_id not in ids:
            raise HTTPException(403, "You don't have access to this person.")
        ids = [member_id]
    return vr.family_report(db, ids)
