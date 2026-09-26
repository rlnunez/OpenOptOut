from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import uuid

from ..models.database import (
    get_db, RemovalRequest, Broker, FamilyMember,
    RequestStatus, OptOutMethod
)
from ..core.auth import (
    get_current_user, get_accessible_member_ids,
    assert_can_view, User
)

router = APIRouter(prefix="/api/requests", tags=["requests"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RequestOut(BaseModel):
    id: int
    member_id: int
    broker_id: int
    broker_name: str
    broker_opt_out_url: Optional[str]
    broker_difficulty: Optional[str]
    member_name: str
    request_key: str
    status: str
    method_used: Optional[str]
    sent_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    recheck_after: Optional[datetime]
    days_until_recheck: Optional[int]
    listing_url: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CreateRequest(BaseModel):
    member_id: int
    broker_id: int
    method_used: Optional[str] = "form"
    listing_url: Optional[str] = None
    notes: Optional[str] = None


class UpdateRequest(BaseModel):
    status: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    listing_url: Optional[str] = None
    notes: Optional[str] = None
    recheck_days: Optional[int] = None


class SnoozeRequest(BaseModel):
    days: int = 30   # push recheck N days into the future


def _to_out(r: RemovalRequest) -> RequestOut:
    now = datetime.utcnow()
    days = None
    if r.recheck_after:
        days = (r.recheck_after - now).days
    return RequestOut(
        id=r.id,
        member_id=r.member_id,
        broker_id=r.broker_id,
        broker_name=r.broker.name if r.broker else "",
        broker_opt_out_url=r.broker.opt_out_url if r.broker else None,
        broker_difficulty=r.broker.difficulty if r.broker else None,
        member_name=r.member.full_name if r.member else "",
        request_key=r.request_key or "",
        status=r.status,
        method_used=r.method_used,
        sent_at=r.sent_at,
        confirmed_at=r.confirmed_at,
        recheck_after=r.recheck_after,
        days_until_recheck=days,
        listing_url=r.listing_url,
        notes=r.notes,
        created_at=r.created_at,
    )


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[RequestOut])
def list_requests(
    member_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accessible = get_accessible_member_ids(db, current_user)
    q = db.query(RemovalRequest).filter(RemovalRequest.member_id.in_(accessible))
    if member_id:
        if member_id not in accessible:
            raise HTTPException(403, "No access to this member")
        q = q.filter(RemovalRequest.member_id == member_id)
    if status:
        q = q.filter(RemovalRequest.status == status)
    reqs = q.order_by(RemovalRequest.updated_at.desc()).offset(skip).limit(limit).all()
    return [_to_out(r) for r in reqs]


# ── Recheck views ─────────────────────────────────────────────────────────────

@router.get("/recheck-due", response_model=List[RequestOut])
def recheck_due(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overdue: confirmed removals whose recheck_after has already passed."""
    accessible = get_accessible_member_ids(db, current_user)
    reqs = db.query(RemovalRequest).filter(
        RemovalRequest.member_id.in_(accessible),
        RemovalRequest.recheck_after <= datetime.utcnow(),
        RemovalRequest.status == RequestStatus.confirmed,
    ).order_by(RemovalRequest.recheck_after).all()
    return [_to_out(r) for r in reqs]


@router.get("/recheck-upcoming", response_model=List[RequestOut])
def recheck_upcoming(
    days_ahead: int = Query(30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upcoming: confirmed removals whose recheck_after is within the next N days."""
    accessible = get_accessible_member_ids(db, current_user)
    cutoff = datetime.utcnow() + timedelta(days=days_ahead)
    reqs = db.query(RemovalRequest).filter(
        RemovalRequest.member_id.in_(accessible),
        RemovalRequest.recheck_after > datetime.utcnow(),
        RemovalRequest.recheck_after <= cutoff,
        RemovalRequest.status == RequestStatus.confirmed,
    ).order_by(RemovalRequest.recheck_after).all()
    return [_to_out(r) for r in reqs]


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=RequestOut, status_code=201)
def create_request(
    data: CreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accessible = get_accessible_member_ids(db, current_user)
    if data.member_id not in accessible:
        raise HTTPException(403, "No access to this member")

    broker = db.query(Broker).filter(Broker.id == data.broker_id).first()
    member = db.query(FamilyMember).filter(FamilyMember.id == data.member_id).first()
    if not broker: raise HTTPException(404, "Broker not found")
    if not member: raise HTTPException(404, "Member not found")

    req = RemovalRequest(
        member_id=data.member_id,
        broker_id=data.broker_id,
        request_key=str(uuid.uuid4()),
        method_used=data.method_used,
        listing_url=data.listing_url,
        notes=data.notes,
        status=RequestStatus.pending,
        recheck_after=datetime.utcnow() + timedelta(days=90),
    )
    db.add(req); db.commit(); db.refresh(req)
    return _to_out(req)


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{req_id}", response_model=RequestOut)
def update_request(
    req_id: int,
    data: UpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(RemovalRequest).filter(RemovalRequest.id == req_id).first()
    if not req: raise HTTPException(404, "Request not found")
    assert_can_view(db, current_user, req.member_id)

    if data.status:
        req.status = data.status
        if data.status == RequestStatus.confirmed and not req.confirmed_at:
            req.confirmed_at = datetime.utcnow()
    if data.confirmed_at: req.confirmed_at = data.confirmed_at
    if data.listing_url:  req.listing_url  = data.listing_url
    if data.notes:        req.notes        = data.notes
    if data.recheck_days: req.recheck_after = datetime.utcnow() + timedelta(days=data.recheck_days)

    req.updated_at = datetime.utcnow()
    db.commit(); db.refresh(req)
    return _to_out(req)


# ── Requeue (re-submit an overdue removal) ────────────────────────────────────

@router.post("/{req_id}/requeue", response_model=RequestOut)
def requeue_request(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reset a confirmed (or overdue) request back to pending so it gets re-sent."""
    req = db.query(RemovalRequest).filter(RemovalRequest.id == req_id).first()
    if not req: raise HTTPException(404, "Request not found")
    assert_can_view(db, current_user, req.member_id)

    req.status       = RequestStatus.pending
    req.sent_at      = None
    req.confirmed_at = None
    req.updated_at   = datetime.utcnow()
    db.commit(); db.refresh(req)
    return _to_out(req)


# ── Snooze (push recheck date forward) ───────────────────────────────────────

@router.post("/{req_id}/snooze", response_model=RequestOut)
def snooze_request(
    req_id: int,
    body: SnoozeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Push the recheck_after date forward by N days without changing status."""
    req = db.query(RemovalRequest).filter(RemovalRequest.id == req_id).first()
    if not req: raise HTTPException(404, "Request not found")
    assert_can_view(db, current_user, req.member_id)

    base = max(req.recheck_after or datetime.utcnow(), datetime.utcnow())
    req.recheck_after = base + timedelta(days=body.days)
    req.updated_at    = datetime.utcnow()
    db.commit(); db.refresh(req)
    return _to_out(req)
