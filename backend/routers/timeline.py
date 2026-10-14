"""
Removal timelines.
  GET /api/timeline/request/{request_id}  one person × one site
  GET /api/timeline/broker/{broker_id}    every person you can see, for one site
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models.database import get_db, RemovalRequest, Broker, User
from ..core.auth import get_current_user, get_accessible_member_ids
from ..core import timeline as tl

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


@router.get("/request/{request_id}")
def request_timeline(request_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    req = db.query(RemovalRequest).filter(RemovalRequest.id == request_id).first()
    if req is None:
        raise HTTPException(404, "That request is gone. Refresh the page.")
    if req.member_id not in set(get_accessible_member_ids(db, current_user)):
        raise HTTPException(403, "You don't have access to this person.")
    return tl.build(db, req)


@router.get("/broker/{broker_id}")
def broker_timelines(broker_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    broker = db.query(Broker).filter(Broker.id == broker_id).first()
    if broker is None:
        raise HTTPException(404, "That site is gone. Refresh the page.")
    allowed = list(get_accessible_member_ids(db, current_user))
    reqs = (db.query(RemovalRequest)
            .filter(RemovalRequest.broker_id == broker_id, RemovalRequest.member_id.in_(allowed))
            .order_by(RemovalRequest.member_id).all())
    return {"broker": broker.name, "timelines": [tl.build(db, r) for r in reqs]}
