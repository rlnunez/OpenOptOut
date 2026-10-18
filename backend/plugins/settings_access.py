"""
Settings accessor for plugins.

Plugins can read non-secret settings and read/write their own scoped settings.
The critical invariant: secrets NEVER reach a plugin. Any settings key that
looks like a credential is refused, and plugin-scoped settings live in a
separate namespace from host settings.
"""

import re
import logging
from typing import Optional, Any

log = logging.getLogger(__name__)

# Keys or substrings that must never be exposed to plugins, even with
# settings_read permission. Matched case-insensitively as substrings.
SECRET_MARKERS = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "private_key", "client_secret", "encryption_key", "bind_password",
    "ils_password", "smtp_pass", "imap_pass", "_enc", "credential",
    "proxy_url", "auth", "bearer", "cert", "cookie", "session",
)

_URL_CREDS_RE = re.compile(r"://[^:/\s]+:[^@/\s]+@")


def _looks_secret(key: str) -> bool:
    k = key.lower()
    return any(marker in k for marker in SECRET_MARKERS)


def _value_looks_secret(val: Any) -> bool:
    """True if val contains embedded credentials, e.g. scheme://user:pass@host."""
    if isinstance(val, str):
        if _URL_CREDS_RE.search(val):
            return True
    return False


class PluginSettingsAccessor:
    """
    Bridges plugin settings requests to the host settings store.

    host_settings_loader() -> dict   (the full settings dict; may contain secrets)
    plugin_settings are stored under settings["plugin_settings"][plugin_id][key].

    Security invariant (G16):
      Credential-bearing settings must always be stored under marker-matching keys
      (or nested dicts / external env files), never as bare non-secret scalars.
      get_global_nonsecret inspects both key names and string scalar contents to
      refuse secrets or embedded URL credentials.
    """

    def __init__(self, settings_loader, settings_saver):
        self._load = settings_loader
        self._save = settings_saver

    # ---- plugin-scoped settings ----

    def get_plugin_setting(self, plugin_id: str, key: str) -> Optional[str]:
        s = self._load()
        return (s.get("plugin_settings", {})
                 .get(plugin_id, {})
                 .get(key))

    def set_plugin_setting(self, plugin_id: str, key: str, value: str) -> None:
        s = self._load()
        ps = s.setdefault("plugin_settings", {}).setdefault(plugin_id, {})
        ps[key] = value
        self._save(s)

    # ---- global non-secret settings ----

    def get_global_nonsecret(self, key: str) -> Optional[str]:
        """
        Return a global setting ONLY if it is not a secret. Refuses anything
        matching a secret marker or containing embedded credentials, returning
        None as if it doesn't exist.
        """
        if _looks_secret(key):
            log.warning("Plugin attempted to read restricted setting '%s' — refused", key)
            return None
        s = self._load()
        val = s.get(key)
        # Refuse values that contain embedded credentials (e.g. http://user:pass@host)
        if _value_looks_secret(val):
            log.warning("Setting '%s' contains embedded credentials — refused", key)
            return None
        # Only return simple scalar values, never nested dicts that might
        # contain secrets deeper down.
        if isinstance(val, (str, int, float, bool)):
            return str(val)
        return None

    # ---- email-provider credential lookup (see broker.py's email_credentials_get
    # for the actual permission + cross-provider gating; this just fetches) ----

    def get_email_credentials(self, account_ref: str) -> Optional[dict]:
        """
        The stored OAuth tokens for account_ref, or None if nothing's
        connected there. Deliberately separate from get_global_nonsecret
        (which would refuse this outright — "credential" and "token" are both
        secret markers, on purpose) since this is the one legitimate, tightly
        gated path a plugin has to its own account's token.
        """
        s = self._load()
        try:
            from ..core import oauth_engine as oe
            return oe.load_tokens(s, account_ref)
        except Exception as e:
            log.error("Email setup lookup failed for account '%s': %s", account_ref, type(e).__name__)
            return None
