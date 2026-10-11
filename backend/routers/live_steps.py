"""
"Do it here": finish a step only a person can do, in the real page.

An opt-out that stopped for a person (a pause_for_human step such as
"pick your listing", "enter the code we texted you" or "answer the
question", or a form OpenOptOut wasn't sure how to fill) can be picked up
live from the Checklist. See core/live_captcha.py (kind "step").

  POST   /api/live-steps/{request_id}           start (or rejoin) a session
  GET    /api/live-steps/{request_id}           state, and what to do
  GET    /api/live-steps/{request_id}/frame     a picture of the page (JPEG, not stored)
  POST   /api/live-steps/{request_id}/input     a click, typing, a key or scrolling
  POST   /api/live-steps/{request_id}/done      "I've done this step"
  DELETE /api/live-steps/{request_id}           stop

Anyone who can see the family member can use it; each opening is recorded
in the privacy record's access log.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..core.auth import get_current_user, assert_can_view
from ..models.database import get_db, RemovalRequest, RequestStatus, User
from .captcha import LiveInput

router = APIRouter(prefix="/api/live-steps", tags=["live-steps"])
KIND = "step"


def _request(db, user, request_id: int, log_it: bool = False) -> RemovalRequest:
    r = db.query(RemovalRequest).filter(RemovalRequest.id == request_id).first()
    if r is None:
        raise HTTPException(404, "That opt-out is gone. Refresh the page.")
    member = assert_can_view(db, user, r.member_id)
    if log_it:
        from ..core.privacy_record import log_access
        log_access(db, user, member, "view", "live opt-out page")
    return r


@router.post("/{request_id}")
def start(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    r = _request(db, user, request_id, log_it=True)
    if r.status != RequestStatus.needs_manual or not r.handoff_enc:
        raise HTTPException(400, "This opt-out can't be picked up here. Use the steps on the Checklist.")
    try:
        return MANAGER.start(request_id, user.id, kind=KIND)
    except RuntimeError as e:
        raise HTTPException(429, str(e))


@router.get("/{request_id}")
def status(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    _request(db, user, request_id)
    return MANAGER.status(request_id, kind=KIND) or {"ref_id": request_id, "state": "none", "active": False}


@router.get("/{request_id}/frame")
def frame(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    _request(db, user, request_id)
    img = MANAGER.frame(request_id, kind=KIND)
    if img is None:
        return Response(status_code=204)
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/{request_id}/input")
def send_input(request_id: int, ev: LiveInput, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    _request(db, user, request_id)
    if not MANAGER.send_input(request_id, ev.model_dump(), kind=KIND):
        raise HTTPException(409, "The page isn't waiting for you right now.")
    return {"ok": True}


@router.post("/{request_id}/done")
def done(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    _request(db, user, request_id)
    if not MANAGER.solved(request_id, kind=KIND):
        raise HTTPException(409, "The page isn't waiting for you right now.")
    return {"ok": True}


@router.delete("/{request_id}")
def stop(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    _request(db, user, request_id)
    return {"stopped": MANAGER.cancel(request_id, kind=KIND)}
