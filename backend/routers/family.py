"""
Family member and identity endpoints.
All access checks go through core.auth.assert_can_view / assert_can_edit.
Super admins bypass all checks. Parents only access explicitly granted profiles.
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..models.database import get_db, FamilyMember, Identity, User
from ..core.auth import (
    get_current_user, get_accessible_member_ids,
    assert_can_view, assert_can_edit
)
from ..core.access import has_permission

family_router   = APIRouter(prefix="/api/family",   tags=["family"])
identity_router = APIRouter(prefix="/api/identity", tags=["identity"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class IdentityOut(BaseModel):
    id: int
    member_id: int
    kind: str
    value: str
    is_primary: bool
    is_deed: Optional[bool] = False
    is_mortgage: Optional[bool] = False

    class Config:
        from_attributes = True


class IdentityCreate(BaseModel):
    kind: str
    value: str
    is_primary: bool = False
    is_deed: bool = False
    is_mortgage: bool = False


class IdentityUpdate(BaseModel):
    value: Optional[str] = None
    is_primary: Optional[bool] = None
    is_deed: Optional[bool] = None
    is_mortgage: Optional[bool] = None


class MemberOut(BaseModel):
    id: int
    user_id: int
    full_name: str
    formal_name: Optional[str] = None
    age: Optional[int]
    created_at: datetime
    identities: List[IdentityOut] = []
    can_edit: bool = True

    class Config:
        from_attributes = True


class MemberUpdate(BaseModel):
    full_name: Optional[str] = None
    formal_name: Optional[str] = None
    age: Optional[int] = None


# ── Family member endpoints ───────────────────────────────────────────────────

@family_router.get("", response_model=List[MemberOut])
def list_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all family member profiles this user can access."""
    accessible_ids = get_accessible_member_ids(db, current_user)
    members = db.query(FamilyMember).filter(
        FamilyMember.id.in_(accessible_ids)
    ).order_by(FamilyMember.created_at).all()

    result = []
    for m in members:
        # determine edit permission
        can_edit = current_user.is_super_admin or m.user_id == current_user.id or \
            has_permission(current_user, "members.edit_all")
        if not can_edit:
            from ..models.database import ProfileAccess
            grant = db.query(ProfileAccess).filter(
                ProfileAccess.manager_id == current_user.id,
                ProfileAccess.managed_id == m.user_id,
                ProfileAccess.can_edit == True,
            ).first()
            can_edit = grant is not None

        result.append(MemberOut(
            id=m.id, user_id=m.user_id, full_name=m.full_name,
            formal_name=m.formal_name,
            age=m.age, created_at=m.created_at,
            identities=m.identities, can_edit=can_edit,
        ))
    return result


@family_router.patch("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: int,
    data: MemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    member = assert_can_edit(db, current_user, member_id)
    if data.full_name is not None:
        member.full_name = data.full_name
        member.user.full_name = data.full_name
    if data.formal_name is not None:
        # Empty string clears the formal name
        member.formal_name = data.formal_name if data.formal_name.strip() else None
    if data.age is not None:
        member.age = data.age
    db.commit()
    db.refresh(member)
    return MemberOut(
        id=member.id, user_id=member.user_id, full_name=member.full_name,
        formal_name=member.formal_name,
        age=member.age, created_at=member.created_at,
        identities=member.identities, can_edit=True,
    )


# ── Identity endpoints ────────────────────────────────────────────────────────

@identity_router.get("/{member_id}", response_model=List[IdentityOut])
def list_identities(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assert_can_view(db, current_user, member_id)
    return (
        db.query(Identity)
        .filter(Identity.member_id == member_id)
        .order_by(Identity.kind, Identity.is_primary.desc())
        .all()
    )


@identity_router.post("/{member_id}", response_model=IdentityOut, status_code=201)
def add_identity(
    member_id: int,
    data: IdentityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assert_can_edit(db, current_user, member_id)

    # Enforce vault limits — configurable by super admin in Settings
    from ..core.combinations import get_vault_limits
    limits = get_vault_limits()
    limit_map = {"name": "name", "address": "address", "phone": "phone", "email": "email"}
    if data.kind in limit_map:
        current_count = db.query(Identity).filter(
            Identity.member_id == member_id,
            Identity.kind == data.kind,
        ).count()
        max_allowed = limits[data.kind]
        if current_count >= max_allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {max_allowed} {data.kind}s per member (configurable in Settings → Vault limits)"
            )

    if data.is_primary:
        db.query(Identity).filter(
            Identity.member_id == member_id,
            Identity.kind == data.kind,
            Identity.is_primary == True,
        ).update({"is_primary": False})

    identity = Identity(
        member_id=member_id, kind=data.kind,
        value=data.value, is_primary=data.is_primary,
        is_deed=data.is_deed if data.kind == "address" else False,
        is_mortgage=data.is_mortgage if data.kind == "address" else False,
    )
    db.add(identity)
    db.commit()
    db.refresh(identity)
    return identity


@identity_router.patch("/{identity_id}", response_model=IdentityOut)
def update_identity(
    identity_id: int,
    data: IdentityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    identity = db.query(Identity).filter(Identity.id == identity_id).first()
    if not identity:
        raise HTTPException(404, "Identity not found")
    assert_can_edit(db, current_user, identity.member_id)

    if data.value is not None:
        identity.value = data.value
    if data.is_deed is not None and identity.kind == "address":
        identity.is_deed = data.is_deed
    if data.is_mortgage is not None and identity.kind == "address":
        identity.is_mortgage = data.is_mortgage
    if data.is_primary is not None:
        if data.is_primary:
            db.query(Identity).filter(
                Identity.member_id == identity.member_id,
                Identity.kind == identity.kind,
                Identity.is_primary == True,
            ).update({"is_primary": False})
        identity.is_primary = data.is_primary

    db.commit()
    db.refresh(identity)
    return identity


@identity_router.delete("/{identity_id}", status_code=204)
def delete_identity(
    identity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    identity = db.query(Identity).filter(Identity.id == identity_id).first()
    if not identity:
        raise HTTPException(404, "Identity not found")
    assert_can_edit(db, current_user, identity.member_id)
    db.delete(identity)
    db.commit()


# ── Vault limits + combo stats ────────────────────────────────────────────────

from ..core.combinations import combo_stats

@identity_router.get("/{member_id}/stats")
def identity_stats(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return vault completeness + combination matrix preview."""
    member = assert_can_view(db, current_user, member_id)
    return combo_stats(member)


# ── ILS Patron Demographics Import Endpoints ─────────────────────────────────

class ILSImportDecision(BaseModel):
    action: str  # "import" | "discard"
    fields: Optional[Dict[str, Any]] = None


@family_router.get("/ils-import-pending")
def get_ils_import_pending(
    current_user: User = Depends(get_current_user),
):
    """Check if there are pending demographic fields staged from an ILS login."""
    raw = getattr(current_user, "pending_ils_import", None)
    if not raw:
        return {"has_pending": False, "fields": None}
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and any(bool(v) for v in data.values()):
            return {"has_pending": True, "fields": data}
    except Exception:
        pass
    return {"has_pending": False, "fields": None}


@family_router.post("/ils-import-decision")
def decide_ils_import(
    req: ILSImportDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Process patron's choice to import their ILS information or enter it manually.
    If action is 'discard', pending import is cleared and fields remain blank.
    If action is 'import', demographic fields are saved into their Identity Vault.
    """
    if req.action == "discard":
        current_user.pending_ils_import = None
        db.commit()
        return {"ok": True, "action": "discard", "message": "Import dismissed; enter information manually."}

    pending_raw = getattr(current_user, "pending_ils_import", None)
    pending_data = {}
    if pending_raw:
        try:
            pending_data = json.loads(pending_raw)
        except Exception:
            pass
    data = {**pending_data, **(req.fields or {})}

    member = db.query(FamilyMember).filter(FamilyMember.user_id == current_user.id).first()
    if not member:
        member = FamilyMember(user_id=current_user.id, full_name=current_user.full_name or "Primary Member")
        db.add(member)
        db.flush()

    if data.get("name"):
        val = str(data["name"]).strip()
        db.add(Identity(member_id=member.id, kind="name", value=val, is_primary=True))
        member.formal_name = val
        if not current_user.full_name or current_user.full_name.startswith("Patron "):
            current_user.full_name = val

    if data.get("email"):
        db.add(Identity(member_id=member.id, kind="email", value=str(data["email"]).strip().lower(), is_primary=True))

    if data.get("phone"):
        db.add(Identity(member_id=member.id, kind="phone", value=str(data["phone"]).strip(), is_primary=True))

    addr_str = data.get("raw_address") or data.get("address") or ""
    if not addr_str and (data.get("city") or data.get("state")):
        addr_str = ", ".join(filter(None, [data.get("address"), data.get("city"), data.get("state")]))
    if addr_str:
        db.add(Identity(member_id=member.id, kind="address", value=str(addr_str).strip(), is_primary=True))

    if data.get("birthdate"):
        try:
            from ..core.sip2_rules import dob_to_age
            age = dob_to_age(str(data["birthdate"]))
            if age is not None:
                member.age = age
        except Exception:
            pass

    current_user.pending_ils_import = None
    db.commit()
    return {"ok": True, "action": "import", "message": "Information imported into Identity Vault."}
