"""
Settings router — appearance, email config (with 6 presets), scheduler, data export.
Credentials encrypted at rest with Fernet derived from SECRET_KEY.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import json, os, base64, logging
from cryptography.fernet import Fernet

from ..core.limits import LimitedModel, ICON_DATA_URL_MAX, ITEMS_MAX
from ..models.database import get_db, User
from ..core.auth import get_current_user, require_super_admin
from ..core.access import require_permission
from ..core.settings_store import load_settings, save_settings, SETTINGS_FILE, get_secret_key, is_valid_secret_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


# ── Encryption ────────────────────────────────────────────────────────────────

def _fernet() -> Fernet:
    raw    = get_secret_key()
    # Repeat the key until it fills 32 bytes. Identical to the old
    # `(raw * 4)[:32]` for keys of 8+ chars (existing data still decrypts),
    # but no longer crashes on a shorter SECRET_KEY.
    _kb = raw.encode() or b"\0"
    padded = (_kb * (32 // len(_kb) + 1))[:32]
    return Fernet(base64.urlsafe_b64encode(padded))

def _encrypt(v: str) -> str:
    return _fernet().encrypt(v.encode()).decode()

def _decrypt(v: str) -> str:
    try:
        return _fernet().decrypt(v.encode()).decode()
    except Exception:
        return ""

def _save(data: dict):
    save_settings(data)


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

class AppearanceSettings(LimitedModel):
    app_name:     Optional[str]   = "OpenOptOut"
    app_icon_url: Optional[str] = Field(None, max_length=ICON_DATA_URL_MAX)
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


class EmailConfig(LimitedModel):
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
    preset:               Optional[str] = None
    provider:             Optional[str] = None    # '' | 'smtp' | 'gmail' | 'outlook' | ... (set via the wizard or an uploaded provider plugin)
    provider_connected:   bool = False             # an OAuth token actually exists for `provider` (account_ref 'default')
    imap_host:            Optional[str] = None
    imap_port:            Optional[int] = None
    imap_user:            Optional[str] = None
    imap_password_set:    bool = False
    imap_ssl:             Optional[bool] = None
    imap_folder:          Optional[str] = None
    poll_interval_minutes:Optional[int] = None
    smtp_host:            Optional[str] = None
    smtp_port:            Optional[int] = None
    smtp_user:            Optional[str] = None
    smtp_password_set:    bool = False
    smtp_tls:             Optional[bool] = None
    from_name:            Optional[str] = None
    from_email:           Optional[str] = None
    connected:            bool = False
    grace_period:         Optional[EmailGracePeriodOut] = None


class SchedulerConfig(LimitedModel):
    enabled:               Optional[bool] = False
    run_time:              Optional[str]  = "02:00"
    timezone:              Optional[str]  = "America/Chicago"
    max_optouts_per_day:   Optional[int]  = 20
    recheck_interval_days: Optional[int]  = 90
    auto_recheck:          Optional[bool] = True
    pause_before_send:     Optional[bool] = True
    # Order in which throttled brokers are dispatched each day:
    #   "aggregators_first" (default) — brokers that feed others first
    #   "priority"       — highest broker priority (1..5) first
    #   "fifo"           — oldest pending first
    #   "easy_first"     — easiest brokers first (quick wins)
    dispatch_order:        Optional[str]  = "aggregators_first"
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
    # Calendar: which weekdays opt-outs go out (0 = Monday … 6 = Sunday; empty
    # or missing = every day) and dates to skip, like holidays ("YYYY-MM-DD").
    run_days: Optional[List[int]] = Field(None, max_length=7)
    skip_dates: Optional[List[str]] = Field(None, max_length=ITEMS_MAX)
    # Scheduled downtime / maintenance windows (pauses background tasks)
    maintenance_windows: Optional[List[dict]] = Field(None, max_length=ITEMS_MAX)
    maintenance_notice_hours: Optional[int] = Field(24, ge=0, le=720, description="Hours in advance to show scheduled downtime banner to users; 0 = disabled")



class PrivacyDataSettings(LimitedModel):
    auto_purge_logs_days:          Optional[int]  = 365
    logs_retention_days:           Optional[int]  = 365
    artifacts_retention_days:      Optional[int]  = 90
    coppa_children_retention_days: Optional[int]  = 30
    audit_access_retention_days:   Optional[int]  = 365
    crypto_shredding_enabled:      Optional[bool] = True
    crypto_shredding_passes:       Optional[int]  = 3
    crypto_shredding_vacuum:       Optional[bool] = True
    coppa_strict_shredding:        Optional[bool] = True


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


# ── Regional formats ──────────────────────────────────────────────────────────

class RegionalSettings(LimitedModel):
    region:     Optional[str] = None
    hour_cycle: Optional[str] = None
    week_start: Optional[str] = None
    time_zone:  Optional[str] = None
    digits:     Optional[str] = None


@router.get("/regional")
def get_regional():
    """How dates, times and numbers are shown. Public: the screens need it
    before sign-in, and it holds nothing about anyone."""
    from ..core import regional
    return {**regional.get(load_settings()), "regions": regional.REGIONS}


@router.patch("/regional")
def save_regional(data: RegionalSettings, _: User = Depends(require_permission("settings.system"))):
    from ..core import regional
    s = load_settings()
    merged = {**regional.get(s), **{k: v for k, v in data.model_dump().items() if v is not None}}
    try:
        s["regional"] = regional.clean(merged)
    except ValueError as e:
        logger.warning("Regional settings update failed: %s", e)
        raise HTTPException(400, "Invalid regional settings. Choose a valid region, time format, and timezone.")
    _save(s)
    regional._cache["value"] = None
    return s["regional"]


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
    except Exception:
        logger.exception("IMAP connection test failed")
        res["errors"].append("IMAP connection test failed")

    try:
        if not e.get("smtp_password_enc"): raise ValueError("No SMTP password saved")
        ctx = ssl_module.create_default_context()
        ctx.minimum_version = ssl_module.TLSVersion.TLSv1_2
        with smtplib.SMTP(e["smtp_host"], e.get("smtp_port", 587)) as sc:
            if e.get("smtp_tls", True): sc.starttls(context=ctx)
            with ephemeral_secret(e.get("smtp_password_enc")) as pw:
                sc.login(e["smtp_user"], pw)
        res["smtp"] = True
    except Exception:
        logger.exception("SMTP connection test failed")
        res["errors"].append("SMTP connection test failed")

    res["connected"] = res["imap"] and res["smtp"]
    return res


# ── Scheduler ─────────────────────────────────────────────────────────────────

@router.patch("/scheduler")
def save_scheduler(data: SchedulerConfig, _: User = Depends(require_permission("scheduler.manage"))):
    from ..core.calendar_plan import clean_days, clean_dates
    s = load_settings()
    new = data.model_dump(exclude_unset=True)
    if "run_days" in new:
        new["run_days"] = clean_days(new["run_days"])
    if "skip_dates" in new:
        new["skip_dates"] = clean_dates(new["skip_dates"])
    if "maintenance_windows" in new:
        from ..core.calendar_plan import clean_maintenance_windows
        new["maintenance_windows"] = clean_maintenance_windows(new["maintenance_windows"])
    s["scheduler"] = {**(s.get("scheduler") or {}), **new}   # fields not sent keep their values
    _save(s)
    # Check maintenance windows immediately and reload scheduler
    from ..core.scheduler import reload_scheduler, check_maintenance_windows
    check_maintenance_windows()
    import threading
    threading.Thread(target=reload_scheduler, daemon=True).start()
    return s["scheduler"]


# ── Privacy / export / danger ─────────────────────────────────────────────────

@router.patch("/privacy")
def save_privacy(data: PrivacyDataSettings, _: User = Depends(require_permission("settings.system"))):
    s = load_settings()
    d = data.model_dump()
    if d.get("auto_purge_logs_days") is not None and d["auto_purge_logs_days"] < 30:
        raise HTTPException(400, "Keep logs for at least 30 days.")
    if d.get("logs_retention_days") is not None and d["logs_retention_days"] < 7:
        raise HTTPException(400, "Logs retention must be at least 7 days.")
    if d.get("audit_access_retention_days") is not None and d["audit_access_retention_days"] < 90:
        raise HTTPException(400, "Audit access log retention must be at least 90 days.")
    # Keep auto_purge_logs_days in sync with logs_retention_days
    if d.get("logs_retention_days") is not None:
        d["auto_purge_logs_days"] = d["logs_retention_days"]
    s["privacy"] = {**(s.get("privacy") or {}), **d}   # keeps the last-run record
    _save(s)
    return s["privacy"]


@router.get("/export")
def export_data(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..models.database import FamilyMember
    from ..core.compliance import own_member_ids
    # Your own family only: a manager's export must not include every patron
    # in their branches (staff use /api/privacy/export/{id} per request).
    ids     = own_member_ids(db, current_user)
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
    from ..models import database as m
    # Children first: their rows point at the requests.
    for model in (m.ConfirmationLink, m.RequestEvent, m.RequestVariant, m.VerificationCheck,
                  m.CaptchaChallenge, m.EmailLog, m.AutomationLog):
        db.query(model).delete(synchronize_session=False)
    if hasattr(m, "NoticeSent"):
        db.query(m.NoticeSent).delete(synchronize_session=False)
    db.query(m.WebSearchHit).filter(m.WebSearchHit.request_id.isnot(None)).update(
        {m.WebSearchHit.request_id: None}, synchronize_session=False)
    db.query(m.RemovalRequest).delete(synchronize_session=False)
    db.commit()


from datetime import datetime


# ── Vault limits ──────────────────────────────────────────────────────────────

class VaultLimits(LimitedModel):
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
    if data.max_names               > 20:  raise HTTPException(400, "Names can go up to 20 per person.")
    if data.max_addresses           > 30:  raise HTTPException(400, "Addresses can go up to 30 per person.")
    if data.max_phones              > 20:  raise HTTPException(400, "Phone numbers can go up to 20 per person.")
    if data.max_emails              > 20:  raise HTTPException(400, "Email addresses can go up to 20 per person.")
    if data.max_children_per_parent < 0:   raise HTTPException(400, "The number of children per parent can't be below 0.")

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

    from ..core.settings_store import get_secret_key_status
    sec_status = get_secret_key_status()

    return {
        "sqlcipher_available":    sqlcipher_available,
        "db_encryption_enabled":  db_key_set and sqlcipher_available and db_url.startswith("sqlite"),
        "field_encryption_enabled": field_key_set,
        "db_key_env_set":         bool(os.getenv("DB_ENCRYPTION_KEY") or os.getenv("DB_ENCRYPTION_KEY_FILE")),
        "field_key_env_set":      bool(os.getenv("FIELD_ENCRYPTION_KEY") or os.getenv("FIELD_ENCRYPTION_KEY_FILE")),
        "secret_key_set":         is_valid_secret_key(os.getenv("SECRET_KEY")),
        "keys_locked_down":       sec_status.get("permissions_secure", False),
        "db_type":                "sqlite" if db_url.startswith("sqlite") else "postgres",
        "notes": {
            "db_migration":   "Run: docker exec openoptout-api python -m backend.core.encryption migrate",
            "key_setup":      "Set DB_ENCRYPTION_KEY and FIELD_ENCRYPTION_KEY in your .env file",
            "postgres":       "For Postgres, use pgcrypto extension or provider-level TDE (RDS, Azure, Cloud SQL)",
        }
    }


# ── HSTS (HTTP Strict Transport Security) ────────────────────────────────────

class HstsSettings(LimitedModel):
    enabled: bool = False


@router.get("/security/hsts")
def get_hsts_settings(_: User = Depends(require_permission("settings.system"))):
    """Return current HSTS (HTTP Strict Transport Security) configuration."""
    from ..core.settings_store import is_hsts_enabled
    s = load_settings()
    dep = s.get("deployment", {})
    return {
        "enabled": is_hsts_enabled(s),
        "reverse_proxy": dep.get("reverse_proxy", "unset"),
        "env_hsts": os.getenv("HSTS", "").strip().lower() in ("1", "true", "on", "yes"),
    }


@router.patch("/security/hsts")
def update_hsts_settings(data: HstsSettings, _: User = Depends(require_permission("settings.system"))):
    """Enable or disable HTTP Strict Transport Security (HSTS) response headers."""
    from ..core.settings_store import is_hsts_enabled
    s = load_settings()
    sec = s.setdefault("security", {})
    sec["hsts"] = bool(data.enabled)
    if "deployment" in s and isinstance(s["deployment"], dict):
        s["deployment"]["hsts"] = bool(data.enabled)
    _save(s)
    return {"saved": True, "enabled": is_hsts_enabled(s)}


# ── WebAuthn / FIDO2 Security Settings ───────────────────────────────────────

class WebAuthnSettings(LimitedModel):
    authenticator_attachment: Optional[str] = "any"     # "any" | "cross-platform" | "platform"
    user_verification:        Optional[str] = "preferred" # "preferred" | "required" | "discouraged"
    fips_only:                Optional[bool] = False
    rp_name:                  Optional[str] = "OpenOptOut"
    rp_id:                    Optional[str] = None


@router.get("/security/webauthn")
def get_webauthn_settings(_: User = Depends(require_super_admin)):
    """Return institutional WebAuthn configuration and metadata."""
    from ..core.mfa import get_webauthn_config
    cfg = get_webauthn_config()
    return {
        "config": cfg,
        "descriptions": {
            "authenticator_attachment": {
                "any": "Allows roaming USB/NFC hardware security keys (YubiKey, Google Titan), built-in platform authenticators (Apple Touch ID / Face ID, Windows Hello), and cross-device phone authentication (scanning a QR code with an iPhone using Face ID or an Android phone using biometrics). Recommended for broad compatibility.",
                "cross-platform": "Requires external/roaming hardware keys (YubiKey, Titan). Restricts built-in platform authenticators like Touch ID. If selected, staff on laptops without a physical USB/NFC key cannot enroll biometrics.",
                "platform": "Requires built-in device biometrics (Apple Touch ID, Windows Hello). Restricts external USB/NFC security keys. If selected, staff using desktop machines or external keyboards without built-in sensors cannot enroll."
            },
            "user_verification": {
                "preferred": "Prompts for PIN or biometric verification (e.g. YubiKey Bio fingerprint, Touch ID, or security key PIN) if the key supports it, but does not block keys without PINs. Best balance of usability and security.",
                "required": "Strictly mandates PIN or biometric verification. Basic U2F keys or hardware keys without a configured PIN will fail authentication.",
                "discouraged": "Only checks physical presence (a basic capacitive touch). Does not require biometric or PIN verification."
            },
            "fips_only": {
                "description": "Enforce NIST FIPS 140-2 / FIPS 140-3 validated authenticators. Checks the cryptographic AAGUID against certified YubiKey FIPS models during enrollment. If enabled, non-FIPS consumer YubiKeys, Titan keys, and platform biometrics (Touch ID) will be rejected during enrollment."
            }
        }
    }


@router.patch("/security/webauthn")
def update_webauthn_settings(data: WebAuthnSettings, _: User = Depends(require_super_admin)):
    """Update institutional WebAuthn configuration."""
    if data.authenticator_attachment not in ("any", "cross-platform", "platform"):
        raise HTTPException(400, "authenticator_attachment must be 'any', 'cross-platform', or 'platform'")
    if data.user_verification not in ("preferred", "required", "discouraged"):
        raise HTTPException(400, "user_verification must be 'preferred', 'required', or 'discouraged'")

    s = load_settings()
    sec = s.setdefault("security", {})
    sec["webauthn"] = data.model_dump()
    _save(s)
    return {"saved": True, "config": sec["webauthn"]}


# ── Passwordless Authentication Policy (Local Accounts Only) ─────────────────

class PasswordlessSettings(LimitedModel):
    enabled: Optional[bool] = False
    allow_passkey: Optional[bool] = True
    allow_magic_link: Optional[bool] = True
    enforce_passwordless_local: Optional[bool] = False


@router.get("/security/passwordless")
def get_passwordless_settings(_: User = Depends(require_super_admin)):
    """Return institutional passwordless authentication settings and scope descriptions."""
    from ..core.mfa import get_passwordless_config
    cfg = get_passwordless_config()
    return {
        "config": cfg,
        "descriptions": {
            "enabled": "Enables passwordless authentication for local user and staff accounts.",
            "allow_passkey": "Permits authentication with FIDO2 / WebAuthn passkeys (Touch ID, Face ID, Windows Hello, YubiKey).",
            "allow_magic_link": "Permits passwordless sign-in via single-use email verification codes and magic links.",
            "enforce_passwordless_local": "Disables password authentication for local accounts, enforcing passkeys or email codes.",
            "scope_notice": "Passwordless settings strictly govern local accounts. Accounts managed through third-party systems (LDAP, SIP2, SAML, Google/Microsoft OIDC) continue to rely on their external identity providers as their source of truth.",
        },
    }


@router.patch("/security/passwordless")
def update_passwordless_settings(data: PasswordlessSettings, _: User = Depends(require_super_admin)):
    """Update institutional passwordless authentication settings for local accounts."""
    s = load_settings()
    sec = s.setdefault("security", {})
    pwdless = sec.setdefault("passwordless", {})
    if data.enabled is not None:
        pwdless["enabled"] = bool(data.enabled)
    if data.allow_passkey is not None:
        pwdless["allow_passkey"] = bool(data.allow_passkey)
    if data.allow_magic_link is not None:
        pwdless["allow_magic_link"] = bool(data.allow_magic_link)
    if data.enforce_passwordless_local is not None:
        pwdless["enforce_passwordless_local"] = bool(data.enforce_passwordless_local)
    _save(s)
    from ..core.mfa import get_passwordless_config
    return {"saved": True, "config": get_passwordless_config()}


# ── Role-Based Session Duration & Remember Me Policy ──────────────────────────

class RoleSessionConfig(LimitedModel):
    session_duration_hours: int = 8
    remember_me_allowed: bool = True
    remember_me_mode: str = "username_only"  # "username_only" | "extend_session"
    remember_me_duration_days: int = 1

class SessionPolicySettings(LimitedModel):
    remember_me_enabled: bool = True
    roles: Dict[str, RoleSessionConfig] = Field(..., max_length=50)


@router.get("/security/session-policy")
def get_session_policy_settings(_: User = Depends(require_super_admin)):
    """Return institutional session duration and remember-me policies by role."""
    from ..core.session_policy import get_session_policy, DEFAULT_SESSION_POLICY
    return {
        "policy": get_session_policy(),
        "defaults": DEFAULT_SESSION_POLICY,
        "descriptions": {
            "remember_me_enabled": "Global switch to allow or completely disable the Remember Me feature across the system.",
            "roles": {
                "super_admin": "Full system administrator account with total system authority.",
                "manager": "Staff manager account with delegated operational controls.",
                "parent": "Account owner managing household profiles.",
                "member": "Standard patron/household member.",
            },
            "modes": {
                "username_only": "Saves username/email on device for quick prefill; session duration remains short (recommended for staff/admins).",
                "extend_session": "Maintains an active long-lived signed session on the device for the configured number of days.",
            },
        },
    }


@router.patch("/security/session-policy")
def update_session_policy_settings(data: SessionPolicySettings, _: User = Depends(require_super_admin)):
    """Update institutional session duration and remember-me policy per role."""
    s = load_settings()
    sec = s.setdefault("security", {})
    sec["session_policy"] = {
        "remember_me_enabled": bool(data.remember_me_enabled),
        "roles": {k: v.model_dump() for k, v in data.roles.items()},
    }
    _save(s)
    from ..core.session_policy import get_session_policy
    return {"saved": True, "policy": get_session_policy()}


# ── Role-Based MFA Policy & Compliance Settings ───────────────────────────────

class MfaRolePermissions(LimitedModel):
    totp: bool = True
    webauthn: bool = True
    backup_codes: bool = True

class MfaComplianceTimer(LimitedModel):
    enabled: bool = True
    value: int = 3
    unit: str = "days"

class MfaRolePolicySettings(LimitedModel):
    roles: Dict[str, MfaRolePermissions] = Field(..., max_length=50)
    compliance: Optional[Dict[str, MfaComplianceTimer]] = Field(None, max_length=50)


@router.get("/security/mfa-policy")
def get_mfa_policy_settings(_: User = Depends(require_super_admin)):
    """Return configured and default MFA options and compliance timers per permissions group/role."""
    from ..core.mfa import (
        get_mfa_role_permissions, DEFAULT_MFA_ROLE_PERMISSIONS,
        get_mfa_role_compliance, DEFAULT_MFA_COMPLIANCE
    )
    return {
        "roles": get_mfa_role_permissions(),
        "defaults": DEFAULT_MFA_ROLE_PERMISSIONS,
        "compliance": get_mfa_role_compliance(),
        "compliance_defaults": DEFAULT_MFA_COMPLIANCE,
        "role_descriptions": {
            "super_admin": "Full system administrators with unrestricted access to settings, databases, and logs.",
            "manager": "Staff managers administering members, queue dispatches, and organizational units.",
            "parent": "Account owners managing their own household profiles and opt-out requests.",
            "member": "Standard patrons/members with view and managed access.",
        },
    }


@router.patch("/security/mfa-policy")
def update_mfa_policy_settings(data: MfaRolePolicySettings, _: User = Depends(require_super_admin)):
    """
    Update allowed MFA options and compliance timers per permissions group.
    Ensures mandated administrative roles retain at least one factor and validates timer ranges.
    """
    from ..core.mfa import (
        validate_mfa_role_permissions, get_mfa_role_permissions,
        validate_mfa_compliance, get_mfa_role_compliance
    )
    policy_dict = {r: p.model_dump() for r, p in data.roles.items()}
    valid, err_msg = validate_mfa_role_permissions(policy_dict)
    if not valid:
        raise HTTPException(400, err_msg)

    compliance_dict = None
    if data.compliance is not None:
        compliance_dict = {r: c.model_dump() for r, c in data.compliance.items()}
        valid_comp, err_comp = validate_mfa_compliance(compliance_dict)
        if not valid_comp:
            raise HTTPException(400, err_comp)

    s = load_settings()
    sec = s.setdefault("security", {})
    sec["mfa_roles"] = policy_dict
    if compliance_dict is not None:
        sec["mfa_compliance"] = compliance_dict
    _save(s)
    return {
        "saved": True,
        "roles": get_mfa_role_permissions(),
        "compliance": get_mfa_role_compliance(),
    }



# ── Automation (user-agent rotation, bot evasion) ─────────────────────────────

class AutomationConfig(LimitedModel):
    rotate_user_agents:   bool = True
    custom_user_agents: list[str] = Field([], max_length=100)
    inter_submission_delay_seconds: float = 1.5
    # Try a best-guess fill on broker sites OpenOptOut has no steps for. Off by
    # default: guessing can type a person's details into the wrong form.
    best_guess_forms: bool = False


@router.get("/automation", response_model=AutomationConfig)
def get_automation(_: User = Depends(get_current_user)):
    s = load_settings()
    a = s.get("automation", {})
    return AutomationConfig(
        rotate_user_agents=a.get("rotate_user_agents", True),
        custom_user_agents=a.get("custom_user_agents", []),
        inter_submission_delay_seconds=a.get("inter_submission_delay_seconds", 1.5),
        best_guess_forms=bool(a.get("best_guess_forms", False)),
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

class ProxyConfig(LimitedModel):
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
    except Exception:
        return {"ok": False, "error": "Proxy connection test failed. Check proxy configuration."}


# ── Plugin system settings ────────────────────────────────────────────────────

class PluginSystemConfig(LimitedModel):
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


class PluginDenyRequest(LimitedModel):
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
        raise HTTPException(400, "Confirm that you want to allow plugins again.")
    s = load_settings()
    p = s.setdefault("plugins", {})
    p["denied"] = False
    _save(s)
    return {"denied": False,
            "message": "Plugin system deny lifted. Enable the system and plugins deliberately to resume."}



# ── Unclear matches (core/match_policy.py) ────────────────────────────────────

class MatchingGlobal(LimitedModel):
    unclear_listings: str
    users_choose: bool = True


class MatchingMine(LimitedModel):
    unclear_listings: Optional[str] = None     # None: use the default


@router.get("/matching")
def get_matching(user: User = Depends(get_current_user)):
    """What happens when a site shows only a name: the default, and this person's own choice."""
    from ..core import match_policy as mp
    from ..core.access import has_permission
    g = mp.global_settings(load_settings())
    mine = mp.user_choice(user) if g["users_choose"] else None
    return {**g, "mine": mine, "effective": mine or g["unclear_listings"],
            "choices": [{"value": c, "label": mp.LABELS[c]} for c in mp.CHOICES],
            "can_set_default": has_permission(user, "settings.system")}


@router.patch("/matching")
def save_matching(data: MatchingGlobal, _: User = Depends(require_permission("settings.system"))):
    from ..core import match_policy as mp
    try:
        return mp.save_global(data.unclear_listings, data.users_choose)
    except ValueError as e:
        logger.warning("Matching policy save global failed: %s", e)
        raise HTTPException(400, "Choose ask, skip or remove all.")


@router.patch("/matching/mine")
def save_my_matching(data: MatchingMine, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..core import match_policy as mp
    if not mp.global_settings(load_settings())["users_choose"]:
        raise HTTPException(403, "Your administrator has set this for everyone.")
    try:
        mp.save_user(user, data.unclear_listings)
    except ValueError as e:
        logger.warning("Matching policy save user failed: %s", e)
        raise HTTPException(400, "Choose ask, skip or remove all.")
    db.commit()
    return {"mine": mp.user_choice(user)}


# ── Master Secret Key & Entropy Generator ─────────────────────────────────────

class SecretKeyUpdate(LimitedModel):
    key: str = Field(..., min_length=128, max_length=512)


@router.get("/security/secret-key")
def get_secret_key_info(_: User = Depends(require_permission("settings.system"))):
    from ..core.settings_store import get_secret_key_status
    return get_secret_key_status()


@router.post("/security/secret-key")
def update_secret_key(body: SecretKeyUpdate, user: User = Depends(require_permission("settings.system"))):
    from ..core.settings_store import save_secret_key_file
    from ..core.auth import create_access_token
    try:
        status_info = save_secret_key_file(body.key)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Master secret key must be between 128 and 512 characters long and must not be a placeholder value.",
        )
    # Issue a fresh access token signed with the new master key so the admin stays signed in
    fresh_token = create_access_token(
        data={"sub": user.email, "user_id": user.id, "role": user.role.value, "token_version": getattr(user, "token_version", 0) or 0}
    )
    return {**status_info, "access_token": fresh_token}


@router.get("/security/entropy-images")
def get_entropy_images(count: int = 8, _: User = Depends(require_permission("settings.system"))):
    from ..core.settings_store import generate_entropy_images
    return {"images": generate_entropy_images(count)}


# ── Client-Certificate Authentication (mTLS) ───────────────────────────────

class MtlsToggle(LimitedModel):
    enabled: bool
    mode: Optional[str] = "require"


class MtlsCaInit(LimitedModel):
    ca_pem: Optional[str] = None
    days: Optional[int] = 3650


class MtlsMintRequest(LimitedModel):
    device_name: str
    password: Optional[str] = None  # nosec: B107 -- optional PKCS#12 export passphrase
    passphrase: Optional[str] = None  # nosec: B107
    days: Optional[int] = 365


class MtlsRevokeRequest(LimitedModel):
    serial_or_name: str


@router.get("/security/mtls")
def get_mtls_settings(_: User = Depends(require_permission("settings.system"))):
    from ..core.mtls import get_mtls_status
    return get_mtls_status()


@router.patch("/security/mtls")
def update_mtls_settings(data: MtlsToggle, _: User = Depends(require_permission("settings.system"))):
    s = load_settings()
    sec = s.setdefault("security", {})
    mtls_cfg = sec.setdefault("mtls", {})

    dep = s.get("deployment", {})
    if data.enabled and dep.get("cloudflare_aop"):
        raise HTTPException(400, "Cloudflare AOP and client mTLS cannot be enabled simultaneously.")

    mtls_cfg["enabled"] = bool(data.enabled)
    mtls_cfg["mode"] = data.mode if data.mode in ("require", "optional") else "require"
    _save(s)

    from ..core.mtls import get_mtls_status
    return get_mtls_status()


@router.post("/security/mtls/ca")
def initialize_mtls_ca(body: MtlsCaInit, _: User = Depends(require_permission("settings.system"))):
    from ..core.mtls import generate_ca, sync_proxy_ca_file
    s = load_settings()
    sec = s.setdefault("security", {})
    mtls_cfg = sec.setdefault("mtls", {})

    if body.ca_pem:
        from cryptography import x509
        try:
            cert = x509.load_pem_x509_certificate(body.ca_pem.encode("utf-8"))
        except Exception as e:
            logger.warning("Invalid PEM certificate uploaded: %s", e)
            raise HTTPException(400, "Invalid PEM certificate format.")
        mtls_cfg["ca_cert"] = body.ca_pem.strip()
        mtls_cfg.pop("ca_key_enc", None)
        sync_proxy_ca_file(body.ca_pem)
    else:
        try:
            ca_cert_pem, ca_key_pem = generate_ca(days=body.days or 3650)
        except Exception as e:
            logger.error("Failed to generate CA certificate: %s", e)
            raise HTTPException(500, "Could not generate CA certificate.")
        from ..core.settings_store import encrypt_password
        mtls_cfg["ca_cert"] = ca_cert_pem
        mtls_cfg["ca_key_enc"] = encrypt_password(ca_key_pem)
        sync_proxy_ca_file(ca_cert_pem)

    _save(s)
    from ..core.mtls import get_mtls_status
    return get_mtls_status()


@router.post("/security/mtls/mint")
def mint_mtls_client_cert(body: MtlsMintRequest, _: User = Depends(require_permission("settings.system"))):
    import uuid
    from ..core.mtls import mint_client_cert
    from ..core.settings_store import decrypt_password

    if not body.device_name or not body.device_name.strip():
        raise HTTPException(400, "device_name is required")

    s = load_settings()
    sec = s.get("security", {}) or {}
    mtls_cfg = sec.get("mtls", {}) or {}

    ca_cert = mtls_cfg.get("ca_cert")
    ca_key_enc = mtls_cfg.get("ca_key_enc")
    if not ca_cert:
        raise HTTPException(400, "No Client CA configured. Initialize a CA first.")
    if not ca_key_enc:
        raise HTTPException(
            400,
            "The CA private key is held offline. Use scripts/openoptout-mtls.sh on the host to issue client certificates.",
        )

    ca_key = decrypt_password(ca_key_enc)
    if not ca_key:
        raise HTTPException(500, "Could not decrypt CA private key.")

    try:
        minted = mint_client_cert(
            ca_cert_pem=ca_cert,
            ca_key_pem=ca_key,
            device_name=body.device_name.strip(),
            passphrase=body.passphrase or body.password or None,
            days=body.days or 365,
        )
    except Exception as e:
        logger.error("Failed to issue client certificate: %s", e)
        raise HTTPException(500, "Failed to issue client certificate.")

    clients = mtls_cfg.setdefault("clients", [])
    entry = {
        "id": str(uuid.uuid4()),
        "name": minted["device_name"],
        "serial": minted["serial"],
        "issued_at": minted["issued_at"],
        "expires_at": minted["expires_at"],
        "revoked": False,
    }
    clients.append(entry)
    _save(s)

    return {
        "ok": True,
        "entry": entry,
        "p12_base64": minted["p12_base64"],
        "filename": minted["filename"],
    }


@router.post("/security/mtls/revoke")
def revoke_mtls_client_cert(body: MtlsRevokeRequest, _: User = Depends(require_permission("settings.system"))):
    import datetime
    s = load_settings()
    sec = s.get("security", {}) or {}
    mtls_cfg = sec.get("mtls", {}) or {}
    clients = mtls_cfg.get("clients", [])

    found = False
    target = body.serial_or_name.strip()
    for c in clients:
        if c.get("id") == target or c.get("serial") == target or c.get("name") == target:
            c["revoked"] = True
            c["revoked_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            found = True

    if not found:
        raise HTTPException(404, "Certificate not found")

    # The per-client "revoked" flag above is for display only; what actually
    # stops the certificate from reaching the app is this file, which
    # backend/main.py's revocation check reads on every request (see
    # core/mtls.py). If it can't be written, fail loudly rather than reporting
    # success for a revoke that silently did nothing.
    from ..core.mtls import write_revoked_serials_file
    all_revoked = [c["serial"] for c in clients if c.get("revoked") and c.get("serial")]
    if not write_revoked_serials_file(all_revoked):
        raise HTTPException(
            500,
            "The certificate was marked revoked, but the revocation list could not be saved "
            "to disk, so it may still be accepted. Check that the app's data volume is writable "
            "and try again.",
        )

    _save(s)
    return {"ok": True}


