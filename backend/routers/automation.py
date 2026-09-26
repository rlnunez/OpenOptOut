"""
Automation API — discovery, opt-out triggers, broker scripts, automation logs.
"""

import asyncio, threading
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..models.database import (
    get_db, BrokerScript, DiscoveryResult, AutomationLog,
    RemovalRequest, RequestStatus, Broker, FamilyMember, User
)
from ..core.auth import (
    get_current_user, require_super_admin,
    get_accessible_member_ids, assert_can_view
)

router = APIRouter(prefix="/api/automation", tags=["automation"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class BrokerScriptOut(BaseModel):
    id: int
    broker_id: int
    broker_name: str
    search_url: Optional[str]
    name_selector: Optional[str]
    email_selector: Optional[str]
    address_selector: Optional[str]
    city_selector: Optional[str]
    state_selector: Optional[str]
    submit_selector: Optional[str]
    success_selector: Optional[str]
    success_text: Optional[str]
    requires_captcha: bool
    requires_email_confirm: bool
    extra_steps: Optional[str]
    email_subject_tpl: Optional[str]
    email_body_tpl: Optional[str]
    last_verified: Optional[datetime]
    verified_working: Optional[bool]
    notes: Optional[str]

    class Config:
        from_attributes = True


class BrokerScriptUpdate(BaseModel):
    search_url: Optional[str] = None
    name_selector: Optional[str] = None
    email_selector: Optional[str] = None
    address_selector: Optional[str] = None
    city_selector: Optional[str] = None
    state_selector: Optional[str] = None
    submit_selector: Optional[str] = None
    success_selector: Optional[str] = None
    success_text: Optional[str] = None
    requires_captcha: Optional[bool] = None
    requires_email_confirm: Optional[bool] = None
    extra_steps: Optional[str] = None
    email_subject_tpl: Optional[str] = None
    email_body_tpl: Optional[str] = None
    verified_working: Optional[bool] = None
    notes: Optional[str] = None


class DiscoveryResultOut(BaseModel):
    id: int
    member_id: int
    member_name: str
    broker_id: int
    broker_name: str
    found: bool
    listing_url: Optional[str]
    source: Optional[str]
    snippet: Optional[str]
    scanned_at: datetime
    scan_error: Optional[str]

    class Config:
        from_attributes = True


class AutomationLogOut(BaseModel):
    id: int
    request_id: Optional[int]
    member_id: Optional[int]
    broker_id: Optional[int]
    broker_name: Optional[str]
    member_name: Optional[str]
    action: Optional[str]
    status: Optional[str]
    detail: Optional[str]
    screenshot: Optional[str]
    duration_ms: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Discovery endpoints ───────────────────────────────────────────────────────

@router.post("/discover/{member_id}")
def trigger_discovery(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger a full discovery scan for a member (runs in background thread)."""
    assert_can_view(db, current_user, member_id)

    def run():
        from ..core.discovery import run_discovery_for_member
        asyncio.run(run_discovery_for_member(member_id))

    threading.Thread(target=run, daemon=True).start()
    return {"triggered": True, "member_id": member_id}


@router.get("/discover/{member_id}", response_model=List[DiscoveryResultOut])
def get_discovery_results(
    member_id: int,
    found_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get discovery scan results for a member."""
    assert_can_view(db, current_user, member_id)
    q = db.query(DiscoveryResult).filter(DiscoveryResult.member_id == member_id)
    if found_only:
        q = q.filter(DiscoveryResult.found == True)
    results = q.order_by(DiscoveryResult.scanned_at.desc()).all()
    return [DiscoveryResultOut(
        id=r.id, member_id=r.member_id,
        member_name=r.member.full_name if r.member else "",
        broker_id=r.broker_id,
        broker_name=r.broker.name if r.broker else "",
        found=r.found, listing_url=r.listing_url,
        source=r.source, snippet=r.snippet,
        scanned_at=r.scanned_at, scan_error=r.scan_error,
    ) for r in results]


# ── Opt-out trigger ───────────────────────────────────────────────────────────

@router.post("/optout/batch")
def trigger_optout_batch(
    request_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger opt-outs for a list of request IDs."""
    accessible = get_accessible_member_ids(db, current_user)
    # Verify all requests belong to accessible members
    for rid in request_ids:
        req = db.query(RemovalRequest).filter(RemovalRequest.id == rid).first()
        if not req or req.member_id not in accessible:
            raise HTTPException(403, f"No access to request {rid}")

    def run():
        from ..core.optout_engine import run_optout_batch
        asyncio.run(run_optout_batch(request_ids))

    threading.Thread(target=run, daemon=True).start()
    return {"triggered": len(request_ids), "request_ids": request_ids}


@router.post("/optout/{request_id}")
def trigger_single_optout(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger opt-out for a single request."""
    req = db.query(RemovalRequest).filter(RemovalRequest.id == request_id).first()
    if not req: raise HTTPException(404, "Request not found")
    assert_can_view(db, current_user, req.member_id)

    def run():
        from ..core.optout_engine import run_optout_batch
        asyncio.run(run_optout_batch([request_id]))

    threading.Thread(target=run, daemon=True).start()
    return {"triggered": True, "request_id": request_id}


# ── Broker scripts ────────────────────────────────────────────────────────────

@router.get("/scripts", response_model=List[BrokerScriptOut])
def list_scripts(
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    scripts = db.query(BrokerScript).all()
    return [_script_out(s) for s in scripts]


@router.get("/scripts/{broker_id}", response_model=BrokerScriptOut)
def get_script(
    broker_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    s = db.query(BrokerScript).filter(BrokerScript.broker_id == broker_id).first()
    if not s: raise HTTPException(404, "No script for this broker")
    return _script_out(s)


@router.put("/scripts/{broker_id}", response_model=BrokerScriptOut)
def upsert_script(
    broker_id: int,
    data: BrokerScriptUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    broker = db.query(Broker).filter(Broker.id == broker_id).first()
    if not broker: raise HTTPException(404, "Broker not found")

    s = db.query(BrokerScript).filter(BrokerScript.broker_id == broker_id).first()
    if not s:
        s = BrokerScript(broker_id=broker_id)
        db.add(s)

    for field, val in data.model_dump(exclude_none=True).items():
        setattr(s, field, val)
    s.updated_at = datetime.utcnow()
    db.commit(); db.refresh(s)
    return _script_out(s)


@router.delete("/scripts/{broker_id}", status_code=204)
def delete_script(
    broker_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    s = db.query(BrokerScript).filter(BrokerScript.broker_id == broker_id).first()
    if not s: raise HTTPException(404, "No script for this broker")
    db.delete(s); db.commit()


def _script_out(s: BrokerScript) -> BrokerScriptOut:
    return BrokerScriptOut(
        id=s.id, broker_id=s.broker_id,
        broker_name=s.broker.name if s.broker else "",
        search_url=s.search_url, name_selector=s.name_selector,
        email_selector=s.email_selector, address_selector=s.address_selector,
        city_selector=s.city_selector, state_selector=s.state_selector,
        submit_selector=s.submit_selector, success_selector=s.success_selector,
        success_text=s.success_text, requires_captcha=s.requires_captcha,
        requires_email_confirm=s.requires_email_confirm, extra_steps=s.extra_steps,
        email_subject_tpl=s.email_subject_tpl, email_body_tpl=s.email_body_tpl,
        last_verified=s.last_verified, verified_working=s.verified_working,
        notes=s.notes,
    )


# ── Automation logs ───────────────────────────────────────────────────────────

@router.get("/logs", response_model=List[AutomationLogOut])
def list_logs(
    member_id: Optional[int] = Query(None),
    broker_id: Optional[int] = Query(None),
    action: Optional[str]    = Query(None),
    status: Optional[str]    = Query(None),
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accessible = get_accessible_member_ids(db, current_user)
    q = db.query(AutomationLog).filter(
        AutomationLog.member_id.in_(accessible)
    )
    if member_id: q = q.filter(AutomationLog.member_id == member_id)
    if broker_id: q = q.filter(AutomationLog.broker_id == broker_id)
    if action:    q = q.filter(AutomationLog.action == action)
    if status:    q = q.filter(AutomationLog.status == status)
    logs = q.order_by(AutomationLog.created_at.desc()).limit(limit).all()
    return [AutomationLogOut(
        id=l.id, request_id=l.request_id,
        member_id=l.member_id, broker_id=l.broker_id,
        broker_name=l.broker.name if l.broker else None,
        member_name=l.member.full_name if l.member else None,
        action=l.action, status=l.status, detail=l.detail,
        screenshot=l.screenshot, duration_ms=l.duration_ms,
        created_at=l.created_at,
    ) for l in logs]
