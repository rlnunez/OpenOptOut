"""
CAPTCHA challenges API — human-in-the-loop queue and resolution seam (Item 4).

When an automated opt-out encounters a challenge that cannot be solved
automatically by a solver plugin, execution pauses and logs a challenge here.
Operators and family managers can review challenges, inspect screenshots,
complete the challenge manually on the broker's site, or submit solution tokens.
"""

import os
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import (
    get_db, CaptchaChallenge, RemovalRequest, RequestStatus,
    Broker, FamilyMember, User, AutomationLog
)
from ..core.auth import (
    get_current_user, get_accessible_member_ids, assert_can_view
)
from ..core.broker_health import record_success

router = APIRouter(prefix="/api/captcha", tags=["captcha"])

SCREENSHOTS_DIR = "/data/screenshots"


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChallengeOut(BaseModel):
    id: int
    request_id: int
    broker_id: int
    broker_name: str
    broker_opt_out_url: Optional[str] = None
    member_id: int
    member_name: str
    challenge_type: str
    site_key: Optional[str] = None
    page_url: Optional[str] = None
    has_screenshot: bool = False
    screenshot_file: Optional[str] = None
    status: str
    token: Optional[str] = None
    notes: Optional[str] = None
    resolved_by_name: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ResolveChallengeIn(BaseModel):
    resolution_type: str = "manual_completed"   # 'manual_completed' | 'token'
    token: Optional[str] = None
    notes: Optional[str] = None


class DismissChallengeIn(BaseModel):
    notes: Optional[str] = None


class CaptchaStatsOut(BaseModel):
    pending: int
    resolved: int
    dismissed: int
    total: int


def _challenge_to_out(c: CaptchaChallenge) -> ChallengeOut:
    has_shot = bool(c.screenshot and os.path.exists(c.screenshot))
    shot_filename = os.path.basename(c.screenshot) if c.screenshot else None
    return ChallengeOut(
        id=c.id,
        request_id=c.request_id,
        broker_id=c.broker_id,
        broker_name=c.broker.name if c.broker else f"Broker #{c.broker_id}",
        broker_opt_out_url=c.broker.opt_out_url if c.broker else None,
        member_id=c.member_id,
        member_name=c.member.full_name if c.member else f"Member #{c.member_id}",
        challenge_type=c.challenge_type or "other",
        site_key=c.site_key,
        page_url=c.page_url,
        has_screenshot=has_shot,
        screenshot_file=shot_filename,
        status=c.status or "pending",
        token=c.token,
        notes=c.notes,
        resolved_by_name=c.resolver.full_name or c.resolver.email if c.resolver else None,
        resolved_at=c.resolved_at,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/challenges", response_model=List[ChallengeOut])
def list_challenges(
    status: Optional[str] = Query("pending"),
    member_id: Optional[int] = Query(None),
    broker_id: Optional[int] = Query(None),
    skip: int = Query(0),
    limit: int = Query(100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List CAPTCHA challenges filtered by visibility scope and status."""
    accessible = get_accessible_member_ids(db, current_user)
    q = db.query(CaptchaChallenge).filter(CaptchaChallenge.member_id.in_(accessible))
    if status and status != "all":
        q = q.filter(CaptchaChallenge.status == status)
    if member_id:
        if member_id not in accessible:
            raise HTTPException(403, "No access to this member")
        q = q.filter(CaptchaChallenge.member_id == member_id)
    if broker_id:
        q = q.filter(CaptchaChallenge.broker_id == broker_id)

    challenges = q.order_by(CaptchaChallenge.created_at.desc()).offset(skip).limit(limit).all()
    return [_challenge_to_out(c) for c in challenges]


@router.get("/stats", response_model=CaptchaStatsOut)
def get_captcha_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Counts of pending, resolved, and dismissed CAPTCHA challenges."""
    accessible = get_accessible_member_ids(db, current_user)
    base_q = db.query(CaptchaChallenge).filter(CaptchaChallenge.member_id.in_(accessible))
    pending = base_q.filter(CaptchaChallenge.status == "pending").count()
    resolved = base_q.filter(CaptchaChallenge.status == "resolved").count()
    dismissed = base_q.filter(CaptchaChallenge.status == "dismissed").count()
    return CaptchaStatsOut(
        pending=pending,
        resolved=resolved,
        dismissed=dismissed,
        total=pending + resolved + dismissed,
    )


@router.get("/challenges/{challenge_id}", response_model=ChallengeOut)
def get_challenge(
    challenge_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch details of a single CAPTCHA challenge."""
    c = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "Challenge not found")
    assert_can_view(db, current_user, c.member_id)
    return _challenge_to_out(c)


@router.get("/challenges/{challenge_id}/screenshot")
def get_challenge_screenshot(
    challenge_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream challenge screenshot image."""
    c = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "Challenge not found")
    assert_can_view(db, current_user, c.member_id)

    if not c.screenshot or not os.path.isfile(c.screenshot):
        raise HTTPException(404, "Screenshot not available")

    # Defense against directory traversal
    real_path = os.path.realpath(c.screenshot)
    if not (real_path.startswith(os.path.realpath(SCREENSHOTS_DIR)) or real_path.startswith("/data/")):
        raise HTTPException(403, "Access to screenshot path forbidden")

    with open(real_path, "rb") as f:
        img_bytes = f.read()

    return Response(content=img_bytes, media_type="image/png")


@router.post("/challenges/{challenge_id}/resolve", response_model=ChallengeOut)
def resolve_challenge(
    challenge_id: int,
    data: ResolveChallengeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Resolve a CAPTCHA challenge via human verification or token injection.
    Transitions the challenge to resolved, marks the associated RemovalRequest as sent,
    heals the broker health status, and logs the manual resolution audit event.
    """
    c = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "Challenge not found")
    assert_can_view(db, current_user, c.member_id)

    c.status = "resolved"
    c.resolved_by = current_user.id
    c.resolved_at = datetime.utcnow()
    if data.token:
        c.token = data.token
    if data.notes:
        c.notes = data.notes

    # Update associated removal request
    req = db.query(RemovalRequest).filter(RemovalRequest.id == c.request_id).first()
    if req:
        req.status = RequestStatus.sent
        req.sent_at = datetime.utcnow()
        req.updated_at = datetime.utcnow()
        req.notes = f"Resolved via human verification: {data.notes or 'Completed by operator'}"

        # Audit log
        db.add(AutomationLog(
            request_id=req.id,
            member_id=req.member_id,
            broker_id=req.broker_id,
            action="human_captcha_resolved",
            status="success",
            detail=f"Human-in-the-loop resolution ({data.resolution_type}) by {current_user.full_name or current_user.email}",
            duration_ms=0,
        ))

    # Reset broker health counter so a challenge wall doesn't stay marked as broken
    try:
        record_success(db, c.broker_id)
    except Exception:
        pass

    db.commit()
    db.refresh(c)

    # Fire notification hook
    try:
        from ..plugins.hooks import fire_event
        fire_event("captcha_challenge_resolved", entity_id=str(c.id), data={
            "broker": c.broker.name if c.broker else "",
            "member": c.member.full_name if c.member else "",
            "resolution": data.resolution_type,
            "resolved_by": current_user.full_name or current_user.email,
        })
    except Exception:
        pass

    return _challenge_to_out(c)


@router.post("/challenges/{challenge_id}/dismiss", response_model=ChallengeOut)
def dismiss_challenge(
    challenge_id: int,
    data: DismissChallengeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dismiss a challenge without completing removal."""
    c = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "Challenge not found")
    assert_can_view(db, current_user, c.member_id)

    c.status = "dismissed"
    c.resolved_by = current_user.id
    c.resolved_at = datetime.utcnow()
    if data.notes:
        c.notes = data.notes

    req = db.query(RemovalRequest).filter(RemovalRequest.id == c.request_id).first()
    if req:
        req.notes = f"CAPTCHA challenge dismissed: {data.notes or 'Skipped by operator'}"
        req.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(c)
    return _challenge_to_out(c)


@router.post("/challenges/{challenge_id}/retry")
def retry_challenge(
    challenge_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reset the removal request to pending to attempt automated execution again."""
    c = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "Challenge not found")
    assert_can_view(db, current_user, c.member_id)

    c.status = "dismissed"
    c.notes = "Re-queued for automated retry"

    req = db.query(RemovalRequest).filter(RemovalRequest.id == c.request_id).first()
    if req:
        req.status = RequestStatus.pending
        req.sent_at = None
        req.notes = "Re-queued after CAPTCHA challenge"
        req.updated_at = datetime.utcnow()

    db.commit()
    return {"retried": True, "request_id": c.request_id}
