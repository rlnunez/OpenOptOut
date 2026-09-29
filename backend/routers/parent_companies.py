"""
Parent-company admin API.

Lets a super admin create parent companies (operators that run many broker
front-sites), edit their opt-out email + locale, group/ungroup child brokers
under them, and see effectiveness stats (does this parent honor email opt-outs?).

The parent-company grouping is the core of the email-first strategy: one email
to a parent, enumerating all its children, clears a whole family of listings.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from ..models.database import get_db, ParentCompany, Broker
from ..core.auth import get_current_user, User
from ..core import parent_company as pc

router = APIRouter(prefix="/api/parent-companies", tags=["parent-companies"])


def _admin(user: User):
    from ..core.access import has_permission, PERMISSIONS
    if not has_permission(user, "brokers.manage"):
        raise HTTPException(403, f"This needs the '{PERMISSIONS['brokers.manage']['label']}' permission")


class ParentIn(BaseModel):
    name: str
    optout_email: Optional[str] = None
    cc_emails: Optional[str] = None
    locale: Optional[str] = "en"
    website: Optional[str] = None
    notes: Optional[str] = None


class ParentOut(BaseModel):
    id: int
    name: str
    optout_email: Optional[str]
    cc_emails: Optional[str]
    locale: str
    website: Optional[str]
    notes: Optional[str]
    honor_status: str
    emails_sent: int
    emails_confirmed: int
    emails_failed: int
    confirm_rate: Optional[float]
    child_count: int

    class Config:
        from_attributes = False


class ChildBroker(BaseModel):
    id: int
    name: str
    method: Optional[str] = None
    priority: Optional[int] = None


def _parent_out(p: ParentCompany) -> ParentOut:
    stats = pc.parent_stats(p)
    return ParentOut(
        id=p.id, name=p.name, optout_email=p.optout_email, cc_emails=p.cc_emails,
        locale=p.locale or "en", website=p.website, notes=p.notes,
        honor_status=stats["honor_status"], emails_sent=stats["emails_sent"],
        emails_confirmed=stats["emails_confirmed"], emails_failed=stats["emails_failed"],
        confirm_rate=stats["confirm_rate"], child_count=stats["child_count"],
    )


@router.get("", response_model=List[ParentOut])
def list_parents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    rows = db.query(ParentCompany).order_by(ParentCompany.name).all()
    return [_parent_out(p) for p in rows]


@router.post("", response_model=ParentOut, status_code=201)
def create_parent(body: ParentIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _admin(user)
    if db.query(ParentCompany).filter(ParentCompany.name.ilike(body.name.strip())).first():
        raise HTTPException(400, f"Parent company '{body.name}' already exists")
    p = ParentCompany(
        name=body.name.strip(), optout_email=body.optout_email, cc_emails=body.cc_emails,
        locale=body.locale or "en", website=body.website, notes=body.notes,
    )
    db.add(p); db.commit(); db.refresh(p)
    return _parent_out(p)


@router.patch("/{parent_id}", response_model=ParentOut)
def update_parent(parent_id: int, body: ParentIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _admin(user)
    p = db.query(ParentCompany).filter(ParentCompany.id == parent_id).first()
    if not p:
        raise HTTPException(404, "Parent company not found")
    p.name = body.name.strip() or p.name
    p.optout_email = body.optout_email
    p.cc_emails = body.cc_emails
    p.locale = body.locale or "en"
    p.website = body.website
    p.notes = body.notes
    db.commit(); db.refresh(p)
    return _parent_out(p)


@router.delete("/{parent_id}")
def delete_parent(parent_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _admin(user)
    p = db.query(ParentCompany).filter(ParentCompany.id == parent_id).first()
    if not p:
        raise HTTPException(404, "Parent company not found")
    # Un-group children first (don't delete the brokers themselves).
    for child in list(p.children):
        child.parent_company_id = None
    db.delete(p); db.commit()
    return {"deleted": parent_id}


@router.get("/{parent_id}/children", response_model=List[ChildBroker])
def list_children(parent_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _admin(user)
    rows = db.query(Broker).filter(Broker.parent_company_id == parent_id).order_by(Broker.name).all()
    return [ChildBroker(
        id=b.id, name=b.name,
        method=b.method.value if b.method else None,
        priority=b.priority,
    ) for b in rows]


class AssignIn(BaseModel):
    broker_ids: List[int]


@router.post("/{parent_id}/assign")
def assign_children(parent_id: int, body: AssignIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Group the given brokers under this parent (sets their parent_company_id)."""
    _admin(user)
    p = db.query(ParentCompany).filter(ParentCompany.id == parent_id).first()
    if not p:
        raise HTTPException(404, "Parent company not found")
    rows = db.query(Broker).filter(Broker.id.in_(body.broker_ids)).all()
    for b in rows:
        b.parent_company_id = parent_id
    db.commit()
    return {"assigned": len(rows)}


@router.post("/unassign")
def unassign_children(body: AssignIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Remove the given brokers from whatever parent they're under."""
    _admin(user)
    rows = db.query(Broker).filter(Broker.id.in_(body.broker_ids)).all()
    for b in rows:
        b.parent_company_id = None
    db.commit()
    return {"unassigned": len(rows)}


@router.get("/unassigned/brokers", response_model=List[ChildBroker])
def list_unassigned(search: Optional[str] = Query(None),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Brokers not yet grouped under any parent — candidates to assign."""
    _admin(user)
    q = db.query(Broker).filter(Broker.parent_company_id.is_(None))
    if search:
        q = q.filter(Broker.name.ilike(f"%{search}%"))
    rows = q.order_by(Broker.name).limit(200).all()
    return [ChildBroker(id=b.id, name=b.name,
                        method=b.method.value if b.method else None,
                        priority=b.priority) for b in rows]


@router.post("/{parent_id}/dispatch")
def dispatch_parent(
    parent_id: int,
    member_id: Optional[int] = Query(None, description="Optional member ID filter"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Trigger immediate email opt-outs to this parent company for all pending child requests.
    """
    _admin(user)
    p = db.query(ParentCompany).filter(ParentCompany.id == parent_id).first()
    if not p:
        raise HTTPException(404, "Parent company not found")
    if not p.optout_email:
        raise HTTPException(400, f"Parent company '{p.name}' has no opt-out email configured")

    from ..core.optout_engine import process_pending_parent_company_optouts
    from ..core.settings_store import load_settings
    cfg = load_settings()

    res = process_pending_parent_company_optouts(
        db, cfg, member_id=member_id, parent_id=parent_id
    )
    return {
        "parent_id": parent_id,
        "parent_name": p.name,
        "sent_emails": res["sent_emails"],
        "covered_requests": res["covered_requests"],
        "covered_request_ids": res["covered_request_ids"],
        "errors": res["errors"],
    }


@router.post("/dispatch-all")
def dispatch_all_parents(
    member_id: Optional[int] = Query(None, description="Optional member ID filter"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Trigger email-first opt-outs across all parent companies for any pending child requests.
    """
    _admin(user)
    from ..core.optout_engine import process_pending_parent_company_optouts
    from ..core.settings_store import load_settings
    cfg = load_settings()

    res = process_pending_parent_company_optouts(db, cfg, member_id=member_id)
    return {
        "sent_emails": res["sent_emails"],
        "covered_requests": res["covered_requests"],
        "covered_request_ids": res["covered_request_ids"],
        "errors": res["errors"],
    }

