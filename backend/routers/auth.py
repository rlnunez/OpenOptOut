"""
Auth router — local login, OIDC redirect/callback, SIP2/LDAP login,
registration with domain/invite controls, token refresh, me endpoint.
"""

import secrets, json
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator

from ..models.database import get_db, User, FamilyMember, UserRole, InviteCode, UsageEvent
from ..core.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_super_admin, validate_password_length
)
from ..core.access import require_permission
from ..core.auth_providers import (
    try_ldap_auth, try_sip2_auth,
    get_oidc_login_url, exchange_oidc_code,
    provider_enabled, get_provider_config, OIDC_PRESETS
)
from ..core.settings_store import load_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# In-memory OIDC state store (use Redis in production)
_oidc_states: dict[str, dict] = {}


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: Optional[str] = None
    full_name: str
    invite_code: Optional[str] = None

    _validate_password = field_validator("password")(validate_password_length)


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    unified_view: bool
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    system_id: Optional[int] = None
    system_name: Optional[str] = None
    permissions: List[str] = []   # manager/super admin permissions (core/access.py)
    preferred_language: str = "en"
    tutorial_completed: bool = False

    class Config:
        from_attributes = True


class SIP2LoginRequest(BaseModel):
    barcode: str
    pin: str


class LDAPLoginRequest(BaseModel):
    username: str
    password: str


# ── Registration helpers ──────────────────────────────────────────────────────

def _check_registration_allowed(email: str, invite_code: Optional[str], db: Session) -> UserRole:
    """
    Returns the role to assign if registration is allowed.
    Raises HTTPException if not allowed.
    """
    s    = load_settings()
    reg  = s.get("registration", {})
    mode = reg.get("mode", "open")   # open | domain | invite | admin_only

    # First user always allowed — becomes super_admin
    if db.query(User).count() == 0:
        return UserRole.super_admin

    if mode == "admin_only":
        raise HTTPException(403, "Self-registration is disabled. Contact your administrator.")

    if mode == "domain":
        allowed_domains = [d.strip().lower() for d in reg.get("allowed_domains", "").split(",") if d.strip()]
        if allowed_domains:
            user_domain = email.split("@")[-1].lower()
            if user_domain not in allowed_domains:
                raise HTTPException(403, f"Registration is restricted to: {', '.join(allowed_domains)}")

    if mode == "invite" or reg.get("require_invite"):
        if not invite_code:
            raise HTTPException(403, "An invite code is required to register.")
        code = db.query(InviteCode).filter(
            InviteCode.code == invite_code.strip(),
            InviteCode.is_active == True,
        ).first()
        if not code:
            raise HTTPException(403, "Invalid invite code.")
        if code.expires_at and code.expires_at < datetime.utcnow():
            raise HTTPException(403, "This invite code has expired.")
        if code.max_uses > 0 and code.uses >= code.max_uses:
            raise HTTPException(403, "This invite code has reached its maximum uses.")
        code.uses += 1
        db.commit()
        return code.role

    return UserRole.parent


def _create_user_and_member(db: Session, email: str, full_name: str,
                             role: UserRole, hashed_pw: Optional[str] = None,
                             created_by: Optional[int] = None) -> User:
    user = User(
        email=email,
        hashed_password=hashed_pw,
        full_name=full_name,
        role=role,
        created_by_id=created_by,
    )
    db.add(user); db.flush()
    db.add(FamilyMember(user_id=user.id, full_name=full_name))
    db.add(UsageEvent(event_type="user_registered", user_id=user.id))
    db.commit(); db.refresh(user)
    return user


# ── Local auth ────────────────────────────────────────────────────────────────

@router.get("/needs-setup")
def needs_setup(db: Session = Depends(get_db)):
    """
    Public: does this install have zero user accounts yet? The login page calls
    this on load to decide whether to show first-run setup (create the initial
    administrator) instead of a login form. Reveals only whether the system is
    freshly installed — no user data.
    """
    return {"needs_setup": db.query(User).count() == 0}


@router.post("/register", response_model=UserOut, status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(400, "Email already registered")
    role = _check_registration_allowed(req.email, req.invite_code, db)
    if not req.password and role != UserRole.super_admin:
        raise HTTPException(400, "Password is required")
    user = _create_user_and_member(
        db, req.email, req.full_name, role,
        hashed_pw=hash_password(req.password) if req.password else None,
    )
    return user


@router.post("/token")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not user.hashed_password or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": create_access_token({"sub": user.email}), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    from ..core.access import effective_permissions
    branch_name = current_user.branch.name if current_user.branch else None
    system_name = current_user.branch.system.name if current_user.branch and current_user.branch.system else None
    system_id = current_user.branch.system_id if current_user.branch else None
    return UserOut(id=current_user.id, email=current_user.email,
                   full_name=current_user.full_name, role=current_user.role,
                   unified_view=current_user.unified_view,
                   branch_id=current_user.branch_id,
                   branch_name=branch_name,
                   system_id=system_id,
                   system_name=system_name,
                   permissions=effective_permissions(current_user))


@router.patch("/me/unified-view")
def toggle_unified_view(unified: bool, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    current_user.unified_view = unified; db.commit()
    return {"unified_view": unified}


# ── LDAP login ────────────────────────────────────────────────────────────────

@router.post("/ldap/login")
def ldap_login(req: LDAPLoginRequest, db: Session = Depends(get_db)):
    if not provider_enabled("ldap"):
        raise HTTPException(400, "LDAP authentication is not enabled")

    result = try_ldap_auth(req.username, req.password)
    if not result.success:
        raise HTTPException(401, result.error or "LDAP authentication failed")

    return _resolve_external_user(result, db)


# ── SIP2 login ────────────────────────────────────────────────────────────────

@router.post("/sip2/login")
def sip2_login(req: SIP2LoginRequest, db: Session = Depends(get_db)):
    from ..models.database import SIP2Connection
    has_db_conns = db.query(SIP2Connection).filter(SIP2Connection.enabled == True).count() > 0
    if not provider_enabled("sip2") and not has_db_conns:
        raise HTTPException(400, "SIP2 authentication is not enabled")

    result = try_sip2_auth(req.barcode, req.pin, db=db)
    if not result.success:
        raise HTTPException(401, result.error or "Library card authentication failed")

    return _resolve_external_user(result, db)


# ── OIDC (Google, Microsoft, Generic) ────────────────────────────────────────

@router.get("/oidc/{provider}/login")
def oidc_login(provider: str, request: Request):
    if not provider_enabled(provider):
        raise HTTPException(400, f"Provider '{provider}' is not enabled")

    state        = secrets.token_urlsafe(32)
    redirect_uri = str(request.base_url).rstrip("/") + f"/api/auth/oidc/{provider}/callback"
    _oidc_states[state] = {"provider": provider, "redirect_uri": redirect_uri}

    url = get_oidc_login_url(provider, redirect_uri, state)
    if not url:
        raise HTTPException(500, "Could not build OIDC login URL")
    return RedirectResponse(url)


@router.get("/oidc/{provider}/callback")
def oidc_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    state_data = _oidc_states.pop(state, None)
    if not state_data or state_data["provider"] != provider:
        raise HTTPException(400, "Invalid or expired OAuth state")

    result = exchange_oidc_code(provider, code, state_data["redirect_uri"])
    if not result.success:
        raise HTTPException(401, result.error or "OIDC authentication failed")

    token_data = _resolve_external_user(result, db)
    return _sso_redirect(token_data["access_token"])


@router.get("/oidc/presets")
def oidc_presets(_: User = Depends(require_permission("auth.providers"))):
    return OIDC_PRESETS


# ── External user resolution ──────────────────────────────────────────────────

def _auth_source_for(provider: str) -> str:
    return provider if provider in ("ldap", "sip2", "saml") else f"oidc:{provider}"


def _resolve_external_user(result, db: Session) -> dict:
    """
    Find or create a local user for an externally-authenticated identity
    (OIDC, LDAP, SIP2, SAML). Every external login is checked against the ONE
    shared sign-in policy (core/sso_policy.py): verified email, allowed domains,
    Google hosted-domain proof, required groups, registration mode, and no
    auto-granted super admin. Returns a JWT token dict; raises 403 if denied.
    """
    from ..core.sso_policy import evaluate_sso_login
    import logging
    _log = logging.getLogger(__name__)

    s = load_settings()
    provider_cfg = s.get("auth_providers", {}).get(result.provider, {}) or {}
    registration_cfg = s.get("registration", {}) or {}
    email = (result.email or "").strip().lower()

    existing = db.query(User).filter(User.email == email).first() if email else None
    decision = evaluate_sso_login(result, provider_cfg, registration_cfg,
                                  user_exists=existing is not None,
                                  user_count=db.query(User).count())
    if not decision.allowed:
        account_id = f"user_id={existing.id}" if existing else "unregistered_account"
        _log.warning("SSO sign-in denied (%s, %s): %s", result.provider, account_id, decision.reason)
        raise HTTPException(403, decision.reason)

    source = _auth_source_for(result.provider)
    if existing:
        # Link the account to this provider so it can log in without a password.
        # (Never clear an existing password — local login keeps working.)
        if not existing.auth_source:
            existing.auth_source = source
        # Update branch if dynamically discovered and not staff overridden
        if getattr(result, "branch_id", None) is not None and existing.branch_source != "staff_override":
            existing.branch_id = result.branch_id
            existing.branch_source = "sip2"
        db.commit()
        token = create_access_token({"sub": existing.email})
        return {"access_token": token, "token_type": "bearer"}

    if decision.downgraded:
        _log.warning("SSO provider %s has default_role=super_admin; new user created "
                     "as 'parent' instead (super admin is never auto-granted)",
                     result.provider)
    user = _create_user_and_member(db, email, result.full_name or email,
                                   UserRole(decision.role))
    user.auth_source = source
    if getattr(result, "branch_id", None) is not None:
        user.branch_id = result.branch_id
        user.branch_source = "sip2"
    db.commit()
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}


def _sso_redirect(token: str) -> RedirectResponse:
    """Hand the JWT to the SPA. Path route + URL fragment: the fragment is never
    sent to servers or written to proxy/access logs."""
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost").rstrip("/")
    return RedirectResponse(f"{frontend_url}/auth/callback#token={token}")


# ── Invite code management ────────────────────────────────────────────────────

class InviteCodeCreate(BaseModel):
    max_uses: int = 1
    expires_days: Optional[int] = None
    role: str = "parent"
    note: Optional[str] = None


class InviteCodeOut(BaseModel):
    id: int
    code: str
    max_uses: int
    uses: int
    expires_at: Optional[datetime]
    role: str
    note: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/invite-codes", response_model=list[InviteCodeOut])
def list_invite_codes(db: Session = Depends(get_db), _: User = Depends(require_permission("users.registration"))):
    return db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()


@router.post("/invite-codes", response_model=InviteCodeOut, status_code=201)
def create_invite_code(
    data: InviteCodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.registration")),
):
    # The code's role is what whoever redeems it becomes, so only a super admin
    # may issue codes for super admin or manager accounts.
    try:
        role = UserRole(data.role or "parent")
    except ValueError:
        raise HTTPException(400, f"Invalid role. Must be one of: {[r.value for r in UserRole]}")
    if role in (UserRole.super_admin, UserRole.manager) and not current_user.is_super_admin:
        raise HTTPException(403, "Only a super admin can create invite codes for super admin "
                                 "or manager accounts")
    expires = datetime.utcnow() + timedelta(days=data.expires_days) if data.expires_days else None
    code = InviteCode(
        code=secrets.token_urlsafe(12),
        created_by=current_user.id,
        max_uses=data.max_uses,
        expires_at=expires,
        role=role.value,
        note=data.note,
    )
    db.add(code); db.commit(); db.refresh(code)
    return code


@router.delete("/invite-codes/{code_id}", status_code=204)
def revoke_invite_code(
    code_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("users.registration")),
):
    code = db.query(InviteCode).filter(InviteCode.id == code_id).first()
    if not code: raise HTTPException(404, "Code not found")
    code.is_active = False; db.commit()


import os
