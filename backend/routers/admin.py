"""
User administration:
  - List / create / update / delete users, and profile access between parents:
    super admins, and managers with the "users.manage" permission. Managers
    only ever act on parent and member accounts and can't change roles.
  - Roles, manager permissions and the manager defaults: super admins only.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime

from ..models.database import get_db, User, FamilyMember, ProfileAccess, UserRole
from ..core.auth import hash_password, require_super_admin, get_current_user, validate_password_length
from ..core import access

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    can_login: bool
    unified_view: bool
    created_at: datetime
    # Managers: effective permissions and how they differ from the defaults.
    permissions: List[str] = []
    permissions_granted: List[str] = []
    permissions_revoked: List[str] = []
    managing_count: int = 0
    managed_by_count: int = 0

    class Config:
        from_attributes = True


class CreateUserRequest(BaseModel):
    full_name: str
    email: EmailStr
    role: str = "member"          # 'super_admin' | 'manager' | 'parent' | 'member'
    password: Optional[str] = None  # omit to create a no-login member profile

    _validate_password = field_validator("password")(validate_password_length)


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None   # set to grant/change login
    unified_view: Optional[bool] = None

    _validate_password = field_validator("password")(validate_password_length)


class AccessGrantRequest(BaseModel):
    manager_id:            int   # the user who will manage
    managed_id:            int   # the user whose profile is being shared
    can_view:              bool = True
    can_edit:              bool = True
    max_children_override: Optional[int] = None  # None = use system default


class AccessGrantOut(BaseModel):
    id: int
    manager_id: int
    manager_name: str
    managed_id: int
    managed_name: str
    can_view: bool
    can_edit: bool
    max_children_override: Optional[int]
    granted_at: datetime
    children_count: int = 0       # how many member profiles this manager currently manages


class ManagerPermissionsRequest(BaseModel):
    # The full set this manager should hold. Stored as the difference from the
    # manager defaults, so keys that match the defaults keep following them.
    permissions: List[str]


class ManagerDefaultsRequest(BaseModel):
    permissions: List[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

# Accounts only a super admin may create, change, or delete.
_PRIVILEGED = (UserRole.super_admin, UserRole.manager)


def _user_out(u: User) -> UserOut:
    granted, revoked = access.user_overrides(u)
    return UserOut(
        id=u.id, full_name=u.full_name, email=u.email, role=u.role,
        can_login=u.can_login, unified_view=u.unified_view, created_at=u.created_at,
        managing_count=len(u.managing), managed_by_count=len(u.managed_by),
        permissions=access.effective_permissions(u),
        permissions_granted=granted if u.is_manager else [],
        permissions_revoked=revoked if u.is_manager else [],
    )


def _parse_role(value: str) -> UserRole:
    try:
        return UserRole(value)
    except ValueError:
        raise HTTPException(400, f"Invalid role. Must be one of: {[r.value for r in UserRole]}")


def _only_super_admin_touches_privileged(actor: User, *roles):
    """Managers act on parent and member accounts only."""
    if not actor.is_super_admin and any(r in _PRIVILEGED for r in roles):
        raise HTTPException(403, "Only a super admin can create or change super admin "
                                 "and manager accounts")


# ── User management ───────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(access.require_permission("users.manage")),
):
    return [_user_out(u) for u in db.query(User).order_by(User.created_at).all()]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    req: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(access.require_permission("users.manage")),
):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(400, "Email already registered")

    role = _parse_role(req.role)
    _only_super_admin_touches_privileged(current_user, role)

    user = User(
        email=req.email,
        full_name=req.full_name,
        role=role,
        hashed_password=hash_password(req.password) if req.password else None,
        created_by_id=current_user.id,
    )
    db.add(user)
    db.flush()

    member = FamilyMember(user_id=user.id, full_name=req.full_name)
    db.add(member)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    req: UpdateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(access.require_permission("users.manage")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    _only_super_admin_touches_privileged(current_user, user.role)
    if req.role is not None and not current_user.is_super_admin:
        raise HTTPException(403, "Only a super admin can change roles")

    if req.full_name is not None:
        user.full_name = req.full_name
        if user.family_member:
            user.family_member.full_name = req.full_name

    if req.role is not None:
        user.role = _parse_role(req.role)
        if not user.is_manager:
            # Leaving the manager role drops its permission changes, so being
            # made a manager again starts from the defaults.
            user.permissions_granted = None
            user.permissions_revoked = None

    if req.password is not None:
        user.hashed_password = hash_password(req.password)

    if req.unified_view is not None:
        user.unified_view = req.unified_view

    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(access.require_permission("users.manage")),
):
    if user_id == current_user.id:
        raise HTTPException(400, "Cannot delete your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    _only_super_admin_touches_privileged(current_user, user.role)
    db.delete(user)
    db.commit()


# ── Access grants ─────────────────────────────────────────────────────────────

@router.get("/access", response_model=List[AccessGrantOut])
def list_grants(
    db: Session = Depends(get_db),
    _: User = Depends(access.require_permission("users.manage")),
):
    grants = db.query(ProfileAccess).all()
    return [_grant_out(g) for g in grants]


@router.post("/access", response_model=AccessGrantOut, status_code=201)
def create_grant(
    req: AccessGrantRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(access.require_permission("users.manage")),
):
    if req.manager_id == req.managed_id:
        raise HTTPException(400, "A user always has access to their own profile")
    _check_grant_allowed(db, current_user, req.manager_id, req.managed_id)

    existing = db.query(ProfileAccess).filter(
        ProfileAccess.manager_id == req.manager_id,
        ProfileAccess.managed_id == req.managed_id,
    ).first()
    if existing:
        raise HTTPException(400, "Grant already exists — use PATCH to update it")

    # validate both users exist
    for uid, label in [(req.manager_id, "manager"), (req.managed_id, "managed")]:
        if not db.query(User).filter(User.id == uid).first():
            raise HTTPException(404, f"{label} user not found")

    # Enforce children-per-parent limit for new member grants
    managed_user = db.query(User).filter(User.id == req.managed_id).first()
    if managed_user and managed_user.role == UserRole.member:
        _check_children_limit(db, req.manager_id, current_user.id)

    grant = ProfileAccess(
        manager_id=req.manager_id,
        managed_id=req.managed_id,
        can_view=req.can_view,
        can_edit=req.can_edit,
        granted_by=current_user.id,
        max_children_override=req.max_children_override,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return _grant_out(grant)


@router.patch("/access/{grant_id}", response_model=AccessGrantOut)
def update_grant(
    grant_id: int,
    req: AccessGrantRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(access.require_permission("users.manage")),
):
    grant = db.query(ProfileAccess).filter(ProfileAccess.id == grant_id).first()
    if not grant:
        raise HTTPException(404, "Grant not found")
    _check_grant_allowed(db, current_user, grant.manager_id, grant.managed_id)
    grant.can_view = req.can_view
    grant.can_edit = req.can_edit
    db.commit()
    db.refresh(grant)
    return _grant_out(grant)


@router.delete("/access/{grant_id}", status_code=204)
def revoke_grant(
    grant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(access.require_permission("users.manage")),
):
    grant = db.query(ProfileAccess).filter(ProfileAccess.id == grant_id).first()
    if not grant:
        raise HTTPException(404, "Grant not found")
    _check_grant_allowed(db, current_user, grant.manager_id, grant.managed_id)
    db.delete(grant)
    db.commit()


def _check_grant_allowed(db: Session, actor: User, manager_id: int, managed_id: int):
    """A manager can share profiles between parents and members, but never
    gives themselves access, and never touches super admin or manager accounts."""
    if actor.is_super_admin:
        return
    if actor.id in (manager_id, managed_id):
        raise HTTPException(403, "Managers can't change profile access that involves themselves")
    roles = [u.role for u in db.query(User).filter(User.id.in_([manager_id, managed_id])).all()]
    _only_super_admin_touches_privileged(actor, *roles)


# ── Manager permissions (super admin only) ────────────────────────────────────

@router.get("/permissions")
def permission_catalog(_: User = Depends(access.require_permission("users.manage"))):
    """The permission catalog, the current manager defaults, and the built-in defaults."""
    return {
        "catalog": [{"key": k, **{"sensitive": False, **v}} for k, v in access.PERMISSIONS.items()],
        "defaults": access.manager_defaults(),
        "builtin_defaults": access.clean(access.DEFAULT_MANAGER_PERMISSIONS),
    }


@router.put("/permissions/defaults")
def set_manager_defaults(req: ManagerDefaultsRequest,
                         _: User = Depends(require_super_admin)):
    """Replace the default permission set. Applies to every manager, except
    for permissions a super admin granted or removed for that manager."""
    unknown = set(req.permissions) - set(access.PERMISSIONS)
    if unknown:
        raise HTTPException(400, f"Unknown permissions: {sorted(unknown)}")
    return {"defaults": access.save_manager_defaults(req.permissions)}


@router.put("/users/{user_id}/permissions", response_model=UserOut)
def set_manager_permissions(user_id: int, req: ManagerPermissionsRequest,
                            db: Session = Depends(get_db),
                            _: User = Depends(require_super_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if not user.is_manager:
        raise HTTPException(400, "Only managers have permissions to set")
    unknown = set(req.permissions) - set(access.PERMISSIONS)
    if unknown:
        raise HTTPException(400, f"Unknown permissions: {sorted(unknown)}")
    import json
    wanted, defaults = set(req.permissions), set(access.manager_defaults())
    user.permissions_granted = json.dumps(access.clean(wanted - defaults))
    user.permissions_revoked = json.dumps(access.clean(defaults - wanted))
    db.commit()
    db.refresh(user)
    return _user_out(user)


# ── Helper ────────────────────────────────────────────────────────────────────

def _grant_out(g: ProfileAccess) -> AccessGrantOut:
    from ..models.database import UserRole as UR, SessionLocal
    # Count member-role profiles this manager currently manages
    from sqlalchemy.orm import Session
    manager   = g.manager
    children  = 0
    if manager:
        children = sum(
            1 for x in manager.managing
            if x.managed and x.managed.role == UR.member
        )
    return AccessGrantOut(
        id=g.id,
        manager_id=g.manager_id,
        manager_name=g.manager.full_name if g.manager else "",
        managed_id=g.managed_id,
        managed_name=g.managed.full_name if g.managed else "",
        can_view=g.can_view,
        can_edit=g.can_edit,
        max_children_override=g.max_children_override,
        granted_at=g.granted_at,
        children_count=children,
    )


def _check_children_limit(db, manager_id: int, admin_id: int):
    """Raise HTTPException if adding a child would exceed the limit for this manager."""
    from ..core.settings_store import load_settings
    s       = load_settings()
    sys_max = s.get("vault_limits", {}).get("max_children_per_parent", 0)
    if sys_max == 0:
        return  # unlimited

    manager = db.query(User).filter(User.id == manager_id).first()
    if not manager:
        return

    # Check for a per-grant override on any existing grant this manager has
    # (the override applies to their total child limit)
    override = None
    for g in manager.managing:
        if g.max_children_override is not None:
            override = g.max_children_override
            break

    effective_max = override if override is not None else sys_max

    current_children = sum(
        1 for g in manager.managing
        if g.managed and g.managed.role == UserRole.member
    )

    if current_children >= effective_max:
        raise HTTPException(
            400,
            f"This parent already manages {current_children} child profile(s). "
            f"The limit is {effective_max}. "
            f"Increase the limit in Settings → Vault limits or set a per-parent override."
        )
