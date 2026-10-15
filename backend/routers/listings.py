"""
Find your listings: search links built from a member's identity vault, and
adding a listing URL someone found to the removal cycle. See
core/listing_finder.py.

  GET  /api/listings/plan/{member_id}   web searches + one search per known broker
  POST /api/listings/resolve            which broker a URL belongs to (no changes made)
  POST /api/listings/{member_id}        add a listing URL to the member's removal cycle
"""

import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.auth import get_current_user, assert_can_view, assert_can_edit
from ..core import listing_finder as lf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/listings", tags=["listings"])


class UrlIn(BaseModel):
    url: str


@router.get("/plan/{member_id}")
def plan(member_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    member = assert_can_view(db, user, member_id)
    return lf.search_plan(db, member)


@router.post("/resolve")
def resolve(body: UrlIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        url = lf.validate_listing_url(body.url)
    except ValueError as e:
        logger.warning("Resolve listing URL failed: %s", e)
        raise HTTPException(400, "Please provide a valid public website address.")
    hit = lf.resolve_broker(db, url)
    b = hit["broker"]
    return {"domain": hit["domain"], "match": hit["match"], "note": hit["note"],
            "broker_id": b.id if b else None, "broker_name": b.name if b else None}


def _check_new_site(broker_id: int):
    """Look at a new site's privacy pages in the background (no personal data is sent)."""
    from ..models.database import SessionLocal, Broker
    from ..core import privacy_finder as pf
    db = SessionLocal()
    try:
        b = db.query(Broker).filter(Broker.id == broker_id).first()
        if b is not None:
            pf.check_new_site(db, b)
    except Exception:
        pass
    finally:
        db.close()


@router.post("/{member_id}")
def add(member_id: int, body: UrlIn, background: BackgroundTasks, db: Session = Depends(get_db),
        user: User = Depends(get_current_user)):
    member = assert_can_edit(db, user, member_id)
    try:
        res = lf.add_listing(db, member, body.url)
    except ValueError as e:
        logger.warning("Add listing failed: %s", e)
        raise HTTPException(400, "Please provide a valid public website address.")
    if res.get("state") == "new_broker":
        background.add_task(_check_new_site, res["broker_id"])
    return res
