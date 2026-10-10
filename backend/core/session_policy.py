"""
Institutional session duration and Remember Me policy management.
Allows Super Admins to configure session lifetimes and remember-me behaviors
per role (e.g. username-only prefill for managers/admins vs extended sessions for users).
"""

from datetime import timedelta
from typing import Dict, Any, Optional
from .settings_store import load_settings, SETTINGS_FILE

DEFAULT_SESSION_POLICY: Dict[str, Any] = {
    "remember_me_enabled": True,
    "roles": {
        "super_admin": {
            "session_duration_hours": 8,
            "remember_me_allowed": True,
            "remember_me_mode": "username_only",  # "username_only" | "extend_session"
            "remember_me_duration_days": 1,
        },
        "manager": {
            "session_duration_hours": 8,
            "remember_me_allowed": True,
            "remember_me_mode": "username_only",
            "remember_me_duration_days": 3,
        },
        "parent": {
            "session_duration_hours": 24,
            "remember_me_allowed": True,
            "remember_me_mode": "extend_session",
            "remember_me_duration_days": 30,
        },
        "member": {
            "session_duration_hours": 24,
            "remember_me_allowed": True,
            "remember_me_mode": "extend_session",
            "remember_me_duration_days": 30,
        },
    },
}


def get_session_policy() -> Dict[str, Any]:
    """Retrieve institutional session duration and remember-me configuration."""
    s = load_settings()
    sec = s.get("security", {}).get("session_policy", {})
    policy: Dict[str, Any] = {
        "remember_me_enabled": bool(sec.get("remember_me_enabled", DEFAULT_SESSION_POLICY["remember_me_enabled"])),
        "roles": {},
    }
    sec_roles = sec.get("roles", {})
    for role, def_cfg in DEFAULT_SESSION_POLICY["roles"].items():
        r_cfg = sec_roles.get(role, {})
        policy["roles"][role] = {
            "session_duration_hours": int(r_cfg.get("session_duration_hours", def_cfg["session_duration_hours"])),
            "remember_me_allowed": bool(r_cfg.get("remember_me_allowed", def_cfg["remember_me_allowed"])),
            "remember_me_mode": str(r_cfg.get("remember_me_mode", def_cfg["remember_me_mode"])),
            "remember_me_duration_days": int(r_cfg.get("remember_me_duration_days", def_cfg["remember_me_duration_days"])),
        }
    return policy


def compute_session_delta(role: str, remember_me: bool = False) -> timedelta:
    """Compute the appropriate JWT expiration timedelta based on role and remember_me flag."""
    policy = get_session_policy()
    role_key = str(role or "parent").lower()
    r_cfg = policy["roles"].get(role_key, DEFAULT_SESSION_POLICY["roles"].get("parent"))
    if not r_cfg:
        r_cfg = DEFAULT_SESSION_POLICY["roles"]["parent"]

    is_remember = bool(remember_me and policy.get("remember_me_enabled", True) and r_cfg.get("remember_me_allowed", True))
    if is_remember and r_cfg.get("remember_me_mode") == "extend_session":
        days = max(1, r_cfg.get("remember_me_duration_days", 30))
        return timedelta(days=days)

    hours = max(1, r_cfg.get("session_duration_hours", 24))
    return timedelta(hours=hours)


def create_user_token(user: Any, remember_me: bool = False) -> str:
    """Issue a signed JWT access token for a user with role-specific expiration policy."""
    from .auth import create_access_token
    role = getattr(getattr(user, "role", None), "value", str(getattr(user, "role", "") or "parent"))
    delta = compute_session_delta(role, remember_me=remember_me)
    return create_access_token({"sub": user.email}, expires_delta=delta)
