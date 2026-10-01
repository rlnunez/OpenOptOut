"""
Settings router — appearance, email config (with 6 presets), scheduler, data export.
Credentials encrypted at rest with Fernet derived from SECRET_KEY.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import json, os, base64
from cryptography.fernet import Fernet

from ..models.database import get_db, User
from ..core.auth import get_current_user, require_super_admin
from ..core.access import require_permission
from ..core.settings_store import load_settings, SETTINGS_FILE

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ── Encryption ────────────────────────────────────────────────────────────────

def _fernet() -> Fernet:
    raw    = os.getenv("SECRET_KEY", "change-me-in-production-use-a-long-random-string")
    padded = (raw * 4)[:32].encode()
    return Fernet(base64.urlsafe_b64encode(padded))

def _encrypt(v: str) -> str:
    return _fernet().encrypt(v.encode()).decode()

def _decrypt(v: str) -> str:
    try:
        return _fernet().decrypt(v.encode()).decode()
    except Exception:
        return ""

def _save(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Email presets ─────────────────────────────────────────────────────────────

PRESETS = {
    "gmail": {
        "imap_host": "imap.gmail.com",       "imap_port": 993, "imap_ssl": True,
        "smtp_host": "smtp.gmail.com",       "smtp_port": 587, "smtp_tls": True,
        "note": "For highest security, connect via OAuth above. If using SMTP, use a Gmail App Password — not your account password. Enable 2-Step Verification first, then visit myaccount.google.com/apppasswords and create an App Password for 'Mail'.",
    },
    "outlook": {
        "imap_host": "outlook.office365.com","imap_port": 993, "imap_ssl": True,
        "smtp_host": "smtp.office365.com",   "smtp_port": 587, "smtp_tls": True,
        "note": "For highest security, connect via OAuth above. If using SMTP, works with Outlook.com, Hotmail, and Microsoft 365. If you have 2FA enabled, create an App Password at account.microsoft.com/security.",
    },
    "yahoo": {
        "imap_host": "imap.mail.yahoo.com",  "imap_port": 993, "imap_ssl": True,
        "smtp_host": "smtp.mail.yahoo.com",  "smtp_port": 587, "smtp_tls": True,
        "note": "Yahoo requires an App Password. Go to myaccount.yahoo.com → Security → Generate app password. Select 'Other app' and name it OpenOptOut.",
    },
    "fastmail": {
        "imap_host": "imap.fastmail.com",    "imap_port": 993, "imap_ssl": True,
        "smtp_host": "smtp.fastmail.com",    "smtp_port": 587, "smtp_tls": True,
        "note": "Use a Fastmail App Password from Settings → Privacy & Security → App Passwords. Fastmail is a great privacy-respecting choice for this inbox.",
    },
    "protonmail": {
        "imap_host": "127.0.0.1",            "imap_port": 1143,"imap_ssl": False,
        "smtp_host": "127.0.0.1",            "smtp_port": 1025,"smtp_tls": False,
        "note": "Requires Proton Mail Bridge running on the same machine or Docker network. Bridge exposes a local IMAP/SMTP server. See proton.me/mail/bridge for setup.",
    },
    "custom": {
        "note": "Enter your IMAP and SMTP server details manually.",
    },
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class AppearanceSettings(BaseModel):
    app_name:     Optional[str]   = "OpenOptOut"
    app_icon_url: Optional[str]   = None
    theme:        Optional[str]   = "dark"
    accent_color: Optional[str]   = "#6366f1"


class EmailGracePeriodOut(BaseModel):
    active: bool = False
    days_remaining: int = 0
    grace_period_days: int = 60
    transition_started_at: Optional[str] = None
    expires_at: Optional[str] = None
    previous_inbox: Optional[str] = None
    previous_mode: Optional[str] = None


class EmailConfig(BaseModel):
    mode:                 Optional[str] = None   # "shared" | "per_user"
    preset:               Optional[str] = None
    imap_host:            Optional[str] = None
    imap_port:            Optional[int] = 993
    imap_user:            Optional[str] = None
    imap_password:        Optional[str] = None   # write-only
    imap_ssl:             Optional[bool]= True
    imap_folder:          Optional[str] = "INBOX"
    poll_interval_minutes:Optional[int] = 15
    smtp_host:            Optional[str] = None
    smtp_port:            Optional[int] = 587
    smtp_user:            Optional[str] = None
    smtp_password:        Optional[str] = None   # write-only
    smtp_tls:             Optional[bool]= True
    from_name:            Optional[str] = "OpenOptOut Removals"
    from_email:           Optional[str] = None


class EmailConfigOut(BaseModel):
    mode:                 Optional[str] = "shared"
    preset:               Optional[str]
    provider:             Optional[str] = None    # '' | 'smtp' | 'gmail' | 'outlook' | ... (set via the wizard or an uploaded provider plugin)
    provider_connected:   bool = False             # an OAuth token actually exists for `provider` (account_ref 'default')
    imap_host:            Optional[str]
    imap_port:            Optional[int]
    imap_user:            Optional[str]
    imap_password_set:    bool
    imap_ssl:             Optional[bool]
    imap_folder:          Optional[str]
    poll_interval_minutes:Optional[int]
    smtp_host:            Optional[str]
    smtp_port:            Optional[int]
    smtp_user:            Optional[str]
    smtp_password_set:    bool
    smtp_tls:             Optional[bool]
    from_name:            Optional[str]
    from_email:           Optional[str]
    connected:            bool
    grace_period:         Optional[EmailGracePeriodOut] = None


class SchedulerConfig(BaseModel):
    enabled:               Optional[bool] = False
    run_time:              Optional[str]  = "02:00"
    timezone:              Optional[str]  = "America/Chicago"
    max_optouts_per_day:   Optional[int]  = 20
    recheck_interval_days: Optional[int]  = 90
    auto_recheck:          Optional[bool] = True
    pause_before_send:     Optional[bool] = True
    # Order in which throttled brokers are dispatched each day:
    #   "priority" (default) — highest broker priority (1..5) first
    #   "fifo"           — oldest pending first
    #   "easy_first"     — easiest brokers first (quick wins)
    dispatch_order:        Optional[str]  = "priority"
    # ── Job spread configuration ──
    # spread_mode: burst | window | rate | distributed
    spread_mode:                Optional[str] = "burst"
    # window mode
    window_start_hour:          Optional[int] = 22
    window_end_hour:            Optional[int] = 6
    window_interval_minutes:    Optional[int] = 30
    # rate mode
    rate_per_hour:              Optional[int] = 5
    rate_interval_minutes:      Optional[int] = 20
    # distributed mode
    distributed_interval_minutes: Optional[int] = 60


class PrivacyDataSettings(BaseModel):
    auto_purge_logs_days: Optional[int] = 365


class AllSettings(BaseModel):
    appearance: AppearanceSettings
    email:      EmailConfigOut
    scheduler:  SchedulerConfig
    privacy:    PrivacyDataSettings


# ── Read all ──────────────────────────────────────────────────────────────────

@router.get("", response_model=AllSettings)
def get_settings(_: User = Depends(get_current_user)):
    s   = load_settings()
    e   = s.get("email", {})
    sch = s.get("scheduler", {})

    # The setup wizard (routers/wizard.py EmailStep) and this page have grown
    # slightly different field names for the same shared-inbox account over
    # time — the wizard writes smtp_username/(no imap_* fields at all, since it
    # treats one login as good for both SMTP and IMAP), this page writes
    # imap_user/smtp_user separately. Read every name a value could be under so
    # data saved by EITHER UI shows up correctly in both, rather than only
    # ever reflecting whichever one wrote it last.
    imap_user = e.get("imap_user") or e.get("smtp_username") or e.get("smtp_user")
    imap_pw_set = bool(e.get("imap_password_enc") or e.get("smtp_password_enc"))
    smtp_user = e.get("smtp_user") or e.get("smtp_username")
    smtp_pw_set = bool(e.get("smtp_password_enc"))
    from_email = e.get("from_email") or e.get("from_address")

    provider = e.get("provider", "") or ""
    # account_ref 'default' is the shared/admin account's ref throughout the
    # OAuth connect flow (ConnectOAuth's default in the wizard and Settings).
    provider_connected = bool(provider and provider != "smtp"
                              and s.get("email_credentials", {}).get("default"))
    # SMTP is "connected" once it can actually send — IMAP (for reading
    # confirmations back) is checked too when host is set, but its absence
    # alone shouldn't block sending outgoing opt-outs from ever showing as configured.
    smtp_ready = bool(e.get("smtp_host") and smtp_user and smtp_pw_set)

    from ..core.email_grace import get_email_grace_status
    grace_stat = get_email_grace_status(s)
    grace_out = EmailGracePeriodOut(
        active=grace_stat.get("active", False),
        days_remaining=grace_stat.get("days_remaining", 0),
        grace_period_days=grace_stat.get("grace_period_days", 60),
        transition_started_at=grace_stat.get("transition_started_at"),
        expires_at=grace_stat.get("expires_at"),
        previous_inbox=grace_stat.get("previous_inbox"),
        previous_mode=grace_stat.get("previous_mode"),
    )

    return AllSettings(
        appearance=AppearanceSettings(**s.get("appearance", {})),
        email=EmailConfigOut(
            mode=e.get("mode", "shared"),
            preset=e.get("preset"),
            provider=provider or None,
            provider_connected=provider_connected,
            imap_host=e.get("imap_host"),             imap_port=e.get("imap_port", 993),
            imap_user=imap_user,                      imap_password_set=imap_pw_set,
            imap_ssl=e.get("imap_ssl", True),         imap_folder=e.get("imap_folder", "INBOX"),
            poll_interval_minutes=e.get("poll_interval_minutes", 15),
            smtp_host=e.get("smtp_host"),             smtp_port=e.get("smtp_port", 587),
            smtp_user=smtp_user,                      smtp_password_set=smtp_pw_set,
            smtp_tls=e.get("smtp_tls", True),
            from_name=e.get("from_name", "OpenOptOut Removals"),
            from_email=from_email,
            connected=provider_connected or smtp_ready,
            grace_period=grace_out,
        ),
        scheduler=SchedulerConfig(**{k: sch.get(k, v) for k, v in SchedulerConfig().model_dump().items()}),
        privacy=PrivacyDataSettings(**s.get("privacy", {})),
    )


# ── Appearance ────────────────────────────────────────────────────────────────

@router.patch("/appearance")
def save_appearance(data: AppearanceSettings, _: User = Depends(require_permission("branding.manage"))):
    s = load_settings(); s["appearance"] = data.model_dump(); _save(s)
    return s["appearance"]


# ── Email ─────────────────────────────────────────────────────────────────────

@router.get("/email/presets")
def get_presets(_: User = Depends(require_permission("email.manage"))):
    return PRESETS


@router.patch("/email")
def save_email(data: EmailConfig, _: User = Depends(require_permission("email.manage"))):
    s = load_settings(); cur = s.get("email", {})

    # Trigger mode-switching grace period snapshot if changing mode or mailbox
    from ..core.email_grace import maybe_snapshot_grace_period
    maybe_snapshot_grace_period(
        current_settings=s,
        new_email_config=data.model_dump(),
        new_mode=data.mode or cur.get("mode", "shared"),
    )

    # apply preset host/port defaults if preset selected (don't overwrite manual values)
    if data.preset and data.preset in PRESETS and data.preset != "custom":
        p = PRESETS[data.preset]
        for k in ("imap_host","imap_port","imap_ssl","smtp_host","smtp_port","smtp_tls"):
            if k in p and not getattr(data, k, None):
                setattr(data, k, p[k])

    s["email"] = {
        "mode":                 data.mode or cur.get("mode", "shared"),
        "preset":               data.preset or cur.get("preset"),
        "imap_host":            data.imap_host  or cur.get("imap_host"),
        "imap_port":            data.imap_port,
        "imap_user":            data.imap_user  or cur.get("imap_user"),
        "imap_password_enc":    _encrypt(data.imap_password) if data.imap_password else cur.get("imap_password_enc"),
        "imap_ssl":             data.imap_ssl,
        "imap_folder":          data.imap_folder,
        "poll_interval_minutes":data.poll_interval_minutes,
        "smtp_host":            data.smtp_host  or cur.get("smtp_host"),
        "smtp_port":            data.smtp_port,
        "smtp_user":            data.smtp_user  or cur.get("smtp_user"),
        "smtp_password_enc":    _encrypt(data.smtp_password) if data.smtp_password else cur.get("smtp_password_enc"),
        "smtp_tls":             data.smtp_tls,
        "from_name":            data.from_name,
        "from_email":           data.from_email or cur.get("from_email"),
    }
    _save(s)
    return {"saved": True}


@router.get("/email/grace-period", response_model=EmailGracePeriodOut)
def get_grace_period(_: User = Depends(get_current_user)):
    from ..core.email_grace import get_email_grace_status
    s = load_settings()
    stat = get_email_grace_status(s)
    return EmailGracePeriodOut(
        active=stat.get("active", False),
        days_remaining=stat.get("days_remaining", 0),
        grace_period_days=stat.get("grace_period_days", 60),
        transition_started_at=stat.get("transition_started_at"),
        expires_at=stat.get("expires_at"),
        previous_inbox=stat.get("previous_inbox"),
        previous_mode=stat.get("previous_mode"),
    )


@router.post("/email/grace-period/dismiss")
def dismiss_grace_period(_: User = Depends(require_permission("email.manage"))):
    from ..core.email_grace import dismiss_email_grace_period
    s = load_settings()
    ok = dismiss_email_grace_period(s)
    if ok:
        _save(s)
    return {"dismissed": ok}


@router.post("/email/grace-period/extend")
def extend_grace_period(extra_days: int = 30, _: User = Depends(require_permission("email.manage"))):
    from ..core.email_grace import extend_email_grace_period
    s = load_settings()
    new_days = extend_email_grace_period(s, extra_days=extra_days)
    if new_days > 0:
        _save(s)
    return {"extended": True, "total_days": new_days}


@router.post("/email/test")
def test_connection(_: User = Depends(require_permission("email.manage"))):
    import imaplib, smtplib, ssl as ssl_module
    s   = load_settings(); e = s.get("email", {})
    res = {"imap": False, "smtp": False, "errors": []}

    from ..core.memory_hygiene import ephemeral_secret
    try:
        if not e.get("imap_password_enc"): raise ValueError("No IMAP password saved")
        if e.get("imap_ssl", True):
            c = imaplib.IMAP4_SSL(e["imap_host"], e.get("imap_port", 993))
        else:
            c = imaplib.IMAP4(e["imap_host"], e.get("imap_port", 143))
        with ephemeral_secret(e.get("imap_password_enc")) as pw:
            c.login(e["imap_user"], pw)
        c.logout()
        res["imap"] = True
    except Exception as ex:
        res["errors"].append(f"IMAP: {ex}")

    try:
        if not e.get("smtp_password_enc"): raise ValueError("No SMTP password saved")
        ctx = ssl_module.create_default_context()
        ctx.minimum_version = ssl_module.TLSVersion.TLSv1_2
        with smtplib.SMTP(e["smtp_host"], e.get("smtp_port", 587)) as sc:
            if e.get("smtp_tls", True): sc.starttls(context=ctx)
            with ephemeral_secret(e.get("smtp_password_enc")) as pw:
                sc.login(e["smtp_user"], pw)
        res["smtp"] = True
    except Exception as ex:
        res["errors"].append(f"SMTP: {ex}")

    res["connected"] = res["imap"] and res["smtp"]
    return res


# ── Scheduler ─────────────────────────────────────────────────────────────────

@router.patch("/scheduler")
def save_scheduler(data: SchedulerConfig, _: User = Depends(require_permission("scheduler.manage"))):
    s = load_settings(); s["scheduler"] = data.model_dump(); _save(s)
    # reload live scheduler to pick up changes
    from ..core.scheduler import reload_scheduler
    import threading
    threading.Thread(target=reload_scheduler, daemon=True).start()
    return s["scheduler"]


# ── Privacy / export / danger ─────────────────────────────────────────────────

@router.patch("/privacy")
def save_privacy(data: PrivacyDataSettings, _: User = Depends(require_permission("settings.system"))):
    s = load_settings(); s["privacy"] = data.model_dump(); _save(s)
    return s["privacy"]


@router.get("/export")
def export_data(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..models.database import FamilyMember
    from ..core.auth import get_accessible_member_ids
    ids     = get_accessible_member_ids(db, current_user)
    members = db.query(FamilyMember).filter(FamilyMember.id.in_(ids)).all()
    out = [{
        "full_name":  m.full_name, "age": m.age,
        "identities": [{"kind": i.kind, "value": i.value, "is_primary": i.is_primary} for i in m.identities],
        "removal_requests": [{
            "broker":       r.broker.name, "status": r.status,
            "sent_at":      r.sent_at.isoformat()      if r.sent_at      else None,
            "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
            "recheck_after":r.recheck_after.isoformat()if r.recheck_after else None,
        } for r in m.requests],
    } for m in members]
    return JSONResponse(
        content={"exported_at": datetime.utcnow().isoformat(), "members": out},
        headers={"Content-Disposition": "attachment; filename=openoptout_export.json"},
    )


@router.delete("/danger/reset-requests", status_code=204)
def reset_requests(_: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    from ..models.database import RemovalRequest, EmailLog
    db.query(EmailLog).delete(); db.query(RemovalRequest).delete(); db.commit()


from datetime import datetime


# ── Vault limits ──────────────────────────────────────────────────────────────

class VaultLimits(BaseModel):
    max_names:               int = 4
    max_addresses:           int = 10
    max_phones:              int = 5
    max_emails:              int = 5
    max_children_per_parent: int = 0   # 0 = unlimited


@router.get("/vault-limits", response_model=VaultLimits)
def get_vault_limits(_: User = Depends(get_current_user)):
    """
    Readable by all authenticated users so the frontend can enforce
    limits without a second admin-only request.
    """
    s = load_settings()
    v = s.get("vault_limits", {})
    return VaultLimits(
        max_names=v.get("max_names", 4),
        max_addresses=v.get("max_addresses", 10),
        max_phones=v.get("max_phones", 5),
        max_emails=v.get("max_emails", 5),
        max_children_per_parent=v.get("max_children_per_parent", 0),
    )


@router.patch("/vault-limits", response_model=VaultLimits)
def save_vault_limits(
    data: VaultLimits,
    _: User = Depends(require_permission("settings.system")),
):
    # Sanity caps — prevent absurd values that would generate millions of combos
    if data.max_names               > 20:  raise HTTPException(400, "max_names cannot exceed 20")
    if data.max_addresses           > 30:  raise HTTPException(400, "max_addresses cannot exceed 30")
    if data.max_phones              > 20:  raise HTTPException(400, "max_phones cannot exceed 20")
    if data.max_emails              > 20:  raise HTTPException(400, "max_emails cannot exceed 20")
    if data.max_children_per_parent < 0:   raise HTTPException(400, "max_children_per_parent cannot be negative")

    s = load_settings()
    s["vault_limits"] = data.model_dump()
    _save(s)
    return data


# ── Encryption status ─────────────────────────────────────────────────────────

@router.get("/encryption-status")
def encryption_status(_: User = Depends(require_permission("database.view"))):
    """Return current encryption configuration and status."""
    from ..core.encryption import get_db_encryption_key, get_field_encryption_key
    import os

    db_key_set    = bool(get_db_encryption_key())
    field_key_set = bool(get_field_encryption_key())

    # Check if sqlcipher3 is available
    try:
        import sqlcipher3
        sqlcipher_available = True
    except ImportError:
        sqlcipher_available = False

    db_url = os.getenv("DATABASE_URL", "sqlite:///./privacy_pipeline.db")

    return {
        "sqlcipher_available":    sqlcipher_available,
        "db_encryption_enabled":  db_key_set and sqlcipher_available and db_url.startswith("sqlite"),
        "field_encryption_enabled": field_key_set,
        "db_key_env_set":         bool(os.getenv("DB_ENCRYPTION_KEY")),
        "field_key_env_set":      bool(os.getenv("FIELD_ENCRYPTION_KEY")),
        "secret_key_set":         os.getenv("SECRET_KEY","change-me") != "change-me-in-production-use-a-long-random-string",
        "db_type":                "sqlite" if db_url.startswith("sqlite") else "postgres",
        "notes": {
            "db_migration":   "Run: docker exec openoptout-api python -m backend.core.encryption migrate",
            "key_setup":      "Set DB_ENCRYPTION_KEY and FIELD_ENCRYPTION_KEY in your .env file",
            "postgres":       "For Postgres, use pgcrypto extension or provider-level TDE (RDS, Azure, Cloud SQL)",
        }
    }


# ── Automation (user-agent rotation, bot evasion) ─────────────────────────────

class AutomationConfig(BaseModel):
    rotate_user_agents:   bool = True
    custom_user_agents:   list[str] = []
    inter_submission_delay_seconds: float = 1.5


@router.get("/automation", response_model=AutomationConfig)
def get_automation(_: User = Depends(get_current_user)):
    s = load_settings()
    a = s.get("automation", {})
    return AutomationConfig(
        rotate_user_agents=a.get("rotate_user_agents", True),
        custom_user_agents=a.get("custom_user_agents", []),
        inter_submission_delay_seconds=a.get("inter_submission_delay_seconds", 1.5),
    )


@router.patch("/automation", response_model=AutomationConfig)
def save_automation(data: AutomationConfig, _: User = Depends(require_permission("settings.system"))):
    # Sanity: cap delay to reasonable bounds
    if data.inter_submission_delay_seconds < 0.5:
        data.inter_submission_delay_seconds = 0.5
    if data.inter_submission_delay_seconds > 30:
        data.inter_submission_delay_seconds = 30
    # Clean custom UAs — strip blanks
    data.custom_user_agents = [ua.strip() for ua in data.custom_user_agents if ua and ua.strip()]

    s = load_settings()
    s["automation"] = data.model_dump()
    _save(s)
    return data


@router.get("/automation/builtin-agents")
def list_builtin_agents(_: User = Depends(require_permission("settings.system"))):
    """Return the built-in user-agent pool for display."""
    from ..core.user_agents import BUILTIN_AGENTS
    return [{"ua": a["ua"], "platform": a["platform"]} for a in BUILTIN_AGENTS]


# ── Proxy / IP masking ────────────────────────────────────────────────────────

class ProxyConfig(BaseModel):
    enabled:   bool = False
    mode:      str  = "single"      # single | pool
    provider:  str  = "generic"     # generic | brightdata | oxylabs | smartproxy | iproyal
    scheme:    Optional[str] = "http"   # http | https | socks5
    host:      Optional[str] = None
    port:      Optional[int] = None


@router.get("/proxy")
def get_proxy(_: User = Depends(require_permission("settings.system"))):
    """Return proxy config (non-secret) + resolved status."""
    from ..core.proxy import get_proxy_status, PROXY_PRESETS
    s = load_settings()
    cfg = s.get("proxy", {})
    return {
        "config": {
            "enabled":  cfg.get("enabled", False),
            "mode":     cfg.get("mode", "single"),
            "provider": cfg.get("provider", "generic"),
            "scheme":   cfg.get("scheme", "http"),
            "host":     cfg.get("host"),
            "port":     cfg.get("port"),
        },
        "status":   get_proxy_status(),
        "presets":  PROXY_PRESETS,
    }


@router.patch("/proxy")
def save_proxy(data: ProxyConfig, _: User = Depends(require_permission("settings.system"))):
    """
    Save non-secret proxy config. Credentials are NEVER accepted here —
    they come from environment variables or mounted files only.
    """
    s = load_settings()
    s["proxy"] = data.model_dump()
    _save(s)
    # Clear the pool cache so changes take effect immediately
    from ..core.proxy import clear_pool_cache
    clear_pool_cache()
    return {"saved": True,
            "note": "Proxy config saved. Ensure credentials are set via environment "
                    "variables or mounted files. Use 'Test proxy' to verify."}


@router.post("/proxy/test")
def test_proxy_endpoint(_: User = Depends(require_permission("settings.system"))):
    """Test the configured proxy and report the exit IP."""
    from ..core.proxy import test_proxy
    from playwright.async_api import async_playwright
    import asyncio

    async def _run():
        async with async_playwright() as p:
            return await test_proxy(p)

    try:
        return asyncio.run(_run())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Plugin system settings ────────────────────────────────────────────────────

class PluginSystemConfig(BaseModel):
    enabled:       bool = False
    storage_mode:  str  = "db"        # "db" | "file"
    plugins_dir:   Optional[str] = "/data/plugins"
    denied:        bool = False       # master kill-switch (overrides enabled)
    lockdown_mode: bool = False       # any single violation disables the plugin


@router.get("/plugins", response_model=PluginSystemConfig)
def get_plugin_settings(_: User = Depends(require_super_admin)):
    s = load_settings()
    p = s.get("plugins", {})
    return PluginSystemConfig(
        enabled=p.get("enabled", False),
        storage_mode=p.get("storage_mode", "db"),
        plugins_dir=p.get("plugins_dir", "/data/plugins"),
        denied=p.get("denied", False),
        lockdown_mode=p.get("lockdown_mode", False),
    )


@router.patch("/plugins", response_model=PluginSystemConfig)
def save_plugin_settings(data: PluginSystemConfig, _: User = Depends(require_super_admin)):
    if data.storage_mode not in ("db", "file"):
        raise HTTPException(400, "storage_mode must be 'db' or 'file'")
    s = load_settings()
    prev = s.get("plugins", {})
    s["plugins"] = data.model_dump()
    _save(s)

    # Enforce the master kill-switch immediately: if the system is now denied
    # (or disabled), stop every running plugin right away.
    try:
        from ..plugins.manager import get_manager
        mgr = get_manager()
        if mgr and (data.denied or not data.enabled):
            mgr.deny_all()
    except Exception:
        pass
    return data


class PluginDenyRequest(BaseModel):
    # Typed confirmation guards against accidental toggles.
    confirm: bool = False


@router.post("/plugins/deny")
def deny_plugin_system(_: User = Depends(require_super_admin)):
    """
    Master kill-switch: immediately stop all running plugins and mark the
    plugin system denied so nothing can run until explicitly re-allowed.
    """
    s = load_settings()
    p = s.setdefault("plugins", {})
    p["denied"] = True
    p["enabled"] = False
    _save(s)
    try:
        from ..plugins.manager import get_manager
        mgr = get_manager()
        if mgr:
            mgr.deny_all()
    except Exception:
        pass
    return {"denied": True, "message": "Plugin system denied. All plugins stopped."}


@router.post("/plugins/allow")
def allow_plugin_system(req: PluginDenyRequest, _: User = Depends(require_super_admin)):
    """
    Lift the deny state. Requires explicit confirmation. Does NOT auto-enable
    the system or re-launch plugins — the admin must enable the system and each
    plugin deliberately afterward.
    """
    if not req.confirm:
        raise HTTPException(400, "Re-allowing the plugin system requires confirm=true")
    s = load_settings()
    p = s.setdefault("plugins", {})
    p["denied"] = False
    _save(s)
    return {"denied": False,
            "message": "Plugin system deny lifted. Enable the system and plugins deliberately to resume."}

