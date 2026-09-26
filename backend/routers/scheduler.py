"""
Scheduler API endpoints:
  GET  /api/scheduler/status       — next run times + last run results
  POST /api/scheduler/trigger/{job} — manually fire a job (super_admin only)
  GET  /api/scheduler/runs         — audit log of past runs
  GET/PATCH /api/scheduler/member/{member_id} — per-member config (parent can edit own family)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..models.database import (
    get_db, MemberScheduleConfig, SchedulerRun,
    FamilyMember, User
)
from ..core.auth import (
    get_current_user, require_super_admin,
    assert_can_edit, get_accessible_member_ids
)
from ..core.access import require_permission
from ..core.scheduler import (
    get_scheduler, get_next_run_times,
    daily_optout_job, email_monitor_job, recheck_job,
    reload_scheduler
)
from ..core.settings_store import load_settings

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class SchedulerStatus(BaseModel):
    enabled: bool
    running: bool
    next_runs: dict
    system_max_per_day: int
    pause_before_send: bool
    auto_recheck: bool
    recheck_interval_days: int
    run_time: str
    timezone: str


class RunOut(BaseModel):
    id: int
    run_type: str
    started_at: datetime
    finished_at: Optional[datetime]
    optouts_sent: int
    emails_matched: int
    rechecks_queued: int
    status: str
    errors: Optional[str]

    class Config:
        from_attributes = True


class MemberConfigOut(BaseModel):
    member_id: int
    member_name: str
    max_optouts_per_day: Optional[int]
    effective_limit: int          # resolved: member override or system default
    enabled: bool
    from_display_name: Optional[str]
    notes: Optional[str]


class MemberConfigUpdate(BaseModel):
    max_optouts_per_day: Optional[int] = None   # None = use system default
    enabled: Optional[bool] = None
    from_display_name: Optional[str] = None
    notes: Optional[str] = None


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status", response_model=SchedulerStatus)
def scheduler_status(_: User = Depends(require_permission("scheduler.manage"))):
    cfg   = load_settings()
    sched = cfg.get("scheduler", {})
    s     = get_scheduler()
    return SchedulerStatus(
        enabled=sched.get("enabled", False),
        running=s.running,
        next_runs=get_next_run_times(),
        system_max_per_day=sched.get("max_optouts_per_day", 20),
        pause_before_send=sched.get("pause_before_send", True),
        auto_recheck=sched.get("auto_recheck", True),
        recheck_interval_days=sched.get("recheck_interval_days", 90),
        run_time=sched.get("run_time", "02:00"),
        timezone=sched.get("timezone", "America/Chicago"),
    )


# ── Manual triggers ───────────────────────────────────────────────────────────

JOB_MAP = {
    "optout":       daily_optout_job,
    "email_monitor": email_monitor_job,
    "recheck":      recheck_job,
}

@router.post("/trigger/{job_name}")
def trigger_job(
    job_name: str,
    _: User = Depends(require_permission("scheduler.manage")),
):
    fn = JOB_MAP.get(job_name)
    if not fn:
        raise HTTPException(400, f"Unknown job. Valid: {list(JOB_MAP)}")
    import threading
    threading.Thread(target=fn, daemon=True).start()
    return {"triggered": job_name, "at": datetime.utcnow().isoformat()}


@router.post("/reload")
def reload(_: User = Depends(require_permission("scheduler.manage"))):
    """Re-read scheduler config and restart jobs."""
    reload_scheduler()
    return {"reloaded": True}


# ── Run history ───────────────────────────────────────────────────────────────

@router.get("/runs", response_model=List[RunOut])
def list_runs(
    limit: int = 50,
    run_type: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("scheduler.manage")),
):
    q = db.query(SchedulerRun)
    if run_type:
        q = q.filter(SchedulerRun.run_type == run_type)
    return q.order_by(SchedulerRun.started_at.desc()).limit(limit).all()


# ── Per-member config ─────────────────────────────────────────────────────────

@router.get("/members", response_model=List[MemberConfigOut])
def list_member_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Super admin sees all members.
    Parents see only their accessible members.
    """
    cfg        = load_settings()
    sys_max    = cfg.get("scheduler", {}).get("max_optouts_per_day", 20)
    accessible = get_accessible_member_ids(db, current_user)
    members    = db.query(FamilyMember).filter(FamilyMember.id.in_(accessible)).all()

    result = []
    for m in members:
        mc = m.schedule_config
        result.append(MemberConfigOut(
            member_id=m.id,
            member_name=m.full_name,
            max_optouts_per_day=mc.max_optouts_per_day if mc else None,
            effective_limit=mc.max_optouts_per_day if (mc and mc.max_optouts_per_day) else sys_max,
            enabled=mc.enabled if mc else True,
            from_display_name=mc.from_display_name if mc else None,
            notes=mc.notes if mc else None,
        ))
    return result


@router.patch("/members/{member_id}", response_model=MemberConfigOut)
def update_member_config(
    member_id: int,
    data: MemberConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Parents can update members they manage. Super admin can update anyone."""
    assert_can_edit(db, current_user, member_id)

    member = db.query(FamilyMember).filter(FamilyMember.id == member_id).first()
    mc     = member.schedule_config

    if not mc:
        mc = MemberScheduleConfig(
            member_id=member_id,
            updated_by_id=current_user.id,
        )
        db.add(mc)

    if data.max_optouts_per_day is not None:
        mc.max_optouts_per_day = data.max_optouts_per_day if data.max_optouts_per_day > 0 else None
    if data.enabled is not None:
        mc.enabled = data.enabled
    if data.from_display_name is not None:
        mc.from_display_name = data.from_display_name
    if data.notes is not None:
        mc.notes = data.notes

    mc.updated_by_id = current_user.id
    db.commit()
    db.refresh(mc)

    cfg     = load_settings()
    sys_max = cfg.get("scheduler", {}).get("max_optouts_per_day", 20)

    return MemberConfigOut(
        member_id=member.id,
        member_name=member.full_name,
        max_optouts_per_day=mc.max_optouts_per_day,
        effective_limit=mc.max_optouts_per_day if mc.max_optouts_per_day else sys_max,
        enabled=mc.enabled,
        from_display_name=mc.from_display_name,
        notes=mc.notes,
    )
