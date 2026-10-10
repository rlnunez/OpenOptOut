"""
Auth router — local login, OIDC redirect/callback, SIP2/LDAP login,
registration with domain/invite controls, token refresh, me endpoint.
"""

import secrets, json, hashlib, logging, threading, time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator

from ..models.database import get_db, User, FamilyMember, UserRole, InviteCode, UsageEvent
from ..core.auth import (
    hash_password, verify_password, is_legacy_unpeppered_hash, create_access_token,
    get_current_user, get_current_user_optional, require_super_admin, validate_password_length
)
from ..core.access import require_permission
from ..core import login_throttle, rate_limit
from ..core.auth_providers import (
    try_ldap_auth, try_sip2_auth,
    get_oidc_login_url, exchange_oidc_code,
    provider_enabled, get_provider_config, OIDC_PRESETS
)
from ..core.settings_store import load_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# In-memory OIDC state store: state -> {provider, redirect_uri, issued_at}.
# /oidc/{provider}/login is public and adds one per call, so states expire after
# _OIDC_STATE_TTL and the store is capped (oldest dropped first under a flood).
_oidc_states: dict[str, dict] = {}
_OIDC_STATE_TTL = 600
_OIDC_MAX_STATES = 10_000
_oidc_lock = threading.Lock()


def _prune_oidc_states(now: float):
    # Insertion order is issue order, so stop at the first live state.
    while _oidc_states:
        state, data = next(iter(_oidc_states.items()))
        if now - data["issued_at"] <= _OIDC_STATE_TTL and len(_oidc_states) < _OIDC_MAX_STATES:
            break
        del _oidc_states[state]


def _remember_oidc_state(state: str, provider: str, redirect_uri: str):
    now = time.time()
    with _oidc_lock:
        _prune_oidc_states(now)
        _oidc_states[state] = {"provider": provider, "redirect_uri": redirect_uri, "issued_at": now}


def _take_oidc_state(state: str):
    """Single use: remove and return the state's data, or None if unknown or expired."""
    with _oidc_lock:
        data = _oidc_states.pop(state, None)
    if data and time.time() - data["issued_at"] <= _OIDC_STATE_TTL:
        return data
    return None


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
    mfa_enabled: bool = False
    totp_enabled: bool = False
    webauthn_count: int = 0
    allowed_mfa_methods: Dict[str, bool] = {}

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


@router.post("/register", response_model=UserOut, status_code=201,
             dependencies=[Depends(rate_limit.limit("register", 10))])
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


@router.post("/token", dependencies=[Depends(rate_limit.limit("signin", 60))])
def login(form: OAuth2PasswordRequestForm = Depends(), request: Request = None, db: Session = Depends(get_db)):
    throttle_key = login_throttle.account_key("password", form.username)
    ip_key = login_throttle.ip_key(request)
    login_throttle.check(throttle_key, ip_key)
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not user.hashed_password or not verify_password(form.password, user.hashed_password):
        login_throttle.failure(throttle_key, ip_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_throttle.success(throttle_key)

    # Automatic transparent hash upgrade: if legacy unpeppered, upgrade to HMAC-SHA256 peppered hash!
    if is_legacy_unpeppered_hash(form.password, user.hashed_password):
        try:
            user.hashed_password = hash_password(form.password)
            db.commit()
        except Exception:
            pass

    from ..core import mfa
    allowed_methods = mfa.get_user_allowed_mfa_methods(user)
    webauthn_keys = []
    if user.webauthn_credentials:
        try:
            webauthn_keys = json.loads(user.webauthn_credentials)
        except Exception:
            pass

    has_totp = bool(user.totp_enabled and allowed_methods.get("totp", True))
    has_webauthn = bool(len(webauthn_keys) > 0 and allowed_methods.get("webauthn", True))
    has_backup = bool(user.backup_codes and len(json.loads(user.backup_codes or "[]")) > 0 and allowed_methods.get("backup_codes", True))

    if has_totp or has_webauthn or has_backup:
        ticket = mfa.create_mfa_ticket(user.id, user.email)
        rp_id = request.url.hostname if (request and request.url) else None
        webauthn_opts = mfa.create_webauthn_authentication_options(webauthn_keys, rp_id=rp_id) if (has_webauthn and webauthn_keys) else None
        if webauthn_opts:
            tdata = mfa.verify_mfa_ticket(ticket) or {}
            tdata["challenge"] = webauthn_opts["challenge"]
            ticket = mfa.encrypt_password(json.dumps(tdata))

        return {
            "mfa_required": True,
            "mfa_ticket": ticket,
            "methods": {
                "totp": has_totp,
                "webauthn": has_webauthn,
                "has_backup_codes": has_backup,
            },
            "allowed_methods": allowed_methods,
            "webauthn_options": webauthn_opts,
        }

    mandated, days_left = mfa.is_mfa_mandated(user, db)
    if mandated:
        ticket = mfa.create_mfa_ticket(user.id, user.email)
        role_val = getattr(getattr(user, "role", None), "value", str(getattr(user, "role", "")))
        compliance_rules = mfa.get_mfa_role_compliance()
        role_comp = compliance_rules.get(role_val, mfa.DEFAULT_MFA_COMPLIANCE.get(role_val, {}))
        timer_val = role_comp.get("value", 3)
        timer_unit = role_comp.get("unit", "days")
        role_title = role_val.replace("_", " ").title() if role_val else "User"
        return {
            "mfa_mandated": True,
            "mfa_ticket": ticket,
            "allowed_methods": allowed_methods,
            "detail": f"Multi-Factor Authentication (MFA) is mandated for {role_title} accounts {timer_val} {timer_unit} after account creation. Please configure an authenticator app (TOTP) or security key (YubiKey / Touch ID) to continue.",
        }

    return {"access_token": create_access_token({"sub": user.email}), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    from ..core.access import effective_permissions
    from ..core import mfa
    branch_name = current_user.branch.name if current_user.branch else None
    system_name = current_user.branch.system.name if current_user.branch and current_user.branch.system else None
    system_id = current_user.branch.system_id if current_user.branch else None

    webauthn_keys = []
    if current_user.webauthn_credentials:
        try:
            webauthn_keys = json.loads(current_user.webauthn_credentials)
        except Exception:
            pass
    has_mfa = bool(current_user.totp_enabled or len(webauthn_keys) > 0)

    return UserOut(id=current_user.id, email=current_user.email,
                   full_name=current_user.full_name, role=current_user.role,
                   unified_view=current_user.unified_view,
                   branch_id=current_user.branch_id,
                   branch_name=branch_name,
                   system_id=system_id,
                   system_name=system_name,
                   permissions=effective_permissions(current_user),
                   mfa_enabled=has_mfa,
                   totp_enabled=bool(current_user.totp_enabled),
                   webauthn_count=len(webauthn_keys),
                   allowed_mfa_methods=mfa.get_user_allowed_mfa_methods(current_user))


@router.patch("/me/unified-view")
def toggle_unified_view(unified: bool, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    current_user.unified_view = unified; db.commit()
    return {"unified_view": unified}


# ── LDAP login ────────────────────────────────────────────────────────────────

@router.post("/ldap/login", dependencies=[Depends(rate_limit.limit("signin", 60))])
def ldap_login(req: LDAPLoginRequest, db: Session = Depends(get_db), request: Request = None):
    if not provider_enabled("ldap"):
        raise HTTPException(400, "LDAP authentication is not enabled")

    throttle_key = login_throttle.account_key("ldap", req.username)
    ip_key = login_throttle.ip_key(request)
    login_throttle.check(throttle_key, ip_key)
    result = try_ldap_auth(req.username, req.password)
    if not result.success:
        if not result.unavailable:
            login_throttle.failure(throttle_key, ip_key)
        raise HTTPException(401, result.error or "LDAP authentication failed")
    login_throttle.success(throttle_key)

    return _resolve_external_user(result, db)


# ── SIP2 login ────────────────────────────────────────────────────────────────

@router.post("/sip2/login", dependencies=[Depends(rate_limit.limit("signin", 60))])
def sip2_login(req: SIP2LoginRequest, db: Session = Depends(get_db), request: Request = None):
    from ..models.database import SIP2Connection
    has_db_conns = db.query(SIP2Connection).filter(SIP2Connection.enabled == True).count() > 0
    if not provider_enabled("sip2") and not has_db_conns:
        raise HTTPException(400, "SIP2 authentication is not enabled")

    throttle_key = login_throttle.account_key("sip2", req.barcode)
    ip_key = login_throttle.ip_key(request)
    login_throttle.check(throttle_key, ip_key)
    result = try_sip2_auth(req.barcode, req.pin, db=db)
    if not result.success:
        if not result.unavailable:
            login_throttle.failure(throttle_key, ip_key)
        raise HTTPException(401, result.error or "Library card authentication failed")
    login_throttle.success(throttle_key)

    return _resolve_external_user(result, db)


# ── OIDC (Google, Microsoft, Generic) ────────────────────────────────────────

@router.get("/oidc/{provider}/login", dependencies=[Depends(rate_limit.limit("sso", 30))])
def oidc_login(provider: str, request: Request):
    if not provider_enabled(provider):
        raise HTTPException(400, f"Provider '{provider}' is not enabled")

    state        = secrets.token_urlsafe(32)
    redirect_uri = str(request.base_url).rstrip("/") + f"/api/auth/oidc/{provider}/callback"
    _remember_oidc_state(state, provider, redirect_uri)

    url = get_oidc_login_url(provider, redirect_uri, state)
    if not url:
        raise HTTPException(500, "Could not build OIDC login URL")
    return RedirectResponse(url)


@router.get("/oidc/{provider}/callback", dependencies=[Depends(rate_limit.limit("sso", 30))])
def oidc_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    state_data = _take_oidc_state(state)
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

    demos = getattr(result, "mapped_demographics", {})
    if demos and getattr(result, "populate_vault", False):
        try:
            from ..models.database import Identity, FamilyMember
            member = db.query(FamilyMember).filter(FamilyMember.user_id == user.id).first()
            if member:
                if demos.get("name"):
                    db.add(Identity(member_id=member.id, kind="name", value=demos["name"], is_primary=True))
                    member.formal_name = demos["name"]
                if demos.get("email"):
                    db.add(Identity(member_id=member.id, kind="email", value=demos["email"], is_primary=True))
                if demos.get("phone"):
                    db.add(Identity(member_id=member.id, kind="phone", value=demos["phone"], is_primary=True))
                if demos.get("address"):
                    db.add(Identity(member_id=member.id, kind="address", value=demos["address"], is_primary=True))
                if demos.get("birthdate"):
                    try:
                        from ..core.sip2_rules import dob_to_age
                        age = dob_to_age(demos["birthdate"])
                        if age is not None:
                            member.age = age
                    except Exception:
                        pass
        except Exception as e:
            _log.warning("Could not pre-populate Identity Vault for new user: %s", e)

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


# ── Multi-Factor Authentication (TOTP + WebAuthn / FIDO2) ────────────────────

class VerifyTotpIn(BaseModel):
    mfa_ticket: str
    code: str

class VerifyBackupIn(BaseModel):
    mfa_ticket: str
    code: str

class VerifyWebAuthnIn(BaseModel):
    mfa_ticket: str
    credential: dict

class TotpSetupOut(BaseModel):
    secret: str
    uri: str
    backup_codes: List[str]

class TotpActivateIn(BaseModel):
    mfa_ticket: Optional[str] = None
    secret: Optional[str] = None
    code: str
    backup_codes: Optional[List[str]] = None

class TotpDisableIn(BaseModel):
    password: str

class WebAuthnRegisterIn(BaseModel):
    mfa_ticket: Optional[str] = None
    name: str = "Security Key"
    credential: dict


def _resolve_user_for_mfa(
    db: Session,
    current_user: Optional[User] = None,
    mfa_ticket: Optional[str] = None,
    request: Optional[Request] = None,
) -> User:
    if current_user:
        return current_user
    ticket = mfa_ticket
    if not ticket and request:
        ticket = request.headers.get("X-MFA-Ticket")
    if ticket:
        from ..core import mfa
        tdata = mfa.verify_mfa_ticket(ticket)
        if tdata:
            user = db.query(User).filter(User.id == tdata["uid"]).first()
            if user:
                return user
    if request:
        auth_hdr = request.headers.get("Authorization", "")
        if auth_hdr.startswith("Bearer "):
            token = auth_hdr[7:].strip()
            try:
                from jose import jwt
                from ..core.auth import SECRET_KEY, ALGORITHM
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                email = payload.get("sub")
                if email:
                    user = db.query(User).filter(User.email == email).first()
                    if user and user.can_login:
                        return user
            except Exception:
                pass
    raise HTTPException(status_code=401, detail="Authentication session required")


@router.post("/mfa/verify-totp", dependencies=[Depends(rate_limit.limit("mfa", 30))])
def verify_totp_login(data: VerifyTotpIn, db: Session = Depends(get_db), request: Request = None):
    from ..core import mfa
    tdata = mfa.verify_mfa_ticket(data.mfa_ticket)
    if not tdata:
        raise HTTPException(400, "MFA session expired or invalid. Please sign in again.")
    user = db.query(User).filter(User.id == tdata["uid"]).first()
    if not user or not user.totp_enabled or not user.totp_secret_enc:
        raise HTTPException(400, "TOTP is not configured for this account.")
    allowed = mfa.get_user_allowed_mfa_methods(user)
    if not allowed.get("totp", True):
        raise HTTPException(403, "TOTP authentication is disabled for this account by security policy.")
    throttle_key = login_throttle.account_key("mfa", user.id)
    ip_key = login_throttle.ip_key(request)
    login_throttle.check(throttle_key, ip_key)
    from ..core.settings_store import decrypt_password
    secret = decrypt_password(user.totp_secret_enc)
    if not mfa.verify_totp(data.code, secret):
        login_throttle.failure(throttle_key, ip_key)
        raise HTTPException(401, "Invalid authentication code. Please check your authenticator app.")
    login_throttle.success(throttle_key)
    return {"access_token": create_access_token({"sub": user.email}), "token_type": "bearer"}


@router.post("/mfa/verify-backup", dependencies=[Depends(rate_limit.limit("mfa", 30))])
def verify_backup_code_login(data: VerifyBackupIn, db: Session = Depends(get_db), request: Request = None):
    from ..core import mfa
    tdata = mfa.verify_mfa_ticket(data.mfa_ticket)
    if not tdata:
        raise HTTPException(400, "MFA session expired or invalid. Please sign in again.")
    user = db.query(User).filter(User.id == tdata["uid"]).first()
    if not user or not user.backup_codes:
        raise HTTPException(400, "No backup recovery codes configured for this account.")
    allowed = mfa.get_user_allowed_mfa_methods(user)
    if not allowed.get("backup_codes", True):
        raise HTTPException(403, "Backup recovery codes are disabled for this account by security policy.")
    throttle_key = login_throttle.account_key("mfa", user.id)
    ip_key = login_throttle.ip_key(request)
    login_throttle.check(throttle_key, ip_key)
    try:
        stored_hashes = json.loads(user.backup_codes)
    except Exception:
        stored_hashes = []
    valid, remaining = mfa.verify_backup_code(data.code, stored_hashes)
    if not valid:
        login_throttle.failure(throttle_key, ip_key)
        raise HTTPException(401, "Invalid backup recovery code.")
    login_throttle.success(throttle_key)
    user.backup_codes = json.dumps(remaining)
    db.commit()
    return {
        "access_token": create_access_token({"sub": user.email}),
        "token_type": "bearer",
        "remaining_backup_codes": len(remaining),
    }


@router.post("/mfa/webauthn-options")
def get_webauthn_challenge_options(data: dict, request: Request, db: Session = Depends(get_db)):
    from ..core import mfa
    ticket = data.get("mfa_ticket", "")
    tdata = mfa.verify_mfa_ticket(ticket)
    if not tdata:
        raise HTTPException(400, "MFA session expired or invalid.")
    user = db.query(User).filter(User.id == tdata["uid"]).first()
    if not user or not user.webauthn_credentials:
        raise HTTPException(400, "No security keys registered.")
    allowed = mfa.get_user_allowed_mfa_methods(user)
    if not allowed.get("webauthn", True):
        raise HTTPException(403, "FIDO2 / WebAuthn security key authentication is disabled for this account by security policy.")
    try:
        keys = json.loads(user.webauthn_credentials)
    except Exception:
        keys = []
    rp_id = request.url.hostname
    opts = mfa.create_webauthn_authentication_options(keys, rp_id=rp_id)
    tdata["challenge"] = opts["challenge"]
    from ..core.settings_store import encrypt_password
    opts["mfa_ticket"] = encrypt_password(json.dumps(tdata))
    return opts


@router.post("/mfa/verify-webauthn", dependencies=[Depends(rate_limit.limit("mfa", 30))])
def verify_webauthn_login(data: VerifyWebAuthnIn, db: Session = Depends(get_db)):
    from ..core import mfa
    tdata = mfa.verify_mfa_ticket(data.mfa_ticket)
    if not tdata:
        raise HTTPException(400, "MFA session expired or invalid. Please sign in again.")
    user = db.query(User).filter(User.id == tdata["uid"]).first()
    if not user or not user.webauthn_credentials:
        raise HTTPException(400, "No security keys registered.")
    allowed = mfa.get_user_allowed_mfa_methods(user)
    if not allowed.get("webauthn", True):
        raise HTTPException(403, "FIDO2 / WebAuthn security key authentication is disabled for this account by security policy.")
    try:
        keys = json.loads(user.webauthn_credentials)
    except Exception:
        keys = []
    cred_id = data.credential.get("id")
    matching_key = next((k for k in keys if k["id"] == cred_id), None)
    if not matching_key:
        raise HTTPException(400, "Security key not registered on this account.")
    challenge = tdata.get("challenge", "")
    if not mfa.verify_webauthn_assertion(data.credential, challenge, matching_key):
        raise HTTPException(401, "Security key verification failed.")
    return {"access_token": create_access_token({"sub": user.email}), "token_type": "bearer"}


@router.get("/mfa/status")
def get_mfa_status(
    request: Request,
    mfa_ticket: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    from ..core import mfa
    user = _resolve_user_for_mfa(db, current_user, mfa_ticket, request)
    mandated, days_left = mfa.is_mfa_mandated(user, db)
    allowed_methods = mfa.get_user_allowed_mfa_methods(user)
    keys = []
    if user.webauthn_credentials:
        try:
            keys = json.loads(user.webauthn_credentials)
        except Exception:
            pass
    backup_count = 0
    if user.backup_codes:
        try:
            backup_count = len(json.loads(user.backup_codes))
        except Exception:
            pass

    return {
        "mfa_enabled": mfa.user_has_mfa(user),
        "totp_enabled": bool(user.totp_enabled),
        "webauthn_keys": [{"id": k["id"], "name": k.get("name", "Security Key"), "created_at": k.get("created_at"), "is_fips": k.get("is_fips", False), "fips_model": k.get("fips_model")} for k in keys],
        "backup_codes_count": backup_count,
        "is_mandated": mandated,
        "days_until_mandate": days_left,
        "allowed_methods": allowed_methods,
    }


@router.post("/mfa/totp/setup", response_model=TotpSetupOut)
def setup_totp(
    request: Request,
    data: dict = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    from ..core import mfa
    ticket = (data or {}).get("mfa_ticket")
    user = _resolve_user_for_mfa(db, current_user, ticket, request)
    allowed = mfa.get_user_allowed_mfa_methods(user)
    if not allowed.get("totp", True):
        raise HTTPException(403, "TOTP authenticator app method is disabled for your role or account by security policy.")
    secret = mfa.generate_totp_secret()
    uri = mfa.build_totp_uri(secret, user.email)
    plain_codes, _ = mfa.generate_backup_codes(8)
    return TotpSetupOut(secret=secret, uri=uri, backup_codes=plain_codes)


@router.post("/mfa/totp/activate")
def activate_totp(
    data: TotpActivateIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    from ..core import mfa
    user = _resolve_user_for_mfa(db, current_user, data.mfa_ticket, request)
    allowed = mfa.get_user_allowed_mfa_methods(user)
    if not allowed.get("totp", True):
        raise HTTPException(403, "TOTP authenticator app method is disabled for your role or account by security policy.")
    
    secret = data.secret
    if not secret and user.totp_secret_enc:
        from ..core.settings_store import decrypt_password
        secret = decrypt_password(user.totp_secret_enc)
    if not secret:
        raise HTTPException(400, "TOTP secret is required to activate authenticator.")

    if not mfa.verify_totp(data.code, secret):
        raise HTTPException(400, "Invalid 6-digit verification code. Please try again.")
    from ..core.settings_store import encrypt_password
    user.totp_secret_enc = encrypt_password(secret)
    user.totp_enabled = True

    plain_codes = data.backup_codes
    if not plain_codes:
        plain_codes, _ = mfa.generate_backup_codes(8)
    hashed_codes = [hashlib.sha256(c.strip().upper().encode("utf-8")).hexdigest() for c in plain_codes]
    user.backup_codes = json.dumps(hashed_codes)
    db.commit()
    return {
        "activated": True,
        "backup_codes": plain_codes,
        "access_token": create_access_token({"sub": user.email}),
        "token_type": "bearer",
    }


@router.post("/mfa/totp/disable")
def disable_totp(
    data: TotpDisableIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ..core import mfa
    mandated, _ = mfa.is_mfa_mandated(current_user, db)
    keys = []
    if current_user.webauthn_credentials:
        try: keys = json.loads(current_user.webauthn_credentials)
        except Exception: pass
    if mandated and len(keys) == 0:
        raise HTTPException(400, "MFA is mandated for this account and cannot be disabled without another method enrolled.")

    if not current_user.hashed_password or not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(400, "Password verification failed.")
    if is_legacy_unpeppered_hash(data.password, current_user.hashed_password):
        try:
            current_user.hashed_password = hash_password(data.password)
        except Exception:
            pass
    current_user.totp_enabled = False
    current_user.totp_secret_enc = None
    db.commit()
    return {"disabled": True}


@router.post("/mfa/webauthn/register-options")
def get_webauthn_register_options(
    request: Request,
    data: dict = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    from ..core import mfa
    ticket = (data or {}).get("mfa_ticket")
    user = _resolve_user_for_mfa(db, current_user, ticket, request)
    allowed = mfa.get_user_allowed_mfa_methods(user)
    if not allowed.get("webauthn", True):
        raise HTTPException(403, "FIDO2 / WebAuthn security key method is disabled for your role or account by security policy.")
    rp_id = request.url.hostname
    opts = mfa.create_webauthn_registration_options(user.id, user.email, user.full_name, rp_id=rp_id)
    if ticket:
        tdata = mfa.verify_mfa_ticket(ticket) or {}
        tdata["reg_challenge"] = opts["challenge"]
        from ..core.settings_store import encrypt_password
        opts["mfa_ticket"] = encrypt_password(json.dumps(tdata))
    return opts


@router.post("/mfa/webauthn/register")
def register_webauthn_key(
    data: WebAuthnRegisterIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    from ..core import mfa
    user = _resolve_user_for_mfa(db, current_user, data.mfa_ticket, request)
    allowed = mfa.get_user_allowed_mfa_methods(user)
    if not allowed.get("webauthn", True):
        raise HTTPException(403, "FIDO2 / WebAuthn security key method is disabled for your role or account by security policy.")
    challenge = ""
    if data.mfa_ticket:
        tdata = mfa.verify_mfa_ticket(data.mfa_ticket)
        challenge = tdata.get("reg_challenge", "") if tdata else ""
    cfg = mfa.get_webauthn_config()
    try:
        parsed = mfa.parse_and_validate_registration_response(
            data.credential,
            expected_challenge=challenge or data.credential.get("challenge", ""),
            fips_only=cfg.get("fips_only", False),
        )
    except ValueError as ve:
        logger.warning("Security key registration validation error: %s", ve)
        err_msg = str(ve)
        if "NIST FIPS 140" in err_msg:
            detail = "Security key is not a certified NIST FIPS 140-2 / FIPS 140-3 device."
        elif "challenge" in err_msg.lower():
            detail = "Security key challenge verification failed. Please try again."
        else:
            detail = "Invalid security key attestation data. Please verify your authenticator."
        raise HTTPException(status_code=400, detail=detail)
    except Exception as e:
        logger.error("Security key registration failed unexpectedly: %s", e, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Security key registration failed. Please ensure the key is supported and try again.",
        )

    keys = []
    if user.webauthn_credentials:
        try: keys = json.loads(user.webauthn_credentials)
        except Exception: pass

    parsed["name"] = data.name or ("YubiKey" if parsed.get("is_fips") else "Security Key")
    parsed["created_at"] = datetime.now(timezone.utc).isoformat()
    keys.append(parsed)
    user.webauthn_credentials = json.dumps(keys)

    plain_backup_codes = []
    if not user.backup_codes:
        plain_backup_codes, _ = mfa.generate_backup_codes(8)
        hashed_codes = [hashlib.sha256(c.strip().upper().encode("utf-8")).hexdigest() for c in plain_backup_codes]
        user.backup_codes = json.dumps(hashed_codes)

    db.commit()

    return {
        "registered": True,
        "key": parsed,
        "backup_codes": plain_backup_codes,
        "access_token": create_access_token({"sub": user.email}),
        "token_type": "bearer",
    }


@router.delete("/mfa/webauthn/{key_id}")
def delete_webauthn_key(
    key_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ..core import mfa
    keys = []
    if current_user.webauthn_credentials:
        try: keys = json.loads(current_user.webauthn_credentials)
        except Exception: pass
    filtered = [k for k in keys if k["id"] != key_id]
    mandated, _ = mfa.is_mfa_mandated(current_user, db)
    if mandated and not current_user.totp_enabled and len(filtered) == 0:
        raise HTTPException(400, "MFA is mandated for this account; you must keep at least one method enabled.")
    current_user.webauthn_credentials = json.dumps(filtered)
    db.commit()
    return {"deleted": True, "remaining": len(filtered)}
