"""
Consortium hierarchy router — library systems, branches, multi-connection SIP2,
manager scope assignments, and patron branch overrides.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional, Any
from datetime import datetime
import json

from ..models.database import (
    get_db, User, UserRole, LibrarySystem, Branch, SIP2Connection, ManagerScope
)
from ..core.auth import (get_current_user, require_super_admin, assert_system_in_scope,
                         assert_branch_in_scope)
from ..core.access import require_permission, has_permission
from ..core.settings_store import encrypt_password, decrypt_password

router = APIRouter(prefix="/api/consortium", tags=["consortium"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class SystemCreate(BaseModel):
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=30)
    allow_custom_branding: bool = False
    branding_config: Optional[str] = None


class SystemUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    allow_custom_branding: Optional[bool] = None
    branding_config: Optional[str] = None


class SystemOut(BaseModel):
    id: int
    name: str
    code: str
    allow_custom_branding: bool
    branding_config: Optional[str] = None
    created_at: datetime
    branch_count: int = 0
    patron_count: int = 0

    class Config:
        from_attributes = True


class BranchCreate(BaseModel):
    system_id: int
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=30)
    ils_location_codes: Optional[str] = None


class BranchUpdate(BaseModel):
    system_id: Optional[int] = None
    name: Optional[str] = None
    code: Optional[str] = None
    ils_location_codes: Optional[str] = None


class BranchOut(BaseModel):
    id: int
    system_id: int
    system_name: Optional[str] = None
    system_code: Optional[str] = None
    name: str
    code: str
    ils_location_codes: Optional[str] = None
    created_at: datetime
    patron_count: int = 0

    class Config:
        from_attributes = True


class SIP2ConnectionCreate(BaseModel):
    system_id: Optional[int] = None
    name: str
    host: str
    port: int = 6001
    use_tls: bool = False
    ca_cert_pem: Optional[str] = None
    ca_cert_path: Optional[str] = None
    institution_id: Optional[str] = ""
    ils_login: Optional[str] = ""
    ils_password: Optional[str] = None
    barcode_prefix: Optional[str] = None
    branch_field_code: str = "AQ"
    email_domain: str = "library.local"
    default_role: str = "parent"
    timeout_seconds: int = 10
    enabled: bool = True
    priority: int = 10
    eligibility_rules: Optional[Any] = None
    date_format: str = "auto"
    map_patron_fields: bool = False
    field_mappings: Optional[Any] = None
    forced_fields: Optional[Any] = ["library"]
    patron_choice: bool = True
    populate_vault: bool = False


class SIP2ConnectionUpdate(BaseModel):
    system_id: Optional[int] = None
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    use_tls: Optional[bool] = None
    ca_cert_pem: Optional[str] = None
    ca_cert_path: Optional[str] = None
    institution_id: Optional[str] = None
    ils_login: Optional[str] = None
    ils_password: Optional[str] = None
    barcode_prefix: Optional[str] = None
    branch_field_code: Optional[str] = None
    email_domain: Optional[str] = None
    default_role: Optional[str] = None
    timeout_seconds: Optional[int] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    eligibility_rules: Optional[Any] = None
    date_format: Optional[str] = None
    map_patron_fields: Optional[bool] = None
    field_mappings: Optional[Any] = None
    forced_fields: Optional[Any] = None
    patron_choice: Optional[bool] = None
    populate_vault: Optional[bool] = None


class SIP2ConnectionOut(BaseModel):
    id: int
    system_id: Optional[int] = None
    system_name: Optional[str] = None
    name: str
    host: str
    port: int
    use_tls: bool
    ca_cert_pem: Optional[str] = None
    ca_cert_path: Optional[str] = None
    institution_id: str
    ils_login: str
    password_set: bool
    barcode_prefix: Optional[str] = None
    branch_field_code: str
    email_domain: str
    default_role: str
    timeout_seconds: int
    enabled: bool
    priority: int
    eligibility_rules: Optional[Any] = None
    date_format: str = "auto"
    map_patron_fields: bool = False
    field_mappings: Optional[Any] = None
    forced_fields: Optional[Any] = ["library"]
    patron_choice: bool = True
    populate_vault: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class ScopeItem(BaseModel):
    scope_type: str  # 'consortium' | 'system' | 'branch'
    system_id: Optional[int] = None
    branch_id: Optional[int] = None


class ManagerScopesUpdate(BaseModel):
    scopes: List[ScopeItem]


class PatronBranchOverride(BaseModel):
    branch_id: int


# ── Library Systems Endpoints ─────────────────────────────────────────────────

@router.get("/systems", response_model=List[SystemOut])
def list_systems(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all library systems. Open to staff, managers, and super admins."""
    systems = db.query(LibrarySystem).order_by(LibrarySystem.name.asc()).all()
    out = []
    for s in systems:
        b_count = db.query(Branch).filter(Branch.system_id == s.id).count()
        p_count = db.query(User).filter(User.branch_id.in_(
            db.query(Branch.id).filter(Branch.system_id == s.id)
        )).count()
        out.append(SystemOut(
            id=s.id, name=s.name, code=s.code,
            allow_custom_branding=s.allow_custom_branding,
            branding_config=s.branding_config,
            created_at=s.created_at,
            branch_count=b_count,
            patron_count=p_count,
        ))
    return out


@router.post("/systems", response_model=SystemOut, status_code=status.HTTP_201_CREATED)
def create_system(
    data: SystemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("consortium.manage")),
):
    assert_system_in_scope(db, current_user, None)   # only unscoped managers add systems
    code_clean = data.code.strip().lower()
    if db.query(LibrarySystem).filter(LibrarySystem.code == code_clean).first():
        raise HTTPException(400, f"Library system code '{code_clean}' already exists")

    system = LibrarySystem(
        name=data.name.strip(),
        code=code_clean,
        allow_custom_branding=data.allow_custom_branding,
        branding_config=data.branding_config,
    )
    db.add(system)
    db.commit()
    db.refresh(system)
    return SystemOut(
        id=system.id, name=system.name, code=system.code,
        allow_custom_branding=system.allow_custom_branding,
        branding_config=system.branding_config,
        created_at=system.created_at,
        branch_count=0, patron_count=0,
    )


@router.get("/systems/{system_id}", response_model=SystemOut)
def get_system(
    system_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.query(LibrarySystem).filter(LibrarySystem.id == system_id).first()
    if not s:
        raise HTTPException(404, "Library system not found")
    b_count = db.query(Branch).filter(Branch.system_id == s.id).count()
    p_count = db.query(User).filter(User.branch_id.in_(
        db.query(Branch.id).filter(Branch.system_id == s.id)
    )).count()
    return SystemOut(
        id=s.id, name=s.name, code=s.code,
        allow_custom_branding=s.allow_custom_branding,
        branding_config=s.branding_config,
        created_at=s.created_at,
        branch_count=b_count,
        patron_count=p_count,
    )


@router.patch("/systems/{system_id}", response_model=SystemOut)
def update_system(
    system_id: int,
    data: SystemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.query(LibrarySystem).filter(LibrarySystem.id == system_id).first()
    if not s:
        raise HTTPException(404, "Library system not found")

    is_super = current_user.is_super_admin
    can_manage_consortium = has_permission(current_user, "consortium.manage")
    can_manage_branding = has_permission(current_user, "system.branding")

    if not is_super and not can_manage_consortium:
        # Check if user is manager with system.branding scoped to this system
        user_scopes = db.query(ManagerScope).filter(ManagerScope.user_id == current_user.id).all()
        scoped_to_this = any(
            (sc.scope_type == "system" and sc.system_id == system_id) or
            (sc.scope_type == "consortium")
            for sc in user_scopes
        )
        if not (can_manage_branding and s.allow_custom_branding and scoped_to_this):
            raise HTTPException(403, "Permission denied")

        # Scoped branding managers may ONLY update branding_config
        if data.branding_config is not None:
            s.branding_config = data.branding_config
        db.commit()
        db.refresh(s)
        b_count = db.query(Branch).filter(Branch.system_id == s.id).count()
        p_count = db.query(User).filter(User.branch_id.in_(
            db.query(Branch.id).filter(Branch.system_id == s.id)
        )).count()
        return SystemOut(
            id=s.id, name=s.name, code=s.code,
            allow_custom_branding=s.allow_custom_branding,
            branding_config=s.branding_config,
            created_at=s.created_at,
            branch_count=b_count, patron_count=p_count,
        )

    # Super admin or consortium.manage can update all fields
    assert_system_in_scope(db, current_user, system_id)
    if data.name is not None:
        s.name = data.name.strip()
    if data.code is not None:
        code_clean = data.code.strip().lower()
        conflict = db.query(LibrarySystem).filter(
            LibrarySystem.code == code_clean, LibrarySystem.id != system_id
        ).first()
        if conflict:
            raise HTTPException(400, f"Library system code '{code_clean}' already in use")
        s.code = code_clean
    if data.allow_custom_branding is not None:
        s.allow_custom_branding = data.allow_custom_branding
    if data.branding_config is not None:
        s.branding_config = data.branding_config

    db.commit()
    db.refresh(s)
    b_count = db.query(Branch).filter(Branch.system_id == s.id).count()
    p_count = db.query(User).filter(User.branch_id.in_(
        db.query(Branch.id).filter(Branch.system_id == s.id)
    )).count()
    return SystemOut(
        id=s.id, name=s.name, code=s.code,
        allow_custom_branding=s.allow_custom_branding,
        branding_config=s.branding_config,
        created_at=s.created_at,
        branch_count=b_count, patron_count=p_count,
    )


@router.delete("/systems/{system_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system(
    system_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("consortium.manage")),
):
    s = db.query(LibrarySystem).filter(LibrarySystem.id == system_id).first()
    if not s:
        raise HTTPException(404, "Library system not found")
    assert_system_in_scope(db, current_user, system_id)
    db.delete(s)
    db.commit()


# ── Branches Endpoints ────────────────────────────────────────────────────────

@router.get("/branches", response_model=List[BranchOut])
def list_branches(
    system_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Branch)
    if system_id is not None:
        q = q.filter(Branch.system_id == system_id)
    branches = q.order_by(Branch.name.asc()).all()
    out = []
    for b in branches:
        p_count = db.query(User).filter(User.branch_id == b.id).count()
        out.append(BranchOut(
            id=b.id, system_id=b.system_id,
            system_name=b.system.name if b.system else None,
            system_code=b.system.code if b.system else None,
            name=b.name, code=b.code,
            ils_location_codes=b.ils_location_codes,
            created_at=b.created_at,
            patron_count=p_count,
        ))
    return out


@router.post("/branches", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
def create_branch(
    data: BranchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("consortium.manage")),
):
    sys = db.query(LibrarySystem).filter(LibrarySystem.id == data.system_id).first()
    if not sys:
        raise HTTPException(404, "Parent library system not found")
    assert_system_in_scope(db, current_user, data.system_id)

    branch = Branch(
        system_id=data.system_id,
        name=data.name.strip(),
        code=data.code.strip(),
        ils_location_codes=data.ils_location_codes,
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return BranchOut(
        id=branch.id, system_id=branch.system_id,
        system_name=sys.name, system_code=sys.code,
        name=branch.name, code=branch.code,
        ils_location_codes=branch.ils_location_codes,
        created_at=branch.created_at, patron_count=0,
    )


@router.patch("/branches/{branch_id}", response_model=BranchOut)
def update_branch(
    branch_id: int,
    data: BranchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("consortium.manage")),
):
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(404, "Branch not found")
    assert_branch_in_scope(db, current_user, branch_id)

    if data.system_id is not None:
        sys = db.query(LibrarySystem).filter(LibrarySystem.id == data.system_id).first()
        if not sys:
            raise HTTPException(404, "Target library system not found")
        assert_system_in_scope(db, current_user, data.system_id)
        branch.system_id = data.system_id
    if data.name is not None:
        branch.name = data.name.strip()
    if data.code is not None:
        branch.code = data.code.strip()
    if data.ils_location_codes is not None:
        branch.ils_location_codes = data.ils_location_codes

    db.commit()
    db.refresh(branch)
    p_count = db.query(User).filter(User.branch_id == branch.id).count()
    return BranchOut(
        id=branch.id, system_id=branch.system_id,
        system_name=branch.system.name if branch.system else None,
        system_code=branch.system.code if branch.system else None,
        name=branch.name, code=branch.code,
        ils_location_codes=branch.ils_location_codes,
        created_at=branch.created_at, patron_count=p_count,
    )


@router.delete("/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("consortium.manage")),
):
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(404, "Branch not found")
    assert_branch_in_scope(db, current_user, branch_id)
    # Unlink assigned users before deletion
    db.query(User).filter(User.branch_id == branch_id).update({
        User.branch_id: None,
        User.branch_source: "unassigned",
    })
    db.delete(branch)
    db.commit()


# ── SIP2 Connections Endpoints ────────────────────────────────────────────────

def _parse_eligibility_rules(raw: Optional[str]) -> Optional[Any]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _parse_field_mappings(raw: Optional[str]) -> Optional[Any]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _parse_forced_fields(raw: Optional[str]) -> List[str]:
    if not raw:
        return ["library"]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
        return [str(parsed)]
    except Exception:
        if isinstance(raw, str):
            return [x.strip() for x in raw.split(",") if x.strip()]
        return ["library"]


@router.get("/sip2-connections", response_model=List[SIP2ConnectionOut])
def list_sip2_connections(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("consortium.sip2")),
):
    conns = db.query(SIP2Connection).order_by(SIP2Connection.priority.asc()).all()
    return [
        SIP2ConnectionOut(
            id=c.id, system_id=c.system_id,
            system_name=c.system.name if c.system else "Consortium Shared",
            name=c.name, host=c.host, port=c.port, use_tls=c.use_tls,
            ca_cert_pem=c.ca_cert_pem, ca_cert_path=c.ca_cert_path,
            institution_id=c.institution_id, ils_login=c.ils_login,
            password_set=bool(c.ils_password_enc),
            barcode_prefix=c.barcode_prefix, branch_field_code=c.branch_field_code,
            email_domain=c.email_domain, default_role=c.default_role,
            timeout_seconds=c.timeout_seconds, enabled=c.enabled,
            priority=c.priority,
            eligibility_rules=_parse_eligibility_rules(c.eligibility_rules),
            date_format=c.date_format or "auto",
            map_patron_fields=bool(getattr(c, "map_patron_fields", False)),
            field_mappings=_parse_field_mappings(getattr(c, "field_mappings", None)),
            forced_fields=_parse_forced_fields(getattr(c, "forced_fields", None)),
            patron_choice=bool(getattr(c, "patron_choice", True)),
            populate_vault=bool(getattr(c, "populate_vault", False)),
            created_at=c.created_at,
        )
        for c in conns
    ]


@router.post("/sip2-connections", response_model=SIP2ConnectionOut, status_code=status.HTTP_201_CREATED)
def create_sip2_connection(
    data: SIP2ConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("consortium.sip2")),
):
    if data.system_id:
        sys = db.query(LibrarySystem).filter(LibrarySystem.id == data.system_id).first()
        if not sys:
            raise HTTPException(404, "Associated library system not found")

    enc_pw = encrypt_password(data.ils_password) if data.ils_password else ""
    elig_str = ""
    if data.eligibility_rules is not None:
        from ..core.sip2_rules import validate_sip2_rules
        valid, err = validate_sip2_rules(data.eligibility_rules)
        if not valid:
            raise HTTPException(400, f"Invalid eligibility rules: {err}")
        elig_str = json.dumps(data.eligibility_rules) if isinstance(data.eligibility_rules, (dict, list)) else str(data.eligibility_rules)

    mappings_str = ""
    if data.field_mappings is not None:
        mappings_str = json.dumps(data.field_mappings) if isinstance(data.field_mappings, (dict, list)) else str(data.field_mappings)

    forced_str = json.dumps(data.forced_fields) if isinstance(data.forced_fields, list) else str(data.forced_fields or '["library"]')

    c = SIP2Connection(
        system_id=data.system_id,
        name=data.name.strip(),
        host=data.host.strip(),
        port=data.port,
        use_tls=data.use_tls,
        ca_cert_pem=data.ca_cert_pem,
        ca_cert_path=data.ca_cert_path,
        institution_id=data.institution_id or "",
        ils_login=data.ils_login or "",
        ils_password_enc=enc_pw,
        barcode_prefix=data.barcode_prefix.strip() if data.barcode_prefix else None,
        branch_field_code=(data.branch_field_code or "AQ").strip(),
        email_domain=(data.email_domain or "library.local").strip(),
        default_role=data.default_role,
        timeout_seconds=data.timeout_seconds,
        enabled=data.enabled,
        priority=data.priority,
        eligibility_rules=elig_str,
        date_format=(data.date_format or "auto").strip(),
        map_patron_fields=bool(data.map_patron_fields),
        field_mappings=mappings_str,
        forced_fields=forced_str,
        patron_choice=bool(data.patron_choice),
        populate_vault=bool(data.populate_vault),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return SIP2ConnectionOut(
        id=c.id, system_id=c.system_id,
        system_name=c.system.name if c.system else "Consortium Shared",
        name=c.name, host=c.host, port=c.port, use_tls=c.use_tls,
        ca_cert_pem=c.ca_cert_pem, ca_cert_path=c.ca_cert_path,
        institution_id=c.institution_id, ils_login=c.ils_login,
        password_set=bool(c.ils_password_enc),
        barcode_prefix=c.barcode_prefix, branch_field_code=c.branch_field_code,
        email_domain=c.email_domain, default_role=c.default_role,
        timeout_seconds=c.timeout_seconds, enabled=c.enabled,
        priority=c.priority,
        eligibility_rules=data.eligibility_rules,
        date_format=c.date_format or "auto",
        map_patron_fields=bool(c.map_patron_fields),
        field_mappings=_parse_field_mappings(c.field_mappings),
        forced_fields=_parse_forced_fields(c.forced_fields),
        patron_choice=bool(c.patron_choice),
        populate_vault=bool(c.populate_vault),
        created_at=c.created_at,
    )


@router.patch("/sip2-connections/{conn_id}", response_model=SIP2ConnectionOut)
def update_sip2_connection(
    conn_id: int,
    data: SIP2ConnectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("consortium.sip2")),
):
    c = db.query(SIP2Connection).filter(SIP2Connection.id == conn_id).first()
    if not c:
        raise HTTPException(404, "SIP2 connection not found")

    if data.system_id is not None:
        if data.system_id > 0:
            sys = db.query(LibrarySystem).filter(LibrarySystem.id == data.system_id).first()
            if not sys:
                raise HTTPException(404, "Target library system not found")
            c.system_id = data.system_id
        else:
            c.system_id = None
    if data.name is not None: c.name = data.name.strip()
    if data.host is not None: c.host = data.host.strip()
    if data.port is not None: c.port = data.port
    if data.use_tls is not None: c.use_tls = data.use_tls
    if data.ca_cert_pem is not None: c.ca_cert_pem = data.ca_cert_pem
    if data.ca_cert_path is not None: c.ca_cert_path = data.ca_cert_path
    if data.institution_id is not None: c.institution_id = data.institution_id
    if data.ils_login is not None: c.ils_login = data.ils_login
    if data.ils_password is not None and data.ils_password != "":
        c.ils_password_enc = encrypt_password(data.ils_password)
    if data.barcode_prefix is not None:
        c.barcode_prefix = data.barcode_prefix.strip() if data.barcode_prefix else None
    if data.branch_field_code is not None:
        c.branch_field_code = data.branch_field_code.strip()
    if data.email_domain is not None:
        c.email_domain = data.email_domain.strip()
    if data.default_role is not None:
        c.default_role = data.default_role
    if data.timeout_seconds is not None:
        c.timeout_seconds = data.timeout_seconds
    if data.enabled is not None:
        c.enabled = data.enabled
    if data.priority is not None:
        c.priority = data.priority
    if data.eligibility_rules is not None:
        from ..core.sip2_rules import validate_sip2_rules
        valid, err = validate_sip2_rules(data.eligibility_rules)
        if not valid:
            raise HTTPException(400, f"Invalid eligibility rules: {err}")
        c.eligibility_rules = json.dumps(data.eligibility_rules) if isinstance(data.eligibility_rules, (dict, list)) else str(data.eligibility_rules)
    if data.date_format is not None:
        c.date_format = data.date_format.strip()
    if data.map_patron_fields is not None:
        c.map_patron_fields = bool(data.map_patron_fields)
    if data.field_mappings is not None:
        c.field_mappings = json.dumps(data.field_mappings) if isinstance(data.field_mappings, (dict, list)) else str(data.field_mappings)
    if data.forced_fields is not None:
        c.forced_fields = json.dumps(data.forced_fields) if isinstance(data.forced_fields, list) else str(data.forced_fields)
    if data.patron_choice is not None:
        c.patron_choice = bool(data.patron_choice)
    if data.populate_vault is not None:
        c.populate_vault = bool(data.populate_vault)

    db.commit()
    db.refresh(c)
    return SIP2ConnectionOut(
        id=c.id, system_id=c.system_id,
        system_name=c.system.name if c.system else "Consortium Shared",
        name=c.name, host=c.host, port=c.port, use_tls=c.use_tls,
        ca_cert_pem=c.ca_cert_pem, ca_cert_path=c.ca_cert_path,
        institution_id=c.institution_id, ils_login=c.ils_login,
        password_set=bool(c.ils_password_enc),
        barcode_prefix=c.barcode_prefix, branch_field_code=c.branch_field_code,
        email_domain=c.email_domain, default_role=c.default_role,
        timeout_seconds=c.timeout_seconds, enabled=c.enabled,
        priority=c.priority,
        eligibility_rules=_parse_eligibility_rules(c.eligibility_rules),
        date_format=c.date_format or "auto",
        map_patron_fields=bool(getattr(c, "map_patron_fields", False)),
        field_mappings=_parse_field_mappings(getattr(c, "field_mappings", None)),
        forced_fields=_parse_forced_fields(getattr(c, "forced_fields", None)),
        patron_choice=bool(getattr(c, "patron_choice", True)),
        populate_vault=bool(getattr(c, "populate_vault", False)),
        created_at=c.created_at,
    )


@router.delete("/sip2-connections/{conn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sip2_connection(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("consortium.sip2")),
):
    c = db.query(SIP2Connection).filter(SIP2Connection.id == conn_id).first()
    if not c:
        raise HTTPException(404, "SIP2 connection not found")
    db.delete(c)
    db.commit()


@router.post("/sip2-connections/{conn_id}/test")
def test_sip2_connection(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("consortium.sip2")),
):
    c = db.query(SIP2Connection).filter(SIP2Connection.id == conn_id).first()
    if not c:
        raise HTTPException(404, "SIP2 connection not found")

    from ..core.auth_providers import _sip2_connect, sip2_cert_status
    cfg = {
        "host": c.host, "port": c.port, "use_tls": c.use_tls,
        "ca_cert_pem": c.ca_cert_pem, "ca_cert_path": c.ca_cert_path,
        "timeout_seconds": c.timeout_seconds,
    }
    cert_info = sip2_cert_status(cfg) if c.use_tls else None

    try:
        sock = _sip2_connect(c.host, c.port, c.timeout_seconds, c.use_tls,
                             c.ca_cert_pem or "", c.ca_cert_path or "")
        sock.close()
        return {"connected": True, "host": c.host, "port": c.port, "use_tls": c.use_tls, "certificate": cert_info}
    except Exception:
        return {"connected": False, "error": "Connection failed. Check host, port, and TLS settings.", "certificate": cert_info}


# ── Manager Scopes Endpoints ──────────────────────────────────────────────────

@router.get("/manager-scopes/{user_id}", response_model=List[ScopeItem])
def get_manager_scopes(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    scopes = db.query(ManagerScope).filter(ManagerScope.user_id == user_id).all()
    return [
        ScopeItem(scope_type=s.scope_type, system_id=s.system_id, branch_id=s.branch_id)
        for s in scopes
    ]


@router.put("/manager-scopes/{user_id}", response_model=List[ScopeItem])
def set_manager_scopes(
    user_id: int,
    data: ManagerScopesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "User not found")
    if target.role != UserRole.manager:
        raise HTTPException(400, "Scopes can only be assigned to managers")

    # Replace existing scopes
    db.query(ManagerScope).filter(ManagerScope.user_id == user_id).delete()
    new_scopes = []
    for s in data.scopes:
        if s.scope_type not in ("consortium", "system", "branch"):
            raise HTTPException(400, f"Invalid scope_type '{s.scope_type}'")
        row = ManagerScope(
            user_id=user_id,
            scope_type=s.scope_type,
            system_id=s.system_id if s.scope_type == "system" else None,
            branch_id=s.branch_id if s.scope_type == "branch" else None,
        )
        db.add(row)
        new_scopes.append(s)

    db.commit()
    return new_scopes


# ── Patron Branch Overrides & Unassigned Queue ────────────────────────────────

@router.get("/patrons/unassigned")
def list_unassigned_patrons(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("members.override_branch")),
):
    """List patrons whose branch is not yet assigned or could not be mapped."""
    q = db.query(User).filter(User.branch_id == None, User.role == UserRole.parent)
    total = q.count()
    patrons = q.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": p.id,
                "email": p.email,
                "full_name": p.full_name,
                "auth_source": p.auth_source,
                "created_at": p.created_at,
            }
            for p in patrons
        ]
    }


@router.post("/patrons/{user_id}/branch")
def override_patron_branch(
    user_id: int,
    data: PatronBranchOverride,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("members.override_branch")),
):
    """Staff override: assign a patron to a branch explicitly."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Patron not found")

    branch = db.query(Branch).filter(Branch.id == data.branch_id).first()
    if not branch:
        raise HTTPException(404, "Branch not found")

    target.branch_id = branch.id
    target.branch_source = "staff_override"
    target.branch_override_by = current_user.id
    target.branch_override_at = datetime.utcnow()
    db.commit()

    return {
        "status": "ok",
        "user_id": target.id,
        "branch_id": branch.id,
        "branch_name": branch.name,
        "system_name": branch.system.name if branch.system else None,
        "branch_source": target.branch_source,
    }


@router.delete("/patrons/{user_id}/branch-override")
def clear_patron_branch_override(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("members.override_branch")),
):
    """Clear staff override so the patron can be placed dynamically by SIP2."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Patron not found")

    target.branch_source = "sip2"
    target.branch_override_by = None
    target.branch_override_at = None
    db.commit()
    return {"status": "ok", "message": "Override cleared"}
