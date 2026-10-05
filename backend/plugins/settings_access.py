"""
Settings accessor for plugins.

Plugins can read non-secret settings and read/write their own scoped settings.
The critical invariant: secrets NEVER reach a plugin. Any settings key that
looks like a credential is refused, and plugin-scoped settings live in a
separate namespace from host settings.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

# Keys or substrings that must never be exposed to plugins, even with
# settings_read permission. Matched case-insensitively as substrings.
SECRET_MARKERS = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "private_key", "client_secret", "encryption_key", "bind_password",
    "ils_password", "smtp_pass", "imap_pass", "_enc", "credential",
)


def _looks_secret(key: str) -> bool:
    k = key.lower()
    return any(marker in k for marker in SECRET_MARKERS)


class PluginSettingsAccessor:
    """
    Bridges plugin settings requests to the host settings store.

    host_settings_loader() -> dict   (the full settings dict; may contain secrets)
    plugin_settings are stored under settings["plugin_settings"][plugin_id][key].
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
        matching a secret marker, returning None as if it doesn't exist.
        """
        if _looks_secret(key):
            # nosemgrep: python-logger-credential-disclosure -- logs setting name, not the value
            log.warning("Plugin attempted to read secret-like setting '%s' — refused", key)
            return None
        s = self._load()
        val = s.get(key)
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
            # nosemgrep: python-logger-credential-disclosure -- logs account name, not credentials
            log.error("get_email_credentials(%s) failed: %s", account_ref, e)
            return None
