from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import csv, io, json

from ..models.database import get_db, Broker, RemovalRequest, RequestStatus, BrokerStatus, OptOutMethod, Difficulty
from ..core.auth import get_current_user, User
from ..core.access import require_permission, has_permission

router = APIRouter(prefix="/api/brokers", tags=["brokers"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class BrokerOut(BaseModel):
    id: int
    name: str
    opt_out_url: Optional[str]
    method: Optional[str]
    difficulty: Optional[str]
    status: Optional[str]
    notes: Optional[str]
    date_added: Optional[datetime] = None
    request_count: int = 0
    latest_status: Optional[str] = None
    recheck_after: Optional[datetime] = None
    is_property_broker: bool = False
    enabled: bool = True
    priority: int = 3
    priority_source: str = "default"
    captcha_plugin_id: Optional[str] = None
    plugin_id: Optional[str] = None

    class Config:
        from_attributes = True


class BrokerUpdate(BaseModel):
    opt_out_url: Optional[str] = None
    method: Optional[str] = None
    difficulty: Optional[str] = None
    notes: Optional[str] = None
    is_property_broker: Optional[bool] = None
    captcha_plugin_id: Optional[str] = None


class BrokerCaptchaSolverUpdate(BaseModel):
    captcha_plugin_id: Optional[str] = None


class DashboardStats(BaseModel):
    total_brokers: int
    confirmed: int
    pending: int
    resistant: int
    recheck_due: int
    actioned: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    total = db.query(Broker).count()
    confirmed = db.query(RemovalRequest).filter(RemovalRequest.status == RequestStatus.confirmed).count()
    pending   = db.query(RemovalRequest).filter(RemovalRequest.status.in_([RequestStatus.sent, RequestStatus.pending])).count()
    resistant = db.query(Broker).filter(Broker.status == BrokerStatus.resistant).count()
    recheck   = db.query(RemovalRequest).filter(
        RemovalRequest.status == RequestStatus.recheck_due,
        RemovalRequest.recheck_after <= datetime.utcnow()
    ).count()
    actioned  = db.query(RemovalRequest.broker_id).distinct().count()

    return DashboardStats(
        total_brokers=total,
        confirmed=confirmed,
        pending=pending,
        resistant=resistant,
        recheck_due=recheck,
        actioned=actioned,
    )


@router.get("", response_model=List[BrokerOut])
def list_brokers(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Broker)
    if search:
        q = q.filter(Broker.name.ilike(f"%{search}%"))
    if status:
        q = q.filter(Broker.status == status)
    if method:
        q = q.filter(Broker.method == method)
    if difficulty:
        q = q.filter(Broker.difficulty == difficulty)

    brokers = q.order_by(Broker.name).offset(skip).limit(limit).all()

    result = []
    for b in brokers:
        latest_req = (
            db.query(RemovalRequest)
            .filter(RemovalRequest.broker_id == b.id)
            .order_by(RemovalRequest.updated_at.desc())
            .first()
        )
        result.append(BrokerOut(
            id=b.id,
            name=b.name,
            opt_out_url=b.opt_out_url,
            method=b.method,
            difficulty=b.difficulty,
            status=b.status,
            notes=b.notes,
            date_added=b.date_added,
            request_count=len(b.requests),
            latest_status=latest_req.status if latest_req else None,
            recheck_after=latest_req.recheck_after if latest_req else None,
            is_property_broker=bool(b.is_property_broker),
            enabled=bool(b.enabled),
            priority=b.priority,
            priority_source=b.priority_source,
            captcha_plugin_id=b.captcha_plugin_id,
        ))
    return result


@router.get("/captcha-solvers")
def list_captcha_solvers(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    List installed plugins that offer CAPTCHA solving capabilities.
    """
    from ..models.database import InstalledPlugin
    plugins = db.query(InstalledPlugin).all()
    solvers = []
    for p in plugins:
        try:
            m = json.loads(p.manifest_json or "{}")
        except Exception:
            m = {}
        hooks = m.get("hooks", [])
        ptype = m.get("type", "")
        if "solve_captcha" in hooks or ptype == "captcha":
            solvers.append({
                "plugin_id": p.plugin_id,
                "name": p.name,
                "version": p.version,
                "enabled": bool(p.enabled),
                "status": p.status,
            })
    return solvers


@router.get("/{broker_id}", response_model=BrokerOut)
def get_broker(
    broker_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    b = db.query(Broker).filter(Broker.id == broker_id).first()
    if not b:
        raise HTTPException(404, "Broker not found")
    return b


@router.patch("/{broker_id}", response_model=BrokerOut)
def update_broker(
    broker_id: int,
    data: BrokerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("brokers.manage")),
):
    b = db.query(Broker).filter(Broker.id == broker_id).first()
    if not b:
        raise HTTPException(404, "Broker not found")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(b, field, val)
    db.commit()
    db.refresh(b)
    return BrokerOut(
        id=b.id, name=b.name, opt_out_url=b.opt_out_url,
        method=b.method, difficulty=b.difficulty, status=b.status,
        notes=b.notes, date_added=b.date_added,
        request_count=len(b.requests), is_property_broker=bool(b.is_property_broker),
        enabled=bool(b.enabled), priority=b.priority, priority_source=b.priority_source,
        captcha_plugin_id=b.captcha_plugin_id,
    )


@router.patch("/{broker_id}/captcha-solver", response_model=BrokerOut)
def set_broker_captcha_solver(
    broker_id: int,
    data: BrokerCaptchaSolverUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("brokers.manage")),
):
    """
    Assign or clear the preferred CAPTCHA solver plugin for a broker.
    """
    b = db.query(Broker).filter(Broker.id == broker_id).first()
    if not b:
        raise HTTPException(404, "Broker not found")
    b.captcha_plugin_id = data.captcha_plugin_id.strip() if data.captcha_plugin_id else None
    db.commit()
    db.refresh(b)
    return BrokerOut(
        id=b.id, name=b.name, opt_out_url=b.opt_out_url,
        method=b.method, difficulty=b.difficulty, status=b.status,
        notes=b.notes, date_added=b.date_added,
        request_count=len(b.requests), is_property_broker=bool(b.is_property_broker),
        enabled=bool(b.enabled), priority=b.priority, priority_source=b.priority_source,
        captcha_plugin_id=b.captcha_plugin_id,
    )


@router.post("/import-csv")
def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("brokers.manage")),
):
    """
    Import brokers from the enriched CSV we generated.
    Accepts columns: name, status, opt_out_url, method, difficulty, notes
    """
    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))

    added = 0
    updated = 0
    for row in reader:
        name = row.get("name", "").strip()
        if not name:
            continue

        existing = db.query(Broker).filter(Broker.name.ilike(name)).first()

        def safe_enum(val, enum_cls, default):
            try:
                return enum_cls(val.lower()) if val else default
            except ValueError:
                return default

        method     = safe_enum(row.get("method", ""), OptOutMethod, OptOutMethod.form)
        difficulty = safe_enum(row.get("difficulty", ""), Difficulty, Difficulty.medium)
        status_val = safe_enum(row.get("status", ""), BrokerStatus, BrokerStatus.compliant)

        if existing:
            existing.opt_out_url = row.get("opt_out_url") or existing.opt_out_url
            existing.method      = method
            existing.difficulty  = difficulty
            existing.status      = status_val
            existing.notes       = row.get("notes") or existing.notes
            updated += 1
        else:
            db.add(Broker(
                name=name,
                opt_out_url=row.get("opt_out_url"),
                method=method,
                difficulty=difficulty,
                status=status_val,
                notes=row.get("notes"),
            ))
            added += 1

    db.commit()
    return {"added": added, "updated": updated}


# ── Single broker form add ────────────────────────────────────────────────────

class BrokerCreate(BaseModel):
    name: str
    opt_out_url: Optional[str] = None
    method: Optional[str] = "form"
    difficulty: Optional[str] = "medium"
    status: Optional[str] = "compliant"
    notes: Optional[str] = None


@router.post("", response_model=BrokerOut, status_code=201)
def create_broker(
    data: BrokerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("brokers.manage")),
):
    """Add a single broker via form."""
    from ..core.auth import require_super_admin
    existing = db.query(Broker).filter(Broker.name.ilike(data.name.strip())).first()
    if existing:
        raise HTTPException(400, f"Broker '{data.name}' already exists (id={existing.id})")

    def safe_enum(val, enum_cls, default):
        try:
            return enum_cls(val.lower()) if val else default
        except ValueError:
            return default

    b = Broker(
        name=data.name.strip(),
        opt_out_url=data.opt_out_url,
        method=safe_enum(data.method, OptOutMethod, OptOutMethod.form),
        difficulty=safe_enum(data.difficulty, Difficulty, Difficulty.medium),
        status=safe_enum(data.status, BrokerStatus, BrokerStatus.compliant),
        notes=data.notes,
    )
    db.add(b); db.commit(); db.refresh(b)
    return BrokerOut(
        id=b.id, name=b.name, opt_out_url=b.opt_out_url,
        method=b.method, difficulty=b.difficulty, status=b.status,
        notes=b.notes, date_added=b.date_added, request_count=0,
    )


@router.delete("/{broker_id}", status_code=204)
def delete_broker(
    broker_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("brokers.manage")),
):
    b = db.query(Broker).filter(Broker.id == broker_id).first()
    if not b: raise HTTPException(404, "Broker not found")
    db.delete(b); db.commit()


# ── JSON bulk import ──────────────────────────────────────────────────────────

@router.post("/import-json")
def import_json_brokers(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("brokers.manage")),
):
    """
    Import brokers from a JSON file.
    Accepts either:
      [ { "name": "...", "opt_out_url": "...", "method": "...", ... }, ... ]
    or the export format:
      { "brokers": [ ... ] }
    """
    import json as _json
    content = file.file.read().decode("utf-8")
    try:
        data = _json.loads(content)
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    rows = data if isinstance(data, list) else data.get("brokers", [])
    if not rows:
        raise HTTPException(400, "No broker entries found in JSON")

    def safe_enum(val, enum_cls, default):
        try:
            return enum_cls(val.lower()) if val else default
        except ValueError:
            return default

    added = updated = skipped = 0
    errors = []
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            skipped += 1; continue
        try:
            existing = db.query(Broker).filter(Broker.name.ilike(name)).first()
            method     = safe_enum(row.get("method"),     OptOutMethod,  OptOutMethod.form)
            difficulty = safe_enum(row.get("difficulty"), Difficulty,    Difficulty.medium)
            status_val = safe_enum(row.get("status"),     BrokerStatus,  BrokerStatus.compliant)
            if existing:
                existing.opt_out_url = row.get("opt_out_url") or existing.opt_out_url
                existing.method      = method
                existing.difficulty  = difficulty
                existing.status      = status_val
                existing.notes       = row.get("notes") or existing.notes
                updated += 1
            else:
                db.add(Broker(
                    name=name, opt_out_url=row.get("opt_out_url"),
                    method=method, difficulty=difficulty,
                    status=status_val, notes=row.get("notes"),
                ))
                added += 1
        except Exception:
            errors.append(f"{name}: invalid record format")

    db.commit()
    return {"added": added, "updated": updated, "skipped": skipped, "errors": errors}


# ── Broker health + enablement ────────────────────────────────────────────────
# Surfaces the health monitor's per-broker record to admins and lets them
# manually disable a broker or re-enable one the monitor auto-disabled. See
# core/broker_health.py for the tracking + auto-disable logic.

from ..core.broker_health import re_enable as _health_re_enable, disable as _health_disable


class BrokerHealthOut(BaseModel):
    broker_id: int
    name: str
    enabled: bool
    consecutive_failures: int = 0
    total_attempts: int = 0
    total_successes: int = 0
    total_failures: int = 0
    success_rate: Optional[float] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_failure_reason: Optional[str] = None
    last_failure_detail: Optional[str] = None
    auto_disabled: bool = False
    auto_disabled_at: Optional[datetime] = None
    auto_disabled_reason: Optional[str] = None
    needs_review: bool = False
    captcha_plugin_id: Optional[str] = None


def _health_out(broker, h) -> "BrokerHealthOut":
    attempts = (h.total_attempts if h else 0) or 0
    succ     = (h.total_successes if h else 0) or 0
    rate = round(100.0 * succ / attempts, 1) if attempts else None
    return BrokerHealthOut(
        broker_id=broker.id, name=broker.name, enabled=bool(broker.enabled),
        consecutive_failures=(h.consecutive_failures or 0) if h else 0,
        total_attempts=attempts, total_successes=succ,
        total_failures=(h.total_failures or 0) if h else 0,
        success_rate=rate,
        last_success_at=h.last_success_at if h else None,
        last_failure_at=h.last_failure_at if h else None,
        last_failure_reason=h.last_failure_reason if h else None,
        last_failure_detail=h.last_failure_detail if h else None,
        auto_disabled=bool(h.auto_disabled) if h else False,
        auto_disabled_at=h.auto_disabled_at if h else None,
        auto_disabled_reason=h.auto_disabled_reason if h else None,
        needs_review=bool(h.needs_review) if h else False,
        captcha_plugin_id=getattr(broker, "captcha_plugin_id", None),
    )


@router.get("/health/all", response_model=List[BrokerHealthOut])
def list_broker_health(
    needs_review: bool = Query(False, description="Only brokers flagged for admin review"),
    disabled_only: bool = Query(False, description="Only disabled brokers"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Health record for every broker, newest-problem-first. Admin visibility."""
    from ..models.database import BrokerHealth
    q = db.query(Broker, BrokerHealth).outerjoin(
        BrokerHealth, BrokerHealth.broker_id == Broker.id)
    rows = q.all()
    out = []
    for broker, h in rows:
        if needs_review and not (h and h.needs_review):
            continue
        if disabled_only and broker.enabled:
            continue
        out.append(_health_out(broker, h))
    # Sort: needs-review first, then most consecutive failures, then name
    out.sort(key=lambda x: (not x.needs_review, -x.consecutive_failures, x.name.lower()))
    return out


@router.get("/{broker_id}/health", response_model=BrokerHealthOut)
def get_broker_health(
    broker_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from ..models.database import BrokerHealth
    broker = db.query(Broker).filter(Broker.id == broker_id).first()
    if not broker:
        raise HTTPException(404, "Broker not found")
    h = db.query(BrokerHealth).filter(BrokerHealth.broker_id == broker_id).first()
    return _health_out(broker, h)


@router.post("/{broker_id}/disable", response_model=BrokerHealthOut)
def disable_broker(
    broker_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Manually turn a broker off. It will be skipped by all runs until re-enabled."""
    if not has_permission(user, "brokers.manage"):
        raise HTTPException(403, "This needs the 'Manage brokers' permission")
    from ..models.database import BrokerHealth
    broker = db.query(Broker).filter(Broker.id == broker_id).first()
    if not broker:
        raise HTTPException(404, "Broker not found")
    _health_disable(db, broker_id, reason=f"manually disabled by {user.email}")
    db.refresh(broker)
    h = db.query(BrokerHealth).filter(BrokerHealth.broker_id == broker_id).first()
    return _health_out(broker, h)


@router.post("/{broker_id}/enable", response_model=BrokerHealthOut)
def enable_broker(
    broker_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Re-enable a broker (clears an auto-disable and resets its consecutive-failure
    count). Use after reviewing why it was failing — e.g. fixing its add-on.
    """
    if not has_permission(user, "brokers.manage"):
        raise HTTPException(403, "This needs the 'Manage brokers' permission")
    from ..models.database import BrokerHealth
    broker = db.query(Broker).filter(Broker.id == broker_id).first()
    if not broker:
        raise HTTPException(404, "Broker not found")
    _health_re_enable(db, broker_id)
    db.refresh(broker)
    h = db.query(BrokerHealth).filter(BrokerHealth.broker_id == broker_id).first()
    return _health_out(broker, h)


# ── Broker priority (1..5): manual set, bulk rules, reset, import/export ───────
# One source of truth: Broker.priority (1..5) + priority_source (default|rule|
# manual). See core/broker_priority.py. Rules are destructive bulk writes that
# only touch matching brokers; the UI previews the effect first (with a
# manual-overwrite count) before applying. Priority changes need brokers.manage.

from ..core import broker_priority as _bp


def _require_admin(user: User):
    if not has_permission(user, "brokers.manage"):
        raise HTTPException(403, "This needs the 'Manage brokers' permission")


class PrioritySet(BaseModel):
    priority: int                       # 1..5


class BulkPrioritySet(BaseModel):
    broker_ids: List[int]
    priority: int                       # 1..5


class RuleModel(BaseModel):
    set_priority: int
    status: Optional[str] = None
    difficulty: Optional[str] = None
    method: Optional[str] = None
    is_property_broker: Optional[bool] = None
    name_contains: Optional[str] = None
    label: Optional[str] = ""


def _rule_from_model(m: "RuleModel") -> "_bp.PriorityRule":
    return _bp.PriorityRule(
        set_priority=m.set_priority, status=m.status, difficulty=m.difficulty,
        method=m.method, is_property_broker=m.is_property_broker,
        name_contains=m.name_contains, label=m.label or "",
    )


@router.patch("/{broker_id}/priority", response_model=BrokerOut)
def set_broker_priority(broker_id: int, body: PrioritySet,
                        db: Session = Depends(get_db),
                        user: User = Depends(require_permission("brokers.manage"))):
    """Manually set one broker's priority (marks source = manual)."""
    _require_admin(user)
    if not (1 <= body.priority <= 5):
        raise HTTPException(400, "priority must be 1..5")
    b = db.query(Broker).filter(Broker.id == broker_id).first()
    if not b:
        raise HTTPException(404, "Broker not found")
    b.priority = body.priority
    b.priority_source = "manual"
    db.commit(); db.refresh(b)
    return b


@router.post("/priority/bulk-set")
def bulk_set_priority(body: BulkPrioritySet,
                      db: Session = Depends(get_db),
                      user: User = Depends(require_permission("brokers.manage"))):
    """Manually set priority on a bulk-selected set of brokers (source = manual)."""
    _require_admin(user)
    if not (1 <= body.priority <= 5):
        raise HTTPException(400, "priority must be 1..5")
    rows = db.query(Broker).filter(Broker.id.in_(body.broker_ids)).all()
    for b in rows:
        b.priority = body.priority
        b.priority_source = "manual"
    db.commit()
    return {"updated": len(rows)}


@router.post("/priority/rule/preview")
def preview_priority_rule(rule: RuleModel,
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """
    Preview what a rule WOULD do before applying it. Returns the counts that
    drive the overwrite warning — total matched, how many change, and of those
    how many were set manually (about to be overwritten).
    """
    _require_admin(user)
    r = _rule_from_model(rule)
    errs = r.validate()
    if errs:
        raise HTTPException(400, f"invalid rule: {errs}")
    brokers = db.query(Broker).all()
    pv = _bp.preview_rule(r, brokers)
    return {
        "total_matched": pv.total_matched,
        "would_change": pv.would_change,
        "overwrites_manual": pv.overwrites_manual,
        "overwrites_rule_or_default": pv.overwrites_rule_or_default,
    }


@router.post("/priority/rule/apply")
def apply_priority_rule(rule: RuleModel,
                        db: Session = Depends(get_db),
                        user: User = Depends(require_permission("brokers.manage"))):
    """
    Apply a rule: writes the priority into every matching broker (source = rule).
    Only matching brokers are touched. The client should have shown the preview
    warning first; this endpoint performs the destructive write.
    """
    _require_admin(user)
    r = _rule_from_model(rule)
    errs = r.validate()
    if errs:
        raise HTTPException(400, f"invalid rule: {errs}")
    brokers = db.query(Broker).all()
    changed = _bp.apply_rule(r, brokers)
    db.commit()
    return {"changed": changed}


@router.post("/{broker_id}/priority/reset", response_model=BrokerOut)
def reset_broker_priority(broker_id: int,
                          db: Session = Depends(get_db),
                          user: User = Depends(require_permission("brokers.manage"))):
    """Reset one broker to its derived default priority (source = default)."""
    _require_admin(user)
    b = db.query(Broker).filter(Broker.id == broker_id).first()
    if not b:
        raise HTTPException(404, "Broker not found")
    _bp.reset_to_default(b)
    db.commit(); db.refresh(b)
    return b


@router.post("/priority/reset-all")
def reset_all_priorities(db: Session = Depends(get_db),
                         user: User = Depends(require_permission("brokers.manage"))):
    """Reset ALL brokers to derived default. Clears every manual/rule value."""
    _require_admin(user)
    brokers = db.query(Broker).all()
    for b in brokers:
        _bp.reset_to_default(b)
    db.commit()
    return {"reset": len(brokers)}


@router.get("/priority/export")
def export_priorities(kind: str = Query("both", description="rankings | rules | both"),
                      db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """
    Export priorities for sharing between deployments. `kind`:
      rankings — final broker->priority numbers
      rules    — (reserved: rules are not yet persisted server-side; returns empty)
      both     — rankings plus any rules
    Rules persistence is a follow-on; for now rankings carry the shareable data.
    """
    _require_admin(user)
    brokers = db.query(Broker).all()
    if kind == "rankings":
        return _bp.export_rankings(brokers)
    if kind == "rules":
        return _bp.export_rules([])   # rules not persisted yet; see note above
    return _bp.export_both(brokers, [])


@router.post("/priority/import")
def import_priorities(data: dict,
                      db: Session = Depends(get_db),
                      user: User = Depends(require_permission("brokers.manage"))):
    """
    Import a priority export (rankings, rules, or both). Rankings are applied to
    matching brokers by name (source = manual). Any rules in the file are
    validated and returned to the client to review/run via the rule endpoints —
    imported rules are NOT auto-applied, since running a rule is a destructive
    action that needs the preview/confirm step.
    """
    _require_admin(user)
    try:
        parsed = _bp.parse_import(data)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Failed to parse priority export. Verify the import file structure and values.",
        )
    applied = 0
    if parsed["rankings"]:
        by_name = {b.name.lower(): b for b in db.query(Broker).all()}
        applied = _bp.apply_imported_rankings(parsed["rankings"], by_name)
        db.commit()
    return {
        "rankings_applied": applied,
        "rules_found": [r.to_dict() for r in parsed["rules"]],
        "note": "Rankings applied. Any rules are returned for review — run them "
                "via the rule preview/apply endpoints so the overwrite warning shows.",
    }
