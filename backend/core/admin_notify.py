"""
Administrator notifications by email.

Sends an operational message (e.g. a certificate reminder) to every super
administrator, one email per person (so admins don't see each other's addresses).

Transport:
  - If the setup wizard's "separate admin email account" is configured
    (settings.email.separate_admin_smtp + email.admin_smtp), use it — that's the
    account intended for the tool's own notifications.
  - Otherwise use the regular configured email transport (provider plugin such as
    Gmail/Outlook via OAuth, or SMTP) through core.email_send.

Never raises: a notification failure must never break the job that triggered it.
Returns {"sent": bool, "recipients": int, "delivered": int, "error": str}.
"""

import logging
import smtplib
import ssl
from email.mime.text import MIMEText

log = logging.getLogger(__name__)


def _super_admin_emails(db=None) -> list:
    from ..models.database import User, UserRole, SessionLocal
    own = db is None
    db = db or SessionLocal()
    try:
        rows = db.query(User).filter(User.role == UserRole.super_admin).all()
        return sorted({u.email.strip() for u in rows if u.email and "@" in u.email})
    finally:
        if own:
            db.close()


def _send_via_admin_smtp(admin: dict, frm: str, to: str, subject: str, body: str) -> dict:
    from .oauth_engine import _decrypt
    host = (admin.get("host") or "").strip()
    port = int(admin.get("port") or 587)
    user = (admin.get("username") or "").strip()
    pw = _decrypt(admin.get("password_enc", "")) if admin.get("password_enc") else ""
    msg = MIMEText(body, "plain")
    msg["Subject"], msg["From"], msg["To"] = subject, frm or user, to
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=25, context=ssl.create_default_context()) as s:
                if pw: s.login(user, pw)
                s.sendmail(frm or user, [to], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=25) as s:
                s.starttls(context=ssl.create_default_context())
                if pw: s.login(user, pw)
                s.sendmail(frm or user, [to], msg.as_string())
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_admin_email(subject: str, body: str, db=None) -> dict:
    try:
        from .settings_store import load_settings
        cfg = load_settings()
        recipients = _super_admin_emails(db)
        if not recipients:
            return {"sent": False, "recipients": 0, "delivered": 0,
                    "error": "no super administrator email addresses"}
        email_cfg = cfg.get("email", {}) or {}
        admin = email_cfg.get("admin_smtp") or {}
        use_admin = bool(email_cfg.get("separate_admin_smtp")) and bool(admin.get("host"))
        delivered, last_err = 0, ""
        for to in recipients:
            if use_admin:
                r = _send_via_admin_smtp(admin, email_cfg.get("from_address", ""), to, subject, body)
            else:
                from .email_send import send_email
                r = send_email(cfg, to=[to], cc=[], subject=subject, body=body)
            if r.get("ok"):
                delivered += 1
            else:
                last_err = r.get("error", "send failed")
        return {"sent": delivered > 0, "recipients": len(recipients),
                "delivered": delivered, "error": "" if delivered else last_err}
    except Exception as e:
        log.error("admin notification failed: %s", e)
        return {"sent": False, "recipients": 0, "delivered": 0, "error": str(e)}
