"""
Emails the server sends to one person from its own notification inbox:
sign-in codes and sign-up codes. Never logs the address or the message.
"""
import logging

log = logging.getLogger(__name__)


def can_send() -> bool:
    """True when a notification inbox (a provider or SMTP) is set up."""
    from .settings_store import load_settings
    email = (load_settings().get("email") or {})
    provider = email.get("provider") or ""
    return bool((provider and provider != "smtp") or email.get("smtp_host"))


def send(to: str, subject: str, body: str) -> bool:
    """Send one plain-text email. Returns True if it was handed to the provider."""
    if not can_send():
        return False
    try:
        from .settings_store import load_settings
        from .email_send import send_email
        r = send_email(load_settings(), to=[to], cc=[], subject=subject, body=body)
        if not r.get("ok"):
            log.warning("system email not sent (%s)", (r.get("error") or "send failed")[:120])
        return bool(r.get("ok"))
    except Exception as e:  # never let a mail problem leak details to the caller
        log.warning("system email not sent (%s)", type(e).__name__)
        return False
