"""
Institutional session duration and Remember Me policy management.
Allows Super Admins to configure session lifetimes and remember-me behaviors
per role (e.g. username-only prefill for managers/admins vs extended sessions for users).
"""

from datetime import timedelta
from typing import Dict, Any, Optional
from .settings_store import load_settings, SETTINGS_FILE

MAX_REMEMBER_ME_DURATION_DAYS = 30   # NIST SP 800-63B rev. 4 S2.2.3: AAL1 session ceiling

DEFAULT_SESSION_POLICY: Dict[str, Any] = {
    "remember_me_enabled": True,
    "roles": {
        "super_admin": {
            "session_duration_hours": 8,
            "remember_me_allowed": True,
            "remember_me_mode": "username_only",  # "username_only" | "extend_session"
            "remember_me_duration_days": 1,
            "idle_timeout_minutes": 60,   # NIST SP 800-63B rev. 4 S2.2.3 (default; admin may reduce or disable)
        },
        "manager": {
            "session_duration_hours": 8,
            "remember_me_allowed": True,
            "remember_me_mode": "username_only",
            "remember_me_duration_days": 3,
            "idle_timeout_minutes": 60,
        },
        "parent": {
            "session_duration_hours": 24,
            "remember_me_allowed": True,
            "remember_me_mode": "extend_session",
            "remember_me_duration_days": 30,
            "idle_timeout_minutes": 60,
        },
        "member": {
            "session_duration_hours": 24,
            "remember_me_allowed": True,
            "remember_me_mode": "extend_session",
            "remember_me_duration_days": 30,
            "idle_timeout_minutes": 60,
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
            "remember_me_duration_days": min(MAX_REMEMBER_ME_DURATION_DAYS, max(1, int(r_cfg.get("remember_me_duration_days", def_cfg["remember_me_duration_days"])))),
            "idle_timeout_minutes": max(0, int(r_cfg.get("idle_timeout_minutes", def_cfg["idle_timeout_minutes"]))),
        }
    return policy


def get_idle_timeout_minutes(role: str) -> int:
    """Defaults to 60 minutes per role (NIST SP 800-63B rev. 4 S2.2.3); an
    admin can lower it or set 0 to disable it entirely."""
    policy = get_session_policy()
    role_key = str(role or "parent").lower()
    r_cfg = policy["roles"].get(role_key, DEFAULT_SESSION_POLICY["roles"]["parent"])
    return int(r_cfg.get("idle_timeout_minutes", 0))


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


def create_user_token(user: Any, db: Any = None, request: Any = None, remember_me: bool = False) -> str:
    """
    Issue a signed JWT access token for a user with role-specific expiration
    policy. When `db` is given, also records a UserSession row (keyed by a
    fresh `jti` claim embedded in the token) so the session can be listed and
    individually revoked later (core/auth.py's session check,
    routers/auth.py's /sessions endpoints) — on top of the existing
    account-wide token_version mechanism, not instead of it.
    """
    import secrets
    from .auth import create_access_token
    role = getattr(getattr(user, "role", None), "value", str(getattr(user, "role", "") or "parent"))
    delta = compute_session_delta(role, remember_me=remember_me)
    token_ver = getattr(user, "token_version", 0) or 0
    claims = {"sub": user.email, "token_version": token_ver}

    if db is not None:
        from datetime import datetime
        from ..models.database import UserSession
        jti = secrets.token_urlsafe(32)
        claims["jti"] = jti
        ip = None
        user_agent = None
        if request is not None:
            try:
                ip = request.client.host if request.client else None
                user_agent = (request.headers.get("user-agent") or "")[:255] or None
            except Exception:
                pass
        db.add(UserSession(
            user_id=user.id, jti=jti, expires_at=datetime.utcnow() + delta,
            ip=ip, user_agent=user_agent, remember_me=bool(remember_me),
        ))
        db.commit()

    return create_access_token(claims, expires_delta=delta)


def revoke_all_sessions(db: Any, user_id: int, except_jti: Optional[str] = None) -> None:
    """Mark every one of a user's tracked sessions revoked (ASVS 7.4.2/7.4.3/
    7.4.5) — called alongside a token_version bump so the UserSession table
    stays an accurate picture of what's actually still valid, not just an
    implicit side effect of the version check. `except_jti` keeps one session
    alive (e.g. the request's own, right after a self-service password change
    that reissues a fresh token for the caller)."""
    from datetime import datetime
    from ..models.database import UserSession
    q = db.query(UserSession).filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_jti:
        q = q.filter(UserSession.jti != except_jti)
    q.update({"revoked_at": datetime.utcnow()}, synchronize_session=False)
    db.commit()
