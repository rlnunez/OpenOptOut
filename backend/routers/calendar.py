"""
Calendar.
  GET    /api/calendar                 upcoming opt-out days, checks and legal deadlines
  GET    /api/calendar/my.ics          the same as a file to import
  POST   /api/calendar/feed            make (or replace) my private subscription link
  DELETE /api/calendar/feed            turn my subscription link off
  GET    /api/calendar/feed/{token}.ics  the subscription itself (no sign-in; the token is the key)

Scope is the person's own family (scope=all: everyone they may see, for staff).
Feeds always cover the account's own family only.
"""
import secrets
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.auth import get_current_user
from ..core.settings_store import load_settings
from ..core import calendar_plan as cal
from .reports import _scope_ids
from ..core.compliance import own_member_ids

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


def _sc():
    return (load_settings().get("scheduler") or {})


@router.get("")
def calendar(scope: str = Query("family"), start: Optional[str] = None, days: int = Query(62, ge=1, le=400),
             db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        d0 = date.fromisoformat(start) if start else None
    except ValueError:
        raise HTTPException(400, "Use a date like 2026-11-01.")
    sc = _sc()
    return {"events": cal.upcoming(db, _scope_ids(db, current_user, scope, None), sc, start=d0, days=days),
            "run_days": sc.get("run_days"), "skip_dates": sc.get("skip_dates") or [],
            "run_time": sc.get("run_time", "02:00"), "timezone": sc.get("timezone", "America/Chicago"),
            "enabled": bool(sc.get("enabled")), "has_feed": bool(current_user.calendar_token_hash)}


def _ics(db, user):
    return cal.to_ics(cal.upcoming(db, own_member_ids(db, user), _sc(), days=180), name="OpenOptOut removals")


@router.get("/my.ics")
def my_ics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return Response(_ics(db, current_user), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="openoptout.ics"'})


@router.post("/feed")
def make_feed(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    token = secrets.token_urlsafe(32)
    current_user.calendar_token_hash = cal.token_hash(token)
    db.commit()
    base = str(request.base_url).rstrip("/")
    return {"url": f"{base}/api/calendar/feed/{token}.ics",
            "note": "Anyone with this link can see your family's removal dates (first names and sites only). "
                    "Make a new one to turn the old one off."}


@router.delete("/feed", status_code=204)
def drop_feed(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.calendar_token_hash = None
    db.commit()


@router.get("/feed/{token}.ics")
def feed(token: str, db: Session = Depends(get_db)):
    if len(token) < 20:
        raise HTTPException(404, "Not found")
    user = db.query(User).filter(User.calendar_token_hash == cal.token_hash(token)).first()
    if user is None:
        raise HTTPException(404, "Not found")
    return Response(_ics(db, user), media_type="text/calendar",
                    headers={"Cache-Control": "private, max-age=900"})
