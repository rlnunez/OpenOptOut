"""
Email mode-switching grace period manager (Roadmap Item 11).

Preserves dual-inbox monitoring when an administrator changes email opt-out modes
(e.g., shared central inbox <-> per-user mail authorization) or updates mailbox
credentials. Because data brokers take 30–60 days to respond with confirmation
emails, in-flight removal requests sent under the previous mailbox configuration
must continue to be polled and resolved during the transition window.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import logging

log = logging.getLogger(__name__)

DEFAULT_GRACE_PERIOD_DAYS = 60
MAX_GRACE_PERIOD_DAYS = 180


def _parse_iso(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def get_email_grace_status(settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates whether an email grace period is currently active and calculates
    days remaining. If the grace period has expired, it automatically deactivates it.
    """
    grace = settings.get("email_grace_period")
    if not grace or not isinstance(grace, dict):
        return {"active": False, "days_remaining": 0, "previous_inbox": None}

    if not grace.get("active", False):
        return {
            "active": False,
            "days_remaining": 0,
            "previous_inbox": grace.get("previous_config", {}).get("imap_user")
            or grace.get("previous_config", {}).get("from_email"),
        }

    started_at = _parse_iso(grace.get("transition_started_at"))
    if not started_at:
        return {"active": False, "days_remaining": 0, "previous_inbox": None}

    grace_days = int(grace.get("grace_period_days", DEFAULT_GRACE_PERIOD_DAYS))
    now = datetime.now(timezone.utc)
    expires_at = started_at + timedelta(days=grace_days)

    if now >= expires_at:
        grace["active"] = False
        return {
            "active": False,
            "days_remaining": 0,
            "previous_inbox": grace.get("previous_config", {}).get("imap_user")
            or grace.get("previous_config", {}).get("from_email"),
        }

    days_remaining = max(1, (expires_at - now).days)
    prev = grace.get("previous_config", {})
    return {
        "active": True,
        "days_remaining": days_remaining,
        "grace_period_days": grace_days,
        "transition_started_at": started_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "previous_inbox": prev.get("imap_user") or prev.get("from_email"),
        "previous_mode": prev.get("mode", "shared"),
        "previous_config": prev,
    }


def maybe_snapshot_grace_period(
    current_settings: Dict[str, Any],
    new_email_config: Dict[str, Any],
    new_mode: Optional[str] = None,
    grace_days: int = DEFAULT_GRACE_PERIOD_DAYS,
) -> Optional[Dict[str, Any]]:
    """
    Checks if an existing active email configuration is changing (mode or credentials).
    If so, snapshots the old configuration into current_settings["email_grace_period"].
    Returns the created grace period dict, or None if no transition snapshot was needed.
    """
    old_email = current_settings.get("email", {})
    if not old_email:
        return None

    old_user = (
        old_email.get("imap_user")
        or old_email.get("smtp_username")
        or old_email.get("smtp_user")
        or ""
    ).strip()
    old_host = (old_email.get("imap_host") or old_email.get("smtp_host") or "").strip()
    old_mode = (old_email.get("mode") or "shared").strip()
    old_pw_enc = (
        old_email.get("imap_password_enc")
        or old_email.get("smtp_password_enc")
        or ""
    )

    # If the old email configuration had no valid host/user, there's nothing to grace-period poll
    if not old_host or not old_user:
        return None

    # Determine what is changing
    incoming_mode = (new_mode or new_email_config.get("mode") or old_mode).strip()
    incoming_user = (
        new_email_config.get("imap_user")
        or new_email_config.get("smtp_username")
        or new_email_config.get("smtp_user")
        or ""
    ).strip()
    incoming_host = (
        new_email_config.get("imap_host")
        or new_email_config.get("smtp_host")
        or ""
    ).strip()

    mode_changed = incoming_mode != old_mode
    account_changed = (incoming_user and incoming_user.lower() != old_user.lower()) or (
        incoming_host and incoming_host.lower() != old_host.lower()
    )

    if not (mode_changed or account_changed):
        return None

    log.info(
        "Email configuration transition detected (mode: %s -> %s, user: %s -> %s). Activating %d-day grace period.",
        old_mode,
        incoming_mode,
        old_user,
        incoming_user or old_user,
        grace_days,
    )

    previous_config = {
        "mode": old_mode,
        "provider": old_email.get("provider", ""),
        "imap_host": old_email.get("imap_host", ""),
        "imap_port": old_email.get("imap_port", 993),
        "imap_user": old_user,
        "imap_password_enc": old_pw_enc,
        "imap_ssl": old_email.get("imap_ssl", True),
        "imap_folder": old_email.get("imap_folder", "INBOX"),
        "from_email": old_email.get("from_email") or old_email.get("from_address", ""),
        "from_name": old_email.get("from_name", "PrivacyShield Removals"),
    }

    now_iso = datetime.now(timezone.utc).isoformat()
    grace_data = {
        "active": True,
        "transition_started_at": now_iso,
        "grace_period_days": grace_days,
        "previous_config": previous_config,
    }

    current_settings["email_grace_period"] = grace_data
    return grace_data


def dismiss_email_grace_period(settings: Dict[str, Any]) -> bool:
    """
    Deactivates any currently active grace period.
    """
    grace = settings.get("email_grace_period")
    if grace and isinstance(grace, dict):
        grace["active"] = False
        return True
    return False


def extend_email_grace_period(settings: Dict[str, Any], extra_days: int = 30) -> int:
    """
    Extends the active grace period by extra_days (up to MAX_GRACE_PERIOD_DAYS).
    Returns the new total grace_period_days.
    """
    grace = settings.get("email_grace_period")
    if not grace or not isinstance(grace, dict):
        return 0

    current_days = int(grace.get("grace_period_days", DEFAULT_GRACE_PERIOD_DAYS))
    new_days = min(MAX_GRACE_PERIOD_DAYS, current_days + extra_days)
    grace["grace_period_days"] = new_days
    grace["active"] = True
    return new_days
