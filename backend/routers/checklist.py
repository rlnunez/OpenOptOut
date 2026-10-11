"""
The checklist. See core/checklist.py.

  GET  /api/checklist                    everything that needs a person + progress
  GET  /api/checklist/count              how many items (for the sidebar badge)
  POST /api/checklist/{req_id}/done      "I've done this" (finished an opt-out by hand)
  POST /api/checklist/{req_id}/removed   "The listing is gone" (overdue or re-check items)
  POST /api/checklist/confirm/{id}/done  "I've confirmed it" (clicked a broker's confirmation link)

"Send again" and "check later" use the existing
/api/requests/{id}/requeue and /api/requests/{id}/snooze.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models.database import get_db, User, RemovalRequest, RequestStatus, ConfirmationLink
from ..core.settings_store import load_settings
from ..core import confirm_links
from ..core.auth import get_current_user, get_accessible_member_ids, assert_can_edit
from ..core import checklist as cl

router = APIRouter(prefix="/api/checklist", tags=["checklist"])


def _ids(db, user, member_id: Optional[int]):
    ids = get_accessible_member_ids(db, user)
    if member_id is not None:
        if member_id not in ids:
            raise HTTPException(403, "You don't have access to this person.")
        return [member_id]
    return ids


@router.get("")
def get_checklist(member_id: Optional[int] = Query(None), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    return cl.build(db, _ids(db, user, member_id))


@router.get("/count")
def count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = cl.build(db, _ids(db, user, None))
    g = data["groups"]
    return {"count": sum(len(g[k]) for k in ("inbox", "finish", "confirm", "captcha", "review", "overdue"))}


def _req(db, user, req_id) -> RemovalRequest:
    r = db.query(RemovalRequest).filter(RemovalRequest.id == req_id).first()
    if not r:
        raise HTTPException(404, "That item is gone.")
    assert_can_edit(db, user, r.member_id)
    return r


@router.post("/{req_id}/done")
def done(req_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = _req(db, user, req_id)
    if r.status != RequestStatus.needs_manual:
        raise HTTPException(400, "This one doesn't need finishing by hand.")
    cl.mark_done(db, r, user.full_name or "a family member")
    return {"ok": True, "message": f"Marked done. OpenOptOut will check {r.broker.name} again in 90 days."}


@router.post("/{req_id}/removed")
def removed(req_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = _req(db, user, req_id)
    if r.status not in (RequestStatus.sent, RequestStatus.submitted, RequestStatus.confirmed):
        raise HTTPException(400, "This one hasn't been sent yet.")
    cl.mark_removed(db, r, user.full_name or "a family member")
    return {"ok": True, "message": f"Great — {r.broker.name} is marked removed."}


@router.post("/confirm/{link_id}/done")
def confirmed(link_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(ConfirmationLink).filter(ConfirmationLink.id == link_id).first()
    if not c:
        raise HTTPException(404, "That item is gone.")
    r = _req(db, user, c.request_id)
    confirm_links.mark_done(db, c, load_settings(), user.full_name or "a family member")
    return {"ok": True, "message": f"Thanks — {r.broker.name} is confirmed. OpenOptOut will check it again in 90 days."}
