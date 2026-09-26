"""
Usage reporting for institutional deployments.
Super admin only. Provides enrollment trends, opt-out metrics, broker compliance.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, extract, case
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from ..models.database import (
    get_db, User, FamilyMember, RemovalRequest,
    RequestStatus, Broker, UsageEvent, SchedulerRun
)
from ..core.auth import require_super_admin

router = APIRouter(prefix="/api/reporting", tags=["reporting"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(require_super_admin)):
    """Top-level KPIs for the admin dashboard."""
    total_users   = db.query(User).count()
    total_members = db.query(FamilyMember).count()
    total_brokers = db.query(Broker).count()

    total_sent      = db.query(RemovalRequest).filter(RemovalRequest.status.in_([RequestStatus.sent, RequestStatus.confirmed])).count()
    total_confirmed = db.query(RemovalRequest).filter(RemovalRequest.status == RequestStatus.confirmed).count()
    total_failed    = db.query(RemovalRequest).filter(RemovalRequest.status == RequestStatus.failed).count()
    total_pending   = db.query(RemovalRequest).filter(RemovalRequest.status == RequestStatus.pending).count()

    success_rate = round((total_confirmed / total_sent * 100) if total_sent else 0, 1)

    # This month
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_sent  = db.query(RemovalRequest).filter(
        RemovalRequest.sent_at >= month_start,
    ).count()
    month_users = db.query(User).filter(User.created_at >= month_start).count()

    return {
        "total_users":      total_users,
        "total_members":    total_members,
        "total_brokers":    total_brokers,
        "total_sent":       total_sent,
        "total_confirmed":  total_confirmed,
        "total_failed":     total_failed,
        "total_pending":    total_pending,
        "success_rate":     success_rate,
        "month_sent":       month_sent,
        "month_new_users":  month_users,
    }


@router.get("/enrollments-over-time")
def enrollments_over_time(
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    """Monthly user enrollment counts for the past N months."""
    since = datetime.utcnow() - timedelta(days=months * 31)
    rows  = (
        db.query(
            func.strftime("%Y-%m", User.created_at).label("month"),
            func.count(User.id).label("count"),
        )
        .filter(User.created_at >= since)
        .group_by("month")
        .order_by("month")
        .all()
    )
    return [{"month": r.month, "enrollments": r.count} for r in rows]


@router.get("/optouts-over-time")
def optouts_over_time(
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    """Monthly opt-out sent + confirmed counts."""
    since = datetime.utcnow() - timedelta(days=months * 31)
    rows  = (
        db.query(
            func.strftime("%Y-%m", RemovalRequest.sent_at).label("month"),
            func.count(RemovalRequest.id).label("sent"),
            func.sum(
                case((RemovalRequest.status == RequestStatus.confirmed, 1), else_=0)
            ).label("confirmed"),
        )
        .filter(RemovalRequest.sent_at >= since)
        .group_by("month")
        .order_by("month")
        .all()
    )
    return [{"month": r.month, "sent": r.sent, "confirmed": int(r.confirmed or 0)} for r in rows]


@router.get("/broker-compliance")
def broker_compliance(
    limit: int = Query(20, ge=5, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    """Per-broker compliance rates — most and least compliant."""
    rows = (
        db.query(
            Broker.name,
            Broker.difficulty,
            Broker.is_property_broker,
            func.count(RemovalRequest.id).label("total"),
            func.sum(
                case((RemovalRequest.status == RequestStatus.confirmed, 1), else_=0)
            ).label("confirmed"),
            func.sum(
                case((RemovalRequest.status == RequestStatus.failed, 1), else_=0)
            ).label("failed"),
        )
        .join(RemovalRequest, RemovalRequest.broker_id == Broker.id, isouter=True)
        .group_by(Broker.id)
        .having(func.count(RemovalRequest.id) > 0)
        .order_by(func.count(RemovalRequest.id).desc())
        .limit(limit)
        .all()
    )
    return [{
        "broker":       r.name,
        "difficulty":   r.difficulty,
        "is_property":  r.is_property_broker,
        "total":        r.total,
        "confirmed":    int(r.confirmed or 0),
        "failed":       int(r.failed or 0),
        "rate":         round((r.confirmed / r.total * 100) if r.total else 0, 1),
    } for r in rows]


@router.get("/per-member")
def per_member_stats(
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    """Per-member summary — useful for institutional reporting."""
    rows = (
        db.query(
            FamilyMember.full_name,
            func.count(RemovalRequest.id).label("total"),
            func.sum(case((RemovalRequest.status == RequestStatus.confirmed, 1), else_=0)).label("confirmed"),
            func.sum(case((RemovalRequest.status == RequestStatus.pending,   1), else_=0)).label("pending"),
            func.sum(case((RemovalRequest.status == RequestStatus.failed,    1), else_=0)).label("failed"),
        )
        .join(RemovalRequest, RemovalRequest.member_id == FamilyMember.id, isouter=True)
        .group_by(FamilyMember.id)
        .order_by(func.count(RemovalRequest.id).desc())
        .all()
    )
    return [{
        "member":    r.full_name,
        "total":     r.total or 0,
        "confirmed": int(r.confirmed or 0),
        "pending":   int(r.pending   or 0),
        "failed":    int(r.failed    or 0),
        "rate":      round((r.confirmed / r.total * 100) if r.total else 0, 1),
    } for r in rows]


@router.get("/scheduler-health")
def scheduler_health(
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    """Last 30 days of scheduler run health."""
    since = datetime.utcnow() - timedelta(days=30)
    runs  = db.query(SchedulerRun).filter(SchedulerRun.started_at >= since).all()
    by_type: dict = {}
    for r in runs:
        t = r.run_type
        if t not in by_type:
            by_type[t] = {"total": 0, "ok": 0, "error": 0, "last_run": None}
        by_type[t]["total"] += 1
        if r.status == "done":
            by_type[t]["ok"] += 1
        elif r.status == "error":
            by_type[t]["error"] += 1
        if not by_type[t]["last_run"] or r.started_at > datetime.fromisoformat(by_type[t]["last_run"]):
            by_type[t]["last_run"] = r.started_at.isoformat()
    return by_type
