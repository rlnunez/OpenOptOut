"""
Email monitor API — status, recent email logs, manual poll trigger.
"""

import threading, asyncio
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..models.database import get_db, EmailLog, SchedulerRun, User
from ..core.auth import get_current_user, require_super_admin
from ..core.access import require_permission
from ..core.settings_store import load_settings

router = APIRouter(prefix="/api/email-monitor", tags=["email-monitor"])


class EmailLogOut(BaseModel):
    id: int
    request_id: Optional[int]
    direction: Optional[str]
    subject: Optional[str]
    body_snippet: Optional[str]
    matched_key: Optional[str]
    broker_name: Optional[str]
    member_name: Optional[str]
    received_at: datetime

    class Config:
        from_attributes = True


class MonitorStatus(BaseModel):
    configured: bool
    imap_host: Optional[str]
    imap_user: Optional[str]
    poll_interval_minutes: int
    last_poll: Optional[datetime]
    last_poll_status: Optional[str]
    total_matched: int
    total_unmatched: int


@router.get("/status", response_model=MonitorStatus)
def monitor_status(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = load_settings(); ec = cfg.get("email", {})
    last_run = (
        db.query(SchedulerRun)
        .filter(SchedulerRun.run_type == "email_poll")
        .order_by(SchedulerRun.started_at.desc())
        .first()
    )
    total_matched   = db.query(EmailLog).filter(EmailLog.matched_key.isnot(None), EmailLog.direction == "received").count()
    total_unmatched = db.query(EmailLog).filter(EmailLog.matched_key.is_(None),   EmailLog.direction == "received").count()

    return MonitorStatus(
        configured=bool(ec.get("imap_host") and ec.get("imap_password_enc")),
        imap_host=ec.get("imap_host"),
        imap_user=ec.get("imap_user"),
        poll_interval_minutes=ec.get("poll_interval_minutes", 15),
        last_poll=last_run.started_at if last_run else None,
        last_poll_status=last_run.status if last_run else None,
        total_matched=total_matched,
        total_unmatched=total_unmatched,
    )


@router.get("/logs", response_model=List[EmailLogOut])
def list_email_logs(
    direction: Optional[str] = Query(None),
    matched: Optional[bool]  = Query(None),
    limit: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(EmailLog)
    if direction: q = q.filter(EmailLog.direction == direction)
    if matched is True:  q = q.filter(EmailLog.matched_key.isnot(None))
    if matched is False: q = q.filter(EmailLog.matched_key.is_(None))
    logs = q.order_by(EmailLog.received_at.desc()).limit(limit).all()
    return [EmailLogOut(
        id=l.id, request_id=l.request_id,
        direction=l.direction, subject=l.subject,
        body_snippet=l.body_snippet, matched_key=l.matched_key,
        broker_name=l.request.broker.name if l.request and l.request.broker else None,
        member_name=l.request.member.full_name if l.request and l.request.member else None,
        received_at=l.received_at,
    ) for l in logs]


@router.post("/poll")
def manual_poll(_: User = Depends(require_permission("scheduler.manage"))):
    """Manually trigger an immediate IMAP poll."""
    from ..core.scheduler import email_monitor_job
    threading.Thread(target=email_monitor_job, daemon=True).start()
    return {"triggered": True, "at": datetime.utcnow().isoformat()}


@router.get("/poll-history", response_model=List[dict])
def poll_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    runs = (
        db.query(SchedulerRun)
        .filter(SchedulerRun.run_type == "email_poll")
        .order_by(SchedulerRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [{
        "id": r.id, "started_at": r.started_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "emails_matched": r.emails_matched,
        "status": r.status,
        "errors": r.errors,
    } for r in runs]
