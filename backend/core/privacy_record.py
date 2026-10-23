"""
OpenOptOut's own privacy record: what personal data an install keeps about
the people it protects, why, how it's protected, how long it's kept, and who
looked at it. For libraries and other organizations running OpenOptOut for
the public, this is the basis of their GDPR Article 30 "record of processing"
and of answering CCPA/GDPR access and deletion requests.

  INVENTORY        what's kept, where, why, and how it's protected
  record()         the inventory plus live counts, encryption state, retention
  export_person()  everything about one person, as JSON (access requests)
  purge()          deletes old logs on the retention schedule (daily job)
  log_access()     records staff looking at, exporting or deleting someone
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 365

# encrypted: "field" = encrypted column (FIELD_ENCRYPTION_KEY); "db" = only as
# protected as the database itself (SQLCipher / provider encryption).
INVENTORY = [
    {"key": "names", "what": "Names (main name, other spellings, legal name)",
     "tables": ["family_members.full_name", "identities (kind=name)", "family_members.formal_name"],
     "why": "To find listings and ask sites to remove them", "encrypted": "field (other spellings, legal name); db (main name)",
     "kept": "Until the person is removed"},
    {"key": "contact", "what": "Addresses, phone numbers, email addresses",
     "tables": ["identities"], "why": "To find listings and fill in opt-out forms", "encrypted": "field",
     "kept": "Until the person removes them, or is removed"},
    {"key": "birthday", "what": "Birthday or age (optional)", "tables": ["family_members.dob", "family_members.age"],
     "why": "Some sites require it; tells a person apart from someone with the same name",
     "encrypted": "field (birthday); db (age)", "kept": "Until the person removes it, or is removed"},
    {"key": "requests", "what": "Opt-out requests and their history (sites, dates, status)",
     "tables": ["removal_requests", "request_events", "verification_checks", "request_variants"],
     "why": "To track removals, check they stay removed, and report missed deadlines",
     "encrypted": "db", "kept": "Until the person is removed"},
    {"key": "emails", "what": "Opt-out email addresses and replies from sites (subject and a short excerpt)",
     "tables": ["contact_addresses", "email_logs", "confirmation_links"],
     "why": "To match replies to requests and click confirmation links",
     "encrypted": "field (addresses, links); db (subjects, excerpts)", "kept": "Excerpts: retention period; rest: until removed"},
    {"key": "inboxes", "what": "Connected email inboxes (address, sign-in tokens or app password)",
     "tables": ["mailboxes", "settings (OAuth tokens)"], "why": "To send opt-outs and read replies",
     "encrypted": "field", "kept": "Until the inbox is disconnected"},
    {"key": "search", "what": "Web search results about a person", "tables": ["web_search_hits", "discovery_results"],
     "why": "To find listings", "encrypted": "field (titles, excerpts); db (addresses of pages)",
     "kept": "Results not on a known site: retention period; rest: until removed"},
    {"key": "logs", "what": "Automation logs and CAPTCHA screenshots", "tables": ["automation_logs", "captcha_challenges", "screenshots folder"],
     "why": "To show what happened and fix problems", "encrypted": "db (logs); none (screenshot files)",
     "kept": "Retention period"},
    {"key": "accounts", "what": "Accounts (email, sign-in, role, branch, preferences)", "tables": ["users"],
     "why": "To sign in and decide who can see whom", "encrypted": "db (passwords are hashed)",
     "kept": "Until the account is deleted"},
    {"key": "access", "what": "Record of staff viewing, exporting or deleting someone's details", "tables": ["access_log"],
     "why": "Accountability", "encrypted": "db", "kept": "Retention period (at least 1 year)"},
]

NEVER_STORED = ["Social Security numbers", "Government ID images", "Payment card numbers", "Passwords in readable form"]


def retention_days(cfg: dict) -> int:
    priv = (cfg or {}).get("privacy") or {}
    v = priv.get("logs_retention_days", priv.get("auto_purge_logs_days", DEFAULT_RETENTION_DAYS))
    try:
        return max(30, int(v))
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_DAYS


def encryption_state() -> dict:
    from .encryption import get_db_encryption_key, get_field_encryption_key
    try:
        import sqlcipher3  # noqa: F401
        have = True
    except ImportError:
        have = False
    url = os.getenv("DATABASE_URL", "sqlite:///./privacy_pipeline.db")
    sqlite = url.startswith("sqlite")
    return {"database": bool(get_db_encryption_key()) and have and sqlite,
            "database_type": "sqlite" if sqlite else "postgres",
            "fields": bool(get_field_encryption_key())}


def record(db, cfg: dict) -> dict:
    from ..models import database as m
    counts = {
        "people": db.query(m.FamilyMember).count(),
        "accounts": db.query(m.User).count(),
        "details": db.query(m.Identity).count(),
        "requests": db.query(m.RemovalRequest).count(),
        "emails": db.query(m.EmailLog).count(),
        "search_results": db.query(m.WebSearchHit).count(),
        "logs": db.query(m.AutomationLog).count(),
        "access_log": db.query(m.AccessLog).count(),
    }
    priv = (cfg or {}).get("privacy") or {}
    days = retention_days(cfg)
    last = priv.get("last_purge")
    enc = encryption_state()
    warnings = []
    if not enc["fields"]:
        warnings.append("Field encryption is off: set FIELD_ENCRYPTION_KEY so addresses, phones and emails are encrypted.")
    if not enc["database"] and enc["database_type"] == "sqlite":
        warnings.append("The database file isn't encrypted: set DB_ENCRYPTION_KEY (SQLCipher) so names and logs are protected at rest.")
    if enc["database_type"] == "postgres":
        warnings.append("Using PostgreSQL: make sure the provider encrypts storage at rest (RDS, Cloud SQL, Azure do).")
    
    lifecycle = {
        "logs_retention_days": int(priv.get("logs_retention_days", days)),
        "artifacts_retention_days": int(priv.get("artifacts_retention_days", 90)),
        "coppa_children_retention_days": int(priv.get("coppa_children_retention_days", 30)),
        "audit_access_retention_days": int(priv.get("audit_access_retention_days", 365)),
        "crypto_shredding_enabled": bool(priv.get("crypto_shredding_enabled", True)),
        "crypto_shredding_passes": int(priv.get("crypto_shredding_passes", 3)),
        "coppa_strict_shredding": bool(priv.get("coppa_strict_shredding", True)),
    }
    return {"generated_at": datetime.utcnow().isoformat(), "inventory": INVENTORY, "never_stored": NEVER_STORED,
            "counts": counts, "encryption": enc, "retention_days": days, "last_purge": last, "warnings": warnings,
            "lifecycle": lifecycle}


# ── Export (access requests) ──────────────────────────────────────────────────

def _iso(d):
    return d.isoformat() if isinstance(d, datetime) else d


def export_person(db, member) -> dict:
    """Everything OpenOptOut holds about one person, in readable form."""
    from ..models import database as m
    from .age import member_dob
    from .timeline import build
    reqs = db.query(m.RemovalRequest).filter(m.RemovalRequest.member_id == member.id).all()
    dob = member_dob(member)
    return {
        "exported_at": datetime.utcnow().isoformat(),
        "person": {"name": member.full_name, "legal_name": member.formal_name, "age": member.age,
                   "birthday": dob.isoformat() if dob else None, "added": _iso(member.created_at)},
        "details": [{"kind": i.kind, "value": i.value, "main": bool(i.is_primary)} for i in member.identities],
        "opt_out_email_addresses": [{"address": c.address,
                                     "site": (db.query(m.Broker.name).filter(m.Broker.id == c.broker_id).scalar()
                                              if c.broker_id else None),
                                     "created": _iso(c.created_at)}
                                    for c in db.query(m.ContactAddress).filter(m.ContactAddress.member_id == member.id)],
        "requests": [{
            "site": r.broker.name if r.broker else None, "status": getattr(r.status, "value", r.status),
            "sent": _iso(r.sent_at), "removed": _iso(r.confirmed_at), "next_check": _iso(r.recheck_after),
            "listing": r.listing_url,
            "history": build(db, r)["cycles"],
            "emails": [{"direction": e.direction, "subject": e.subject, "excerpt": e.body_snippet, "at": _iso(e.received_at)}
                       for e in r.emails],
        } for r in reqs],
        "search_results": [{"url": h.url, "title": h.title, "found": _iso(getattr(h, "found_at", None))}
                           for h in db.query(m.WebSearchHit).filter(m.WebSearchHit.member_id == member.id)],
        "account": _account(member.user),
        "never_stored": NEVER_STORED,
    }


def _account(u):
    if u is None:
        return None
    return {"email": u.email if not (u.email or "").endswith(".invalid") else None,
            "role": getattr(u.role, "value", u.role), "created": _iso(getattr(u, "created_at", None)),
            "can_sign_in": u.can_login, "language": u.preferred_language}


# ── Access log ────────────────────────────────────────────────────────────────

def log_access(db, actor, member, action: str, detail: str = "", throttle_minutes: int = 60) -> None:
    """
    Record staff touching someone else's details. Looking at your own family
    isn't logged. Views are recorded once an hour per person; exports and
    deletions every time. Never raises.
    """
    from ..models import database as m
    try:
        if actor is None or member is None or member.user_id == actor.id:
            return
        if action == "view":
            owned = db.query(m.ProfileAccess).filter(m.ProfileAccess.manager_id == actor.id,
                                                     m.ProfileAccess.managed_id == member.user_id).first()
            if owned is not None:
                return      # a parent looking at their own child
            since = datetime.utcnow() - timedelta(minutes=throttle_minutes)
            if db.query(m.AccessLog).filter(m.AccessLog.actor_id == actor.id, m.AccessLog.member_id == member.id,
                                            m.AccessLog.action == "view", m.AccessLog.at >= since).first():
                return
        db.add(m.AccessLog(actor_id=actor.id, actor_name=actor.full_name, member_id=member.id,
                           member_name=member.full_name, action=action, detail=(detail or "")[:200]))
        db.commit()
    except Exception as e:
        log.warning("access log failed: %s", e)
        try:
            db.rollback()
        except Exception:
            pass


# ── Retention ─────────────────────────────────────────────────────────────────

def purge(db, cfg: dict, now: Optional[datetime] = None, screenshots_dir: Optional[str] = None) -> dict:
    """
    Delete logs older than the retention period. Never touches a person's
    details, requests or their history; only working records about them.
    Supports granular retention per ISO/IEC 27701 and COPPA standards.
    """
    from ..models import database as m
    now = now or datetime.utcnow()
    priv = (cfg or {}).get("privacy") or {}
    ret_days = retention_days(cfg)

    logs_days = int(priv.get("logs_retention_days", ret_days) or ret_days)
    artifacts_days = int(priv.get("artifacts_retention_days", 90) or 90)
    audit_days = int(priv.get("audit_access_retention_days", 365) or 365)
    coppa_days = int(priv.get("coppa_children_retention_days", 30) or 30)

    # In tests or custom config where only auto_purge_logs_days is passed:
    if "auto_purge_logs_days" in priv and "artifacts_retention_days" not in priv:
        artifacts_days = min(artifacts_days, ret_days)

    cut_logs = now - timedelta(days=logs_days)
    cut_artifacts = now - timedelta(days=artifacts_days)
    cut_audit = now - timedelta(days=max(90, audit_days))
    cut_coppa = now - timedelta(days=coppa_days)

    st = {}
    st["automation_logs"] = db.query(m.AutomationLog).filter(m.AutomationLog.created_at < cut_logs).delete(synchronize_session=False)
    st["email_excerpts"] = db.query(m.EmailLog).filter(m.EmailLog.received_at < cut_logs, m.EmailLog.body_snippet.isnot(None)) \
        .update({m.EmailLog.body_snippet: None}, synchronize_session=False)
    old_ch = db.query(m.CaptchaChallenge).filter(m.CaptchaChallenge.created_at < cut_artifacts,
                                                 m.CaptchaChallenge.status != "pending").all()
    for c in old_ch:
        if c.screenshot:
            try:
                os.remove(c.screenshot)
            except OSError:
                pass
        db.delete(c)
    st["captchas"] = len(old_ch)
    st["search_results"] = db.query(m.WebSearchHit).filter(
        m.WebSearchHit.request_id.is_(None), m.WebSearchHit.status != "added",
        m.WebSearchHit.last_seen_at < cut_logs).delete(synchronize_session=False)
    st["scheduler_runs"] = db.query(m.SchedulerRun).filter(m.SchedulerRun.started_at < cut_logs).delete(synchronize_session=False)
    st["access_log"] = db.query(m.AccessLog).filter(m.AccessLog.at < cut_audit).delete(synchronize_session=False)

    # COPPA Child Data Protection: purge auxiliary confirmation links & email logs for confirmed minor requests
    coppa_purged = 0
    if priv.get("coppa_strict_shredding", True):
        from .age import current_age
        child_members = [mem.id for mem in db.query(m.FamilyMember).all()
                          if (current_age(mem) is not None and current_age(mem) < 18)
                          or getattr(mem, "is_child", False)]
        if child_members:
            old_child_reqs = [r.id for r in db.query(m.RemovalRequest.id).filter(
                m.RemovalRequest.member_id.in_(child_members),
                m.RemovalRequest.status == m.RequestStatus.confirmed if hasattr(m.RequestStatus, "confirmed") else m.RemovalRequest.confirmed_at.isnot(None),
                m.RemovalRequest.confirmed_at < cut_coppa
            )]
            if old_child_reqs:
                coppa_purged += db.query(m.ConfirmationLink).filter(m.ConfirmationLink.request_id.in_(old_child_reqs)).delete(synchronize_session=False)
                coppa_purged += db.query(m.EmailLog).filter(m.EmailLog.request_id.in_(old_child_reqs), m.EmailLog.body_snippet.isnot(None))\
                    .update({m.EmailLog.body_snippet: None}, synchronize_session=False)
    st["coppa_records"] = coppa_purged

    # Opt-out address labels written before they were masked held names and
    # addresses in the clear; keep only a fingerprint.
    import hashlib
    legacy = 0
    for c in db.query(m.ContactAddress).filter(m.ContactAddress.combo_label.like("% | %")).all():
        c.combo_label = "legacy · " + hashlib.sha256(c.combo_label.encode()).hexdigest()[:8]; legacy += 1
    st["old_labels_masked"] = legacy
    d = screenshots_dir if screenshots_dir is not None else "/data/screenshots"
    removed = 0
    if d and os.path.isdir(d):
        for n in os.listdir(d):
            p = os.path.join(d, n)
            try:
                if os.path.isfile(p) and datetime.utcfromtimestamp(os.path.getmtime(p)) < cut_artifacts:
                    os.remove(p); removed += 1
            except OSError:
                pass
    st["screenshot_files"] = removed
    db.commit()
    return st


def mark_purged(stats: dict) -> None:
    """Remember when the retention schedule last ran (shown on the privacy record)."""
    from .settings_store import load_settings, save_settings
    cfg = load_settings()
    cfg.setdefault("privacy", {})["last_purge"] = {"at": datetime.utcnow().isoformat(), "removed": stats}
    save_settings(cfg)
