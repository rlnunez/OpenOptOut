"""
Branding, registration controls, auth provider config, and announcement banner.
All readable by authenticated users (for applying theme etc),
writable only by super_admin.
"""

import os, base64, json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from ..models.database import get_db, User
from ..core.auth import get_current_user, get_current_user_optional, require_super_admin
from ..core.access import require_permission, has_permission
from ..core.settings_store import load_settings, SETTINGS_FILE
from ..core.auth_providers import OIDC_PRESETS

import base64 as b64lib
from cryptography.fernet import Fernet

router = APIRouter(prefix="/api/branding", tags=["branding"])

LOGO_PATH = os.getenv("LOGO_PATH", "/data/logo")
os.makedirs(LOGO_PATH, exist_ok=True)

_LOGO_EXTENSIONS = {"image/png": "png", "image/svg+xml": "svg", "image/jpeg": "jpeg", "image/webp": "webp"}

def _logo_exists() -> bool:
    return any(os.path.exists(os.path.join(LOGO_PATH, f"logo.{ext}")) for ext in _LOGO_EXTENSIONS.values())


# ── Encryption (reuse from settings) ─────────────────────────────────────────

def _fernet() -> Fernet:
    from ..core.settings_store import get_secret_key
    raw    = get_secret_key()
    # Repeat the key until it fills 32 bytes. Identical to the old
    # `(raw * 4)[:32]` for keys of 8+ chars (existing data still decrypts),
    # but no longer crashes on a shorter SECRET_KEY.
    _kb = raw.encode() or b"\0"
    padded = (_kb * (32 // len(_kb) + 1))[:32]
    return Fernet(b64lib.urlsafe_b64encode(padded))

def _encrypt(v: str) -> str: return _fernet().encrypt(v.encode()).decode()
def _decrypt(v: str) -> str:
    try: return _fernet().decrypt(v.encode()).decode()
    except: return ""

def _save(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Schemas ───────────────────────────────────────────────────────────────────

class BrandingConfig(BaseModel):
    system_name:            str   = "OpenOptOut"
    tagline:                Optional[str] = "Your personal data removal service"
    primary_color:          str   = "#6366f1"
    accent_color:           str   = "#4f46e5"
    logo_url:               Optional[str] = None
    favicon_url:            Optional[str] = None
    contact_email:          Optional[str] = None
    contact_phone:          Optional[str] = None
    support_url:            Optional[str] = None
    welcome_message:        Optional[str] = None
    email_footer:           Optional[str] = None
    terms_url:              Optional[str] = None
    show_powered_by:        bool  = True
    # Dual auth configuration
    show_staff_tab:         bool  = True    # show staff login tab (email/LDAP/OIDC)
    show_patron_tab:        bool  = False   # show patron tab (SIP2 barcode+PIN)
    staff_tab_label:        str   = "Staff"
    patron_tab_label:       str   = "Library Card"
    staff_welcome:          Optional[str] = None  # override welcome msg for staff tab
    patron_welcome:         Optional[str] = None  # override welcome msg for patron tab


class RegistrationConfig(BaseModel):
    mode:              str   = "open"         # open | domain | invite | admin_only
    allowed_domains:   Optional[str] = None   # comma-separated, e.g. "library.org,city.gov"
    require_invite:    bool  = False
    self_registration: bool  = True


class AnnouncementBanner(BaseModel):
    message:   str
    severity:  str  = "info"   # info | warning | maintenance | success
    active:    bool = True
    expires_at: Optional[str] = None


class AuthProviderConfig(BaseModel):
    # SAML (public view exposes only these two)
    saml_enabled:       bool = False
    saml_label:         Optional[str] = None
    # LDAP
    ldap_enabled:       bool  = False
    ldap_host:          Optional[str] = None
    ldap_base_dn:       Optional[str] = None
    ldap_bind_dn:       Optional[str] = None
    ldap_bind_password: Optional[str] = None   # write-only
    ldap_user_attr:     Optional[str] = "sAMAccountName"
    ldap_name_attr:     Optional[str] = "displayName"
    ldap_email_attr:    Optional[str] = "mail"
    ldap_use_tls:       bool  = True
    ldap_tls_mode:      Optional[str] = None   # ldaps | starttls | none
    ldap_port:          Optional[int] = None
    ldap_ca_cert_pem:   Optional[str] = None   # public cert, not a secret
    ldap_email_domain:  Optional[str] = None
    ldap_default_role:  str   = "parent"
    ldap_password_set:  bool  = False          # read-only indicator

    # SIP2
    sip2_enabled:       bool  = False
    sip2_host:          Optional[str] = None
    sip2_port:          int   = 6001
    sip2_use_tls:       bool  = False          # SIP2S — TLS-wrapped SIP2
    sip2_ca_cert_pem:   Optional[str] = None   # pasted CA (public cert)
    sip2_ca_cert_path:  Optional[str] = None   # path to CA bundle in container
    sip2_institution_id: Optional[str] = None
    sip2_ils_login:     Optional[str] = None
    sip2_ils_password:  Optional[str] = None   # write-only
    sip2_email_domain:  Optional[str] = "library.local"
    sip2_default_role:  str   = "parent"
    sip2_password_set:  bool  = False
    sip2_timeout:       int   = 10

    # OIDC providers (google, microsoft, custom + any named)
    oidc_providers:     List[dict] = []


class OIDCProviderConfig(BaseModel):
    key:                str         # 'google' | 'microsoft' | 'custom' | any slug
    label:              str
    enabled:            bool = False
    discovery_url:      Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint:     Optional[str] = None
    userinfo_endpoint:  Optional[str] = None
    client_id:          Optional[str] = None
    client_secret:      Optional[str] = None   # write-only
    scope:              str = "openid email profile"
    default_role:       str = "parent"
    tenant_id:          Optional[str] = None   # Microsoft
    # Sign-in policy (core/sso_policy.py)
    allowed_domains:    Optional[str] = None   # comma-separated; Google also checks hd
    required_groups:    Optional[str] = None   # comma-separated; any-of
    auto_provision:     Optional[bool] = None  # allow new users when registration is closed
    client_secret_set:  bool = False


# ── Branding endpoints ────────────────────────────────────────────────────────

@router.get("/config", response_model=BrandingConfig)
def get_branding(
    system: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    # Public: the login page needs branding (name, colors, logo) before auth.
    # Branding is cosmetic and contains no secrets.
    s = load_settings()
    b = dict(s.get("branding", {}))

    # Per-system branding overlay if enabled by super admin
    try:
        from ..models.database import LibrarySystem, Branch
        sys_obj = None
        if current_user and getattr(current_user, "branch_id", None):
            branch = db.query(Branch).filter(Branch.id == current_user.branch_id).first()
            if branch and branch.system:
                sys_obj = branch.system
        elif system:
            sys_obj = db.query(LibrarySystem).filter(LibrarySystem.code == system.strip().lower()).first()

        if sys_obj and sys_obj.allow_custom_branding and sys_obj.branding_config:
            custom_b = json.loads(sys_obj.branding_config)
            if isinstance(custom_b, dict):
                for k, v in custom_b.items():
                    if v is not None and v != "":
                        b[k] = v
    except Exception:
        pass

    # Check if a logo file exists, in whichever format was last uploaded
    logo_url = "/api/branding/logo" if _logo_exists() else None
    return BrandingConfig(
        system_name=b.get("system_name", "OpenOptOut"),
        tagline=b.get("tagline"),
        primary_color=b.get("primary_color", "#6366f1"),
        accent_color=b.get("accent_color", "#4f46e5"),
        logo_url=logo_url,
        favicon_url=b.get("favicon_url"),
        contact_email=b.get("contact_email"),
        contact_phone=b.get("contact_phone"),
        support_url=b.get("support_url"),
        welcome_message=b.get("welcome_message"),
        email_footer=b.get("email_footer"),
        terms_url=b.get("terms_url"),
        show_powered_by=b.get("show_powered_by", True),
        show_staff_tab=b.get("show_staff_tab", True),
        show_patron_tab=b.get("show_patron_tab", False),
        staff_tab_label=b.get("staff_tab_label", "Staff"),
        patron_tab_label=b.get("patron_tab_label", "Library Card"),
        staff_welcome=b.get("staff_welcome"),
        patron_welcome=b.get("patron_welcome"),
    )


@router.patch("/config", response_model=BrandingConfig)
def save_branding(data: BrandingConfig, _: User = Depends(require_permission("branding.manage"))):
    s = load_settings()
    s["branding"] = data.model_dump(exclude={"logo_url"})
    _save(s)
    return data


@router.post("/logo")
def upload_logo(file: UploadFile = File(...), _: User = Depends(require_permission("branding.manage"))):
    # Was: ext always came out "png" for jpeg/webp uploads too (only svg was
    # distinguished), silently mislabeling those files while still leaving the
    # GET /logo and DELETE endpoints' now-unreachable jpeg/webp branches dead
    # code. Map every accepted content-type to its real extension instead.
    ext = _LOGO_EXTENSIONS.get(file.content_type)
    if not ext:
        raise HTTPException(400, "Logo must be PNG, SVG, JPEG, or WebP")
    # Clear any previously uploaded logo in a DIFFERENT format first — now that
    # jpeg/webp get their own real extension, an old file in another format
    # would otherwise linger on disk and get served ahead of the one just
    # uploaded (get_logo/_logo_exists check extensions in a fixed order).
    for other_ext in set(_LOGO_EXTENSIONS.values()) - {ext}:
        other_path = os.path.join(LOGO_PATH, f"logo.{other_ext}")
        if os.path.exists(other_path):
            os.remove(other_path)
    path = os.path.join(LOGO_PATH, f"logo.{ext}")
    with open(path, "wb") as f:
        f.write(file.file.read())
    return {"logo_url": f"/api/branding/logo?v={int(datetime.utcnow().timestamp())}"}


@router.get("/logo")
def get_logo():
    for ext in ("svg", "png", "jpeg", "webp"):
        path = os.path.join(LOGO_PATH, f"logo.{ext}")
        if os.path.exists(path):
            return FileResponse(path)
    raise HTTPException(404, "No logo uploaded")


@router.delete("/logo", status_code=204)
def delete_logo(_: User = Depends(require_permission("branding.manage"))):
    for ext in ("svg", "png", "jpeg", "webp"):
        path = os.path.join(LOGO_PATH, f"logo.{ext}")
        if os.path.exists(path):
            os.remove(path)


# ── Registration config ───────────────────────────────────────────────────────

@router.get("/registration", response_model=RegistrationConfig)
def get_registration(_: User = Depends(require_permission("users.registration"))):
    s = load_settings()
    r = s.get("registration", {})
    return RegistrationConfig(**{k: r.get(k, v) for k, v in RegistrationConfig().model_dump().items()})


@router.patch("/registration", response_model=RegistrationConfig)
def save_registration(data: RegistrationConfig, _: User = Depends(require_permission("users.registration"))):
    s = load_settings()
    s["registration"] = data.model_dump()
    _save(s)
    return data


# ── Announcement banner ───────────────────────────────────────────────────────

@router.get("/banner")
def get_banner(_: Optional[User] = Depends(get_current_user_optional)):
    # Public: shown on the login page too. Cosmetic, no secrets.
    s      = load_settings()
    banner = s.get("banner")
    if not banner or not banner.get("active"):
        return None
    if banner.get("expires_at"):
        try:
            if datetime.fromisoformat(banner["expires_at"]) < datetime.utcnow():
                return None
        except Exception:
            pass
    return banner


@router.put("/banner")
def set_banner(data: AnnouncementBanner, _: User = Depends(require_permission("branding.manage"))):
    s = load_settings()
    s["banner"] = data.model_dump()
    _save(s)
    return data


@router.delete("/banner", status_code=204)
def clear_banner(_: User = Depends(require_permission("branding.manage"))):
    s = load_settings()
    s.pop("banner", None)
    _save(s)


# ── Auth provider config ──────────────────────────────────────────────────────

def _ldap_mode(ldap_cfg: dict) -> str:
    from ..core.auth_providers import ldap_tls_mode
    return ldap_tls_mode(ldap_cfg)


@router.get("/auth-providers", response_model=AuthProviderConfig)
def get_auth_providers(user: Optional[User] = Depends(get_current_user_optional)):
    s   = load_settings()
    ap  = s.get("auth_providers", {})
    ldap = ap.get("ldap", {})
    sip2 = ap.get("sip2", {})

    # May the caller see sign-in configuration (super admin, or a manager with
    # the "Sign-in providers" permission)? Only they get the full config
    # (LDAP host/bind DN, OIDC client IDs). The login page calls this while
    # LOGGED OUT to know which SSO buttons to show, so we must answer publicly —
    # but a public caller gets ONLY enabled flags + provider labels, never the
    # sensitive infrastructure details.
    is_admin = bool(user and has_permission(user, "auth.providers"))

    oidc_providers = []
    for key, preset in OIDC_PRESETS.items():
        cfg = ap.get(key, {})
        entry = {
            "key":     key,
            "label":   preset.get("label", key),
            "enabled": cfg.get("enabled", False),
            "note":    preset.get("note", ""),
        }
        if is_admin:
            entry.update({
                "discovery_url":       cfg.get("discovery_url", preset.get("discovery_url","")),
                "client_id":           cfg.get("client_id",""),
                "client_secret_set":   bool(cfg.get("client_secret_enc")),
                "scope":               cfg.get("scope", preset.get("scope","openid email profile")),
                "default_role":        cfg.get("default_role","parent"),
                "tenant_id":           cfg.get("tenant_id",""),
                "allowed_domains":     cfg.get("allowed_domains",""),
                "required_groups":     cfg.get("required_groups",""),
                "auto_provision":      cfg.get("auto_provision", False),
            })
        oidc_providers.append(entry)

    if not is_admin:
        # Public view: only what the login page needs to render its buttons.
        return AuthProviderConfig(
            ldap_enabled=ldap.get("enabled", False),
        saml_enabled=bool(ap.get("saml", {}).get("enabled", False)),
        saml_label=ap.get("saml", {}).get("label") or "Single sign-on",
            sip2_enabled=sip2.get("enabled", False),
            oidc_providers=oidc_providers,
        )

    return AuthProviderConfig(
        ldap_enabled=ldap.get("enabled", False),
        saml_enabled=bool(ap.get("saml", {}).get("enabled", False)),
        saml_label=ap.get("saml", {}).get("label") or "Single sign-on",
        ldap_host=ldap.get("host"),
        ldap_base_dn=ldap.get("base_dn"),
        ldap_bind_dn=ldap.get("bind_dn"),
        ldap_user_attr=ldap.get("user_attr","sAMAccountName"),
        ldap_name_attr=ldap.get("name_attr","displayName"),
        ldap_email_attr=ldap.get("email_attr","mail"),
        ldap_use_tls=ldap.get("use_tls",True),
        ldap_tls_mode=_ldap_mode(ldap),
        ldap_port=ldap.get("port"),
        ldap_ca_cert_pem=ldap.get("ca_cert_pem", ""),
        ldap_email_domain=ldap.get("email_domain"),
        ldap_default_role=ldap.get("default_role","parent"),
        ldap_password_set=bool(ldap.get("bind_password_enc")),
        sip2_enabled=sip2.get("enabled",False),
        sip2_host=sip2.get("host"),
        sip2_port=sip2.get("port", 6443 if sip2.get("use_tls") else 6001),
        sip2_use_tls=sip2.get("use_tls", False),
        sip2_ca_cert_pem=sip2.get("ca_cert_pem", ""),
        sip2_ca_cert_path=sip2.get("ca_cert_path"),
        sip2_institution_id=sip2.get("institution_id"),
        sip2_ils_login=sip2.get("ils_login"),
        sip2_email_domain=sip2.get("email_domain","library.local"),
        sip2_default_role=sip2.get("default_role","parent"),
        sip2_password_set=bool(sip2.get("ils_password_enc")),
        sip2_timeout=sip2.get("timeout_seconds", 10),
        oidc_providers=oidc_providers,
    )


@router.patch("/auth-providers/ldap")
def save_ldap(data: dict, _: User = Depends(require_permission("auth.providers"))):
    s  = load_settings()
    ap = s.setdefault("auth_providers", {})
    cur = ap.get("ldap", {})
    pw = data.pop("bind_password", None)
    if "tls_mode" in data and data["tls_mode"] not in ("ldaps", "starttls", "none"):
        raise HTTPException(400, "tls_mode must be ldaps, starttls, or none")
    if data.get("port") in ("", None):
        data.pop("port", None)
    elif "port" in data:
        try:
            data["port"] = int(data["port"])
            assert 1 <= data["port"] <= 65535
        except Exception:
            raise HTTPException(400, "port must be a number between 1 and 65535")
    warnings = []
    if "ca_cert_pem" in data:
        pem = (data.get("ca_cert_pem") or "").strip()
        if pem:
            from ..core.auth_providers import classify_ca_pem
            try:
                verdict = classify_ca_pem(pem)
            except Exception:
                raise HTTPException(400, "CA certificate is not a valid PEM certificate.")
            if not verdict["certs"]:
                raise HTTPException(400, "No certificate found in the pasted text.")
            if verdict["errors"]:
                raise HTTPException(400, " ".join(verdict["errors"]))
            warnings = verdict["warnings"]
        data["ca_cert_pem"] = pem
    ap["ldap"] = {**cur, **data}
    if pw: ap["ldap"]["bind_password_enc"] = _encrypt(pw)
    _save(s); return {"saved": True, "warnings": warnings}


@router.patch("/auth-providers/sip2")
def save_sip2(data: dict, _: User = Depends(require_permission("auth.providers"))):
    s  = load_settings()
    ap = s.setdefault("auth_providers", {})
    cur = ap.get("sip2", {})
    pw = data.pop("ils_password", None)
    data.pop("verify_cert", None)          # verification is always on now
    warnings = []
    if "ca_cert_pem" in data:
        pem = (data.get("ca_cert_pem") or "").strip()
        if pem:
            from ..core.auth_providers import classify_ca_pem
            try:
                verdict = classify_ca_pem(pem)
            except Exception:
                raise HTTPException(400, "CA certificate is not a valid PEM certificate.")
            if not verdict["certs"]:
                raise HTTPException(400, "No certificate found in the pasted text.")
            if verdict["errors"]:
                raise HTTPException(400, " ".join(verdict["errors"]))
            warnings = verdict["warnings"]
        data["ca_cert_pem"] = pem
    ap["sip2"] = {**cur, **data}
    if pw: ap["sip2"]["ils_password_enc"] = _encrypt(pw)
    # Auto-update default port when TLS mode changes
    if "use_tls" in data and "port" not in data:
        if data["use_tls"] and cur.get("port", 6001) == 6001:
            ap["sip2"]["port"] = 6443
        elif not data["use_tls"] and cur.get("port", 6443) == 6443:
            ap["sip2"]["port"] = 6001
    ap["sip2"].pop("verify_cert", None)
    _save(s); return {"saved": True, "warnings": warnings}


@router.put("/auth-providers/oidc/{provider_key}")
def save_oidc_provider(
    provider_key: str,
    data: OIDCProviderConfig,
    _: User = Depends(require_permission("auth.providers")),
):
    s  = load_settings()
    ap = s.setdefault("auth_providers", {})
    cur = ap.get(provider_key, {})
    secret = data.client_secret

    # Handle Microsoft tenant_id substitution in discovery URL
    disc = data.discovery_url or ""
    if data.tenant_id:
        disc = disc.replace("{tenant_id}", data.tenant_id)

    ap[provider_key] = {
        **cur,
        "enabled":       data.enabled,
        "discovery_url": disc,
        "client_id":     data.client_id,
        "scope":         data.scope,
        "default_role":  data.default_role,
        "allowed_domains": (data.allowed_domains or "").strip(),
        "required_groups": (data.required_groups or "").strip(),
    }
    if data.auto_provision is not None:
        ap[provider_key]["auto_provision"] = bool(data.auto_provision)
    if data.tenant_id:
        ap[provider_key]["tenant_id"] = data.tenant_id
    if secret:
        ap[provider_key]["client_secret_enc"] = _encrypt(secret)

    _save(s); return {"saved": True}


@router.post("/auth-providers/ldap/test")
def test_ldap(_: User = Depends(require_permission("auth.providers"))):
    """Test LDAP connectivity + service-account bind with the stored settings,
    using exactly the same TLS/verification path as real logins."""
    from ..core.auth_providers import (get_provider_config, decrypt_password,
                                       ldap_connect, ldap_tls_mode, ldap_uri, ldap_tls_hint)
    cfg = get_provider_config("ldap")
    info = {"uri": ldap_uri(cfg), "tls_mode": ldap_tls_mode(cfg)}
    conn = None
    try:
        conn = ldap_connect(cfg)
        conn.simple_bind_s(cfg.get("bind_dn", ""), decrypt_password(cfg.get("bind_password_enc", "")))
        from ..core.auth_providers import ldap_cert_status
        info["certificate"] = ldap_cert_status(cfg)
        return {"connected": True, **info,
                "warning": ("Unencrypted: staff passwords cross the network in clear text."
                            if info["tls_mode"] == "none" else None)}
    except Exception as e:
        from ..core.auth_providers import ldap_diagnose
        return {"connected": False, **info, "error": ldap_diagnose(cfg) or ldap_tls_hint(e)}
    finally:
        if conn is not None:
            try: conn.unbind_s()
            except Exception: pass


@router.get("/auth-providers/ldap/cert-status")
def ldap_cert_status_stored(_: User = Depends(require_permission("auth.providers"))):
    """Most recent stored certificate check (daily job), for the dashboard."""
    from ..core.auth_providers import get_provider_config
    cfg = get_provider_config("ldap")
    if not cfg.get("enabled"):
        return {"level": "disabled"}
    from ..core.cert_monitor import load_state
    return (load_state().get("results") or {}).get("ldap") or cfg.get("cert_status") \
        or {"level": "unchecked"}


@router.post("/auth-providers/ldap/cert-check")
def ldap_cert_check_now(_: User = Depends(require_permission("auth.providers"))):
    from ..core.auth_providers import run_ldap_cert_check
    return run_ldap_cert_check()


@router.get("/auth-providers/sip2/presets")
def sip2_presets(_: User = Depends(require_permission("auth.providers"))):
    from ..core.auth_providers import SIP2_ILS_PRESETS
    return SIP2_ILS_PRESETS


@router.post("/auth-providers/sip2/test")
def test_sip2(_: User = Depends(require_permission("auth.providers"))):
    """Test SIP2 / SIP2-over-TLS connectivity with the same verification as logins."""
    from ..core.auth_providers import (get_provider_config, sip2_endpoint, tls_diagnose,
                                       sip2_cert_status)
    import socket as _socket
    cfg = get_provider_config("sip2")
    host, port, use_tls = sip2_endpoint(cfg)
    timeout = int(cfg.get("timeout_seconds", 10))
    info = {"host": host, "port": port, "tls": use_tls}
    if cfg.get("verify_cert") is False:
        info["note"] = ("Certificate verification is now always on. If this test fails "
                        "with a trust error, paste the ILS's CA certificate.")
    if use_tls:
        problem = tls_diagnose(host, port, (cfg.get("ca_cert_pem") or "").strip(),
                               cfg.get("ca_cert_path") or "", timeout, service="ILS")
        if problem:
            return {"connected": False, **info, "error": problem}
        return {"connected": True, **info, "certificate": sip2_cert_status(cfg)}
    try:
        _socket.create_connection((host, port), timeout=timeout).close()
        return {"connected": True, **info,
                "warning": "Unencrypted: card numbers and PINs cross the network in clear text."}
    except OSError:
        return {"connected": False, **info,
                "error": f"Cannot reach {host}:{port}. Check the host, port, and firewall."}
