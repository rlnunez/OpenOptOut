"""
Manager permissions.

Four roles:
  super_admin  everything, always; the only role that can assign roles and
               permissions
  manager      a parent (own profile + profiles shared with them) plus the
               permissions below that a super admin grants
  parent       own profile + profiles shared with them
  member       a profile, usually without a login

A manager's effective permissions are:

    (manager defaults  ∪  granted to this manager)  −  revoked from this manager

The defaults are one editable set (settings["access"]["manager_defaults"],
falling back to DEFAULT_MANAGER_PERMISSIONS). Per-manager changes are stored on
the user (permissions_granted / permissions_revoked), so editing the defaults
changes every manager except where a super admin set something specific.

Some things are never delegated, however permissions are set: assigning
roles and permissions, the setup wizard, enabling/installing plugins and the
plugin-system switch, database migration and connection changes, and the
"reset all requests" danger zone. Those stay behind require_super_admin.
"""

import json
from typing import Iterable

from fastapi import Depends, HTTPException

# key -> label, group, description, sensitive (shown with a warning when granting)
PERMISSIONS = {
    "users.manage": {
        "group": "Users & access", "label": "Manage users", "sensitive": True,
        "description": "Create, edit and delete parent and member accounts, set their passwords, "
                       "and share profiles between parents. Setting a password means being able to "
                       "sign in as that person and see their family's data. Can't touch super "
                       "admins or managers, change roles, or share profiles with themselves.",
    },
    "users.registration": {
        "group": "Users & access", "label": "Registration & invite codes",
        "description": "Who can sign up (open, domain-restricted, invite-only, admin-only) and "
                       "invite codes.",
    },
    "members.view_all": {
        "group": "Member data", "label": "View all members' data", "sensitive": True,
        "description": "See every family's profiles, identity vault (names, addresses, phones, "
                       "emails), requests and logs, not just their own and those shared with them.",
    },
    "members.edit_all": {
        "group": "Member data", "label": "Edit all members' data", "sensitive": True,
        "description": "Change any family's profiles and identity vault. Includes viewing them.",
    },
    "brokers.manage": {
        "group": "Brokers", "label": "Manage brokers",
        "description": "Add, import, edit and delete brokers; enable or disable them; set "
                       "priorities; group them under parent companies.",
    },
    "brokers.automation": {
        "group": "Brokers", "label": "Automation scripts",
        "description": "Edit per-broker form selectors and use the test broker to check email "
                       "delivery.",
    },
    "scheduler.manage": {
        "group": "Operations", "label": "Run the scheduler",
        "description": "See scheduler status and runs, trigger or reload jobs, change the schedule, "
                       "and check the removal inbox now.",
    },
    "reporting.view": {
        "group": "Operations", "label": "View reports",
        "description": "Enrollment, opt-out, broker compliance and per-member reports, and CSV export.",
    },
    "help.edit": {
        "group": "Operations", "label": "Edit help notes",
        "description": "Add, edit and delete the custom notes on the Help page.",
    },
    "certificates.view": {
        "group": "Operations", "label": "Certificate status",
        "description": "Certificate-expiry alerts for LDAP, SIP2, SAML and HTTPS, and the HTTPS check.",
    },
    "email.manage": {
        "group": "System configuration", "label": "Email settings", "sensitive": True,
        "description": "The removal inbox: SMTP/IMAP settings and connected OAuth accounts.",
    },
    "branding.manage": {
        "group": "System configuration", "label": "Branding & appearance",
        "description": "Logo, colors, system name, welcome text, email footer and the announcement banner.",
    },
    "auth.providers": {
        "group": "System configuration", "label": "Sign-in providers", "sensitive": True,
        "description": "LDAP, SIP2, OIDC and SAML sign-in configuration.",
    },
    "settings.system": {
        "group": "System configuration", "label": "System settings", "sensitive": True,
        "description": "Privacy, identity-vault limits, automation settings and proxies.",
    },
    "database.view": {
        "group": "System configuration", "label": "Database status",
        "description": "Database health, tables, encryption status and connection settings "
                       "(read only; migrating or changing the connection stays with super admins).",
    },
    "plugins.view": {
        "group": "Plugins", "label": "View plugins",
        "description": "Installed plugins, their status, audit logs and violations, and plugin docs.",
    },
    "plugins.upload": {
        "group": "Plugins", "label": "Upload plugins",
        "description": "Use the plugin upload wizard. Uploaded plugins stay disabled until a "
                       "super admin enables them.",
    },
}

# The default set a new manager gets: day-to-day operations, nothing that
# exposes member data, credentials or security configuration.
DEFAULT_MANAGER_PERMISSIONS = [
    "brokers.manage", "brokers.automation", "scheduler.manage",
    "reporting.view", "help.edit", "certificates.view",
]

# Holding the key on the left also counts as holding the ones on the right.
IMPLIES = {"members.edit_all": {"members.view_all"}}


def clean(keys: Iterable[str]) -> list[str]:
    """Known permission keys only, deduplicated, in catalog order."""
    wanted = set(keys or [])
    return [k for k in PERMISSIONS if k in wanted]


def manager_defaults() -> list[str]:
    from . import settings_store
    stored = settings_store.load_settings().get("access", {}).get("manager_defaults")
    return clean(stored if stored is not None else DEFAULT_MANAGER_PERMISSIONS)


def save_manager_defaults(keys: Iterable[str]) -> list[str]:
    from . import settings_store
    keys = clean(keys)
    s = settings_store.load_settings()
    s.setdefault("access", {})["manager_defaults"] = keys
    with open(settings_store.SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)
    return keys


def _json_list(text) -> list[str]:
    try:
        return clean(json.loads(text or "[]"))
    except (ValueError, TypeError):
        return []


def user_overrides(user) -> tuple[list[str], list[str]]:
    """(granted, revoked) specific to this user."""
    return (_json_list(getattr(user, "permissions_granted", None)),
            _json_list(getattr(user, "permissions_revoked", None)))


def effective_permissions(user) -> list[str]:
    """Every permission this user holds. Super admins hold all of them;
    parents and members hold none."""
    if user is None:
        return []
    if user.is_super_admin:
        return list(PERMISSIONS)
    if not getattr(user, "is_manager", False):
        return []
    granted, revoked = user_overrides(user)
    keys = (set(manager_defaults()) | set(granted)) - set(revoked)
    for k in list(keys):
        keys |= IMPLIES.get(k, set())
    return clean(keys)


def has_permission(user, key: str) -> bool:
    if key not in PERMISSIONS:
        raise ValueError(f"unknown permission {key!r}")
    return key in effective_permissions(user)


def require_permission(*keys: str):
    """FastAPI dependency: the user must hold at least one of keys (super
    admins always pass)."""
    for k in keys:
        if k not in PERMISSIONS:
            raise ValueError(f"unknown permission {k!r}")

    from .auth import get_current_user

    def dependency(current_user=Depends(get_current_user)):
        held = effective_permissions(current_user)
        if not any(k in held for k in keys):
            labels = " or ".join(f"'{PERMISSIONS[k]['label']}'" for k in keys)
            raise HTTPException(403, f"This needs the {labels} permission")
        return current_user
    dependency.required_permissions = keys   # lets tests audit every route's gate
    return dependency
