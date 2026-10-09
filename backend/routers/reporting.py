"""
Usage reporting for institutional deployments.
Needs "reporting.view". Provides enrollment trends, opt-out metrics, broker compliance.

Reports cover only a scoped manager's branches, name only the members the
viewer can already see, and return only the fields the Reporting page shows.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, extract, case, select
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from ..models.database import (
    get_db, User, FamilyMember, RemovalRequest,
    RequestStatus, Broker, UsageEvent, SchedulerRun
)
from ..core.auth import require_super_admin, manager_scope, get_accessible_member_ids
from ..core.access import require_permission, has_permission

router = APIRouter(prefix="/api/reporting", tags=["reporting"])


def _scoped_users(db: Session, user: User):
    """A select of the user ids the reports cover, or None for everyone. Scoped
    managers only get counts for accounts in their branches."""
    scope = manager_scope(db, user)
    if scope is None:
        return None
    return select(User.id).where(User.branch_id.in_(scope[1]))


def _scoped_requests(q, users):
    """Restrict a RemovalRequest query to the members of the covered users."""
    if users is None:
        return q
    return q.filter(RemovalRequest.member_id.in_(
        select(FamilyMember.id).where(FamilyMember.user_id.in_(users))))


def _nameable_member_ids(db: Session, user: User):
    """None when the user may see every member's name, else the member ids
    they can already open (own, shared, and scoped 'view all members' data')."""
    if user.is_super_admin or has_permission(user, "consortium.cross_system"):
        return None
    if has_permission(user, "members.view_all") and manager_scope(db, user) is None:
        return None
    return get_accessible_member_ids(db, user)


@router.get("/summary")
def summary(db: Session = Depends(get_db), current_user=Depends(require_permission("reporting.view"))):
    """Top-level KPIs for the admin dashboard."""
    users = _scoped_users(db, current_user)
    user_q = db.query(func.count(User.id))
    if users is not None:
        user_q = user_q.filter(User.id.in_(users))
    req_q = _scoped_requests(db.query(func.count(RemovalRequest.id)), users)

    total_users   = user_q.scalar()
    total_brokers = db.query(func.count(Broker.id)).scalar()

    total_sent      = req_q.filter(RemovalRequest.status.in_([RequestStatus.sent, RequestStatus.confirmed])).scalar()
    total_confirmed = req_q.filter(RemovalRequest.status == RequestStatus.confirmed).scalar()
    total_pending   = req_q.filter(RemovalRequest.status == RequestStatus.pending).scalar()

    success_rate = round((total_confirmed / total_sent * 100) if total_sent else 0, 1)

    # This month
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_sent  = req_q.filter(RemovalRequest.sent_at >= month_start).scalar()
    month_users = user_q.filter(User.created_at >= month_start).scalar()

    return {
        "total_users":      total_users,
        "total_brokers":    total_brokers,
        "total_sent":       total_sent,
        "total_confirmed":  total_confirmed,
        "total_pending":    total_pending,
        "success_rate":     success_rate,
        "month_sent":       month_sent,
        "month_new_users":  month_users,
    }


@router.get("/enrollments-over-time")
def enrollments_over_time(
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("reporting.view")),
):
    """Monthly user enrollment counts for the past N months."""
    since = datetime.utcnow() - timedelta(days=months * 31)
    q = db.query(
        func.strftime("%Y-%m", User.created_at).label("month"),
        func.count(User.id).label("count"),
    ).filter(User.created_at >= since)
    users = _scoped_users(db, current_user)
    if users is not None:
        q = q.filter(User.id.in_(users))
    rows  = (
        q
        .group_by("month")
        .order_by("month")
        .all()
    )
    return [{"month": r.month, "enrollments": r.count} for r in rows]


@router.get("/optouts-over-time")
def optouts_over_time(
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("reporting.view")),
):
    """Monthly opt-out sent + confirmed counts."""
    since = datetime.utcnow() - timedelta(days=months * 31)
    q = db.query(
        func.strftime("%Y-%m", RemovalRequest.sent_at).label("month"),
        func.count(RemovalRequest.id).label("sent"),
        func.sum(
            case((RemovalRequest.status == RequestStatus.confirmed, 1), else_=0)
        ).label("confirmed"),
    )
    rows  = (
        _scoped_requests(q, _scoped_users(db, current_user))
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
    current_user=Depends(require_permission("reporting.view")),
):
    """Per-broker compliance rates — most and least compliant."""
    q = db.query(
        Broker.name,
        func.count(RemovalRequest.id).label("total"),
        func.sum(
            case((RemovalRequest.status == RequestStatus.confirmed, 1), else_=0)
        ).label("confirmed"),
    ).join(RemovalRequest, RemovalRequest.broker_id == Broker.id)
    rows = (
        _scoped_requests(q, _scoped_users(db, current_user))
        .group_by(Broker.id)
        .having(func.count(RemovalRequest.id) > 0)
        .order_by(func.count(RemovalRequest.id).desc())
        .limit(limit)
        .all()
    )
    return [{
        "broker":       r.name,
        "total":        r.total,
        "confirmed":    int(r.confirmed or 0),
        "rate":         round((r.confirmed / r.total * 100) if r.total else 0, 1),
    } for r in rows]


@router.get("/per-member")
def per_member_stats(
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("reporting.view")),
):
    """Per-member summary — useful for institutional reporting. Names only the
    members the viewer can already open."""
    q = db.query(
        FamilyMember.full_name,
        func.count(RemovalRequest.id).label("total"),
        func.sum(case((RemovalRequest.status == RequestStatus.confirmed, 1), else_=0)).label("confirmed"),
        func.sum(case((RemovalRequest.status == RequestStatus.pending,   1), else_=0)).label("pending"),
        func.sum(case((RemovalRequest.status == RequestStatus.failed,    1), else_=0)).label("failed"),
    ).join(RemovalRequest, RemovalRequest.member_id == FamilyMember.id, isouter=True)
    visible = _nameable_member_ids(db, current_user)
    if visible is not None:
        q = q.filter(FamilyMember.id.in_(visible))
    rows = (
        q
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
    _=Depends(require_permission("reporting.view")),
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
