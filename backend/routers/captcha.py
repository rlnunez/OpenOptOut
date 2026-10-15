"""
CAPTCHA challenges API — human-in-the-loop queue and resolution seam (Item 4).

When an automated opt-out encounters a challenge that cannot be solved
automatically by a solver plugin, execution pauses and logs a challenge here.
Operators and family managers can review challenges, inspect screenshots,
complete the challenge manually on the broker's site, or submit solution tokens.
"""

import logging
import os
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from ..models.database import (
    get_db, CaptchaChallenge, RemovalRequest, RequestStatus,
    Broker, FamilyMember, User, AutomationLog
)
from ..core.auth import (
    get_current_user, get_accessible_member_ids, assert_can_view, require_super_admin
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
            raise HTTPException(403, "You don't have access to this person.")
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
        raise HTTPException(404, "That CAPTCHA is gone. Refresh the page.")
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
        raise HTTPException(404, "That CAPTCHA is gone. Refresh the page.")
    assert_can_view(db, current_user, c.member_id)

    if not c.screenshot or not os.path.isfile(c.screenshot):
        raise HTTPException(404, "There's no picture of this page.")

    # Defense against directory traversal
    real_path = os.path.realpath(c.screenshot)
    if not (real_path.startswith(os.path.realpath(SCREENSHOTS_DIR)) or real_path.startswith("/data/")):
        raise HTTPException(403, "That picture can't be shown.")

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
        raise HTTPException(404, "That CAPTCHA is gone. Refresh the page.")
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
        raise HTTPException(404, "That CAPTCHA is gone. Refresh the page.")
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
        raise HTTPException(404, "That CAPTCHA is gone. Refresh the page.")
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


# ── Live hand-off: solve it in the real page (core/live_captcha.py) ───────────

class LiveInput(BaseModel):
    type: str                      # click | text | key | scroll
    x: Optional[float] = None
    y: Optional[float] = None
    text: Optional[str] = None
    key: Optional[str] = None
    dy: Optional[float] = None


def _live_challenge(db, current_user, challenge_id: int) -> CaptchaChallenge:
    c = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "That CAPTCHA is gone. Refresh the page.")
    member = assert_can_view(db, current_user, c.member_id)
    from ..core.privacy_record import log_access
    log_access(db, current_user, member, "view", "live CAPTCHA page")
    return c


@router.post("/challenges/{challenge_id}/live")
def live_start(challenge_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    c = _live_challenge(db, current_user, challenge_id)
    if c.status != "pending":
        raise HTTPException(400, "This one is already finished.")
    try:
        return MANAGER.start(challenge_id, current_user.id)
    except RuntimeError as e:
        logger.warning("Live captcha session start failed: %s", e)
        raise HTTPException(429, "Too many live sessions are open right now. Try again in a few minutes.")


@router.get("/challenges/{challenge_id}/live")
def live_status(challenge_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    c = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "That CAPTCHA is gone. Refresh the page.")
    assert_can_view(db, current_user, c.member_id)
    return MANAGER.status(challenge_id) or {"challenge_id": challenge_id, "state": "none", "active": False}


@router.get("/challenges/{challenge_id}/live/frame")
def live_frame(challenge_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    c = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "That CAPTCHA is gone. Refresh the page.")
    assert_can_view(db, current_user, c.member_id)
    img = MANAGER.frame(challenge_id)
    if img is None:
        return Response(status_code=204)
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/challenges/{challenge_id}/live/input")
def live_input(challenge_id: int, ev: LiveInput, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    c = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "That CAPTCHA is gone. Refresh the page.")
    assert_can_view(db, current_user, c.member_id)
    if not MANAGER.send_input(challenge_id, ev.model_dump()):
        raise HTTPException(409, "The page isn't waiting for you right now.")
    return {"ok": True}


@router.post("/challenges/{challenge_id}/live/solved")
def live_solved(challenge_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    _live_challenge(db, current_user, challenge_id)
    if not MANAGER.solved(challenge_id):
        raise HTTPException(409, "The page isn't waiting for you right now.")
    return {"ok": True}


@router.delete("/challenges/{challenge_id}/live")
def live_cancel(challenge_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..core.live_captcha import MANAGER
    c = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "That CAPTCHA is gone. Refresh the page.")
    assert_can_view(db, current_user, c.member_id)
    return {"stopped": MANAGER.cancel(challenge_id)}


# ── Automatic solving settings (super admin) ──────────────────────────────────

class SolvingIn(BaseModel):
    service: str
    api_key: Optional[str] = None      # omit to keep the saved key; "" to clear it


@router.get("/solving")
def solving_settings(db: Session = Depends(get_db), _=Depends(require_super_admin)):
    from ..core import captcha_services as cs
    from ..core.settings_store import load_settings
    from ..models.database import InstalledPlugin
    row = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == cs.SERVICE_PLUGIN).first()
    return {**cs.public(load_settings()), "plugin_id": cs.SERVICE_PLUGIN,
            "plugin_installed": row is not None, "plugin_enabled": bool(row and row.enabled)}


@router.patch("/solving")
def save_solving(data: SolvingIn, _=Depends(require_super_admin)):
    from ..core import captcha_services as cs
    try:
        return cs.save_service(cs.SERVICE_PLUGIN, data.service, data.api_key)
    except ValueError as e:
        logger.warning("Captcha save service failed: %s", e)
        safe_msg = "Choose one of the listed services." if str(e) == "Choose one of the listed services." else "Invalid captcha service selection."
        raise HTTPException(400, safe_msg)


@router.post("/solving/install")
def install_solving_plugin(db: Session = Depends(get_db), current: User = Depends(require_super_admin)):
    """Copy the built-in solving plugin into the plugins folder and register it
    (off). An admin then turns it on and approves its permissions on the Plugins page."""
    import json as _json
    from ..core import captcha_services as cs
    from ..models.database import InstalledPlugin
    from ..plugins import layout
    from ..plugins.permissions import PluginManifest
    from .plugins import _register, _code_inspection, _audit
    row = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == cs.SERVICE_PLUGIN).first()
    if row is not None:
        return {"installed": True, "enabled": bool(row.enabled)}
    src = layout.bundled_plugins().get(cs.SERVICE_PLUGIN)
    if not src:
        raise HTTPException(404, "The built-in solving plugin is missing from this install.")
    with open(os.path.join(src, "manifest.json"), encoding="utf-8") as f:
        manifest = PluginManifest.from_dict(_json.load(f))
    if manifest.validate():
        raise HTTPException(500, "The built-in solving plugin is damaged.")
    dest = layout.sync_bundled(src, layout.plugins_root(), manifest)
    code = _code_inspection(manifest, dest)
    if code.get("blocked"):
        raise HTTPException(400, "The solving plugin didn't pass the code check: " + "; ".join(code.get("high", [])))
    _register(db, manifest, dest)
    _audit(db, manifest.id, "installed", current.id, "built-in CAPTCHA solving service")
    return {"installed": True, "enabled": False}
