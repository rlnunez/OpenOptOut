"""
Deadline report and notices.
  GET   /api/compliance/report        sites that missed legal deadlines or relisted people
  GET   /api/compliance/report.csv    the same rows as a file (for a complaint)
  GET   /api/compliance/notices       this person's notice settings
  PATCH /api/compliance/notices       turn notices on or off

Every report is limited to the people the viewer can already see: their own
family, a manager's branches, or everyone for a super admin.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.auth import get_current_user, get_accessible_member_ids
from ..core import compliance as cp

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


class NoticePrefs(BaseModel):
    overdue: Optional[bool] = None
    relisted: Optional[bool] = None


@router.get("/report")
def deadline_report(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return cp.report(db, get_accessible_member_ids(db, current_user))


@router.get("/report.csv")
def deadline_report_csv(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rep = cp.report(db, get_accessible_member_ids(db, current_user))
    return Response(cp.to_csv(rep), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="deadline-report.csv"'})


@router.get("/notices")
def get_notices(current_user: User = Depends(get_current_user)):
    return {**cp.prefs(current_user), "email": current_user.email}


@router.patch("/notices")
def set_notices(data: NoticePrefs, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = cp.prefs(current_user)
    if data.overdue is not None:
        p["overdue"] = data.overdue
    if data.relisted is not None:
        p["relisted"] = data.relisted
    current_user.notification_prefs = json.dumps(p)
    db.commit()
    return {**p, "email": current_user.email}
