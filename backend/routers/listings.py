"""
Find your listings: search links built from a member's identity vault, and
adding a listing URL someone found to the removal cycle. See
core/listing_finder.py.

  GET  /api/listings/plan/{member_id}   web searches + one search per known broker
  POST /api/listings/resolve            which broker a URL belongs to (no changes made)
  POST /api/listings/{member_id}        add a listing URL to the member's removal cycle
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.auth import get_current_user, assert_can_view, assert_can_edit
from ..core import listing_finder as lf

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
        raise HTTPException(400, str(e))
    hit = lf.resolve_broker(db, url)
    b = hit["broker"]
    return {"domain": hit["domain"], "match": hit["match"], "note": hit["note"],
            "broker_id": b.id if b else None, "broker_name": b.name if b else None}


@router.post("/{member_id}")
def add(member_id: int, body: UrlIn, db: Session = Depends(get_db),
        user: User = Depends(get_current_user)):
    member = assert_can_edit(db, user, member_id)
    try:
        return lf.add_listing(db, member, body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
