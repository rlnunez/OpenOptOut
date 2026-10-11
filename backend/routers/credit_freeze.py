"""
Credit freeze letters: GET /api/credit-freeze/{member_id}

Builds the letters on request and returns them; nothing is stored. Social
Security numbers are never asked for — the letters leave a blank to write in.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models.database import get_db, FamilyMember, User
from ..core.auth import get_current_user, get_accessible_member_ids
from ..core import credit_freeze as cf

router = APIRouter(prefix="/api/credit-freeze", tags=["credit-freeze"])


@router.get("/{member_id}")
def freeze_letters(
    member_id: int,
    requester_id: Optional[int] = None,
    kind: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed = set(get_accessible_member_ids(db, current_user))
    if member_id not in allowed:
        raise HTTPException(403, "You don't have access to this person.")
    if kind not in (None, "adult", "minor"):
        raise HTTPException(400, "Choose an adult or a child freeze.")
    member = db.query(FamilyMember).filter(FamilyMember.id == member_id).first()
    if member is None:
        raise HTTPException(404, "That person is gone. Refresh the page.")
    requester = None
    if requester_id is not None:
        if requester_id not in allowed:
            raise HTTPException(403, "You don't have access to that parent's details.")
        requester = db.query(FamilyMember).filter(FamilyMember.id == requester_id).first()
    return cf.letters(member, requester=requester, kind=kind)
