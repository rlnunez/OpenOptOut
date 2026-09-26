"""
Host capability broker.

Implements the gRPC HostService that plugins call back into. Every method:
  1. Validates the session token (issued at handshake, unique per plugin run)
  2. Checks the plugin was granted the required permission
  3. Scopes all data access to that plugin (no cross-plugin access)

Storage is namespaced per plugin. Settings reads never return secrets.
This is the ONLY surface through which a sandboxed plugin can affect the host,
so it is deliberately small and every method is permission-gated.
"""

import logging
import time
from typing import Optional

from .permissions import Permission

log = logging.getLogger(__name__)


class CapabilityError(Exception):
    """Raised when a plugin requests something it isn't permitted to do."""
    pass


class MethodNotDeclaredError(CapabilityError):
    """
    Raised when a plugin calls a host method it did NOT declare in its manifest.
    This is treated as a security violation (not a benign permission error):
    the plugin is holding a permission but reaching for a method it never
    disclosed, so the manager records it, banners the admin, and disables it.
    """
    def __init__(self, plugin_id: str, method: str):
        self.plugin_id = plugin_id
        self.method = method
        super().__init__(f"method not declared in manifest: {method}")


class SessionRegistry:
    """
    Tracks active plugin sessions: token -> (plugin_id, granted_permissions,
    declared_methods). A token is created when a plugin is launched and revoked
    when it stops.
    """
    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def register(self, token: str, plugin_id: str, permissions: set[str],
                 methods: set[str] = None):
        self._sessions[token] = {
            "plugin_id": plugin_id,
            "permissions": set(permissions),
            "methods": set(methods or set()),
            "created_at": time.time(),
        }

    def revoke(self, token: str):
        self._sessions.pop(token, None)

    def validate(self, token: str, plugin_id: str) -> dict:
        s = self._sessions.get(token)
        if not s:
            raise CapabilityError("invalid or expired session token")
        if s["plugin_id"] != plugin_id:
            raise CapabilityError("session token does not match plugin id")
        return s

    def has_permission(self, token: str, plugin_id: str, permission: str) -> bool:
        s = self.validate(token, plugin_id)
        return permission in s["permissions"]

    def has_method(self, token: str, plugin_id: str, method: str) -> bool:
        s = self.validate(token, plugin_id)
        return method in s["methods"]


class CapabilityBroker:
    """
    Backs the gRPC HostService. Given a storage backend and settings accessor,
    it enforces permissions and scopes data per plugin.

    storage_backend must implement:
        get(plugin_id, key) -> Optional[str]
        set(plugin_id, key, value) -> None
        delete(plugin_id, key) -> None
        list(plugin_id, prefix) -> list[str]

    settings_accessor must implement:
        get_plugin_setting(plugin_id, key) -> Optional[str]
        set_plugin_setting(plugin_id, key, value) -> None
        get_global_nonsecret(key) -> Optional[str]   # returns None for secrets
        get_email_credentials(account_ref) -> Optional[dict]   # for email_credentials_get only
    """

    def __init__(self, sessions: SessionRegistry, storage_backend, settings_accessor,
                 event_sink=None, method_violation_sink=None, extended=None,
                 plugin_outbound_domains=None, email_provider_key_lookup=None):
        self.sessions  = sessions
        self.storage   = storage_backend
        self.settings  = settings_accessor
        self.event_sink = event_sink
        # Called when a plugin invokes a host method it never declared. The
        # manager wires this to record a violation, banner the admin, and disable.
        self.method_violation_sink = method_violation_sink
        # Broker read / request lifecycle / email trigger / fetch / scheduling.
        self.extended = extended
        # plugin_id -> set(declared outbound_domains), for http_fetch enforcement.
        self.plugin_outbound_domains = plugin_outbound_domains or {}
        # plugin_id -> its own confirmed provider_key (e.g. "gmail"), for
        # email_credentials_get's cross-provider guard below.
        self.email_provider_key_lookup = email_provider_key_lookup or (lambda pid: None)

    # ---- internal guards ----

    def _require(self, auth, permission: str, method: str) -> str:
        """
        Validate auth, the method allowlist, AND the permission. Returns
        plugin_id. Order matters: we check the declared-method allowlist first,
        because calling an undeclared method is a security violation even if the
        broad permission is held.
        """
        token     = auth.session_token
        plugin_id = auth.plugin_id

        # 1) Method must be declared in the manifest (least privilege).
        if not self.sessions.has_method(token, plugin_id, method):
            log.error("Plugin %s called UNDECLARED method '%s' — violation", plugin_id, method)
            if self.method_violation_sink:
                try:
                    self.method_violation_sink(plugin_id, method)
                except Exception as e:
                    log.error("method_violation_sink failed: %s", e)
            raise MethodNotDeclaredError(plugin_id, method)

        # 2) Permission backing that method must be granted.
        if permission and not self.sessions.has_permission(token, plugin_id, permission):
            log.warning("Plugin %s denied capability requiring '%s'", plugin_id, permission)
            raise CapabilityError(f"permission denied: {permission}")
        return plugin_id

    # ---- storage capability ----

    def storage_get(self, auth, key: str):
        pid = self._require(auth, Permission.STORAGE.value, "storage.get")
        val = self.storage.get(pid, key)
        return (val is not None, val or "")

    def storage_set(self, auth, key: str, value: str):
        pid = self._require(auth, Permission.STORAGE.value, "storage.set")
        # Guard against unbounded storage abuse
        if len(value) > 1_048_576:  # 1MB per value
            raise CapabilityError("value exceeds 1MB limit")
        self.storage.set(pid, key, value)

    def storage_delete(self, auth, key: str):
        pid = self._require(auth, Permission.STORAGE.value, "storage.delete")
        self.storage.delete(pid, key)

    def storage_list(self, auth, prefix: str):
        pid = self._require(auth, Permission.STORAGE.value, "storage.list")
        return self.storage.list(pid, prefix)

    # ---- settings capability ----

    def setting_get(self, auth, key: str):
        pid = self._require(auth, Permission.SETTINGS_READ.value, "settings.get")
        # Plugin-scoped settings take priority; fall back to global NON-SECRET.
        val = self.settings.get_plugin_setting(pid, key)
        if val is None:
            val = self.settings.get_global_nonsecret(key)  # returns None for secrets
        return (val is not None, val or "")

    def setting_set(self, auth, key: str, value: str):
        pid = self._require(auth, Permission.SETTINGS_WRITE.value, "settings.set")
        self.settings.set_plugin_setting(pid, key, value)

    # ---- email-provider credential lookup ────────────────────────────────────
    # A DELIBERATE, narrow exception to "plugins never see secrets": an
    # email-provider plugin cannot send anything at all without its account's
    # access token, and generic settings.get() permanently refuses anything
    # matching "credential"/"token" for every OTHER kind of plugin, by design.
    # Gated on: the EMAIL_PROVIDER permission (the same "trusted class"
    # already established for the read_pii+network exemption), the method
    # being declared in the manifest, AND — the actual cross-plugin guard —
    # the requested account_ref's stored provider matching THIS SPECIFIC
    # plugin process's own confirmed provider_key, so a Gmail plugin cannot
    # read an Outlook account's token just because both hold email_provider.

    def email_credentials_get(self, auth, account_ref: str):
        pid = self._require(auth, Permission.EMAIL_PROVIDER.value, "email.get_credentials")
        own_provider = self.email_provider_key_lookup(pid)
        if not own_provider:
            log.warning("Plugin %s requested email credentials but has no confirmed "
                       "provider_key yet — refusing", pid)
            return (False, "", "", "not authorized for any provider yet")
        creds = self.settings.get_email_credentials(account_ref)
        if not creds:
            return (False, "", "", f"no connected account '{account_ref}'")
        if creds.get("provider_key") != own_provider:
            log.warning("Plugin %s (provider '%s') requested account '%s' belonging to "
                       "provider '%s' — refusing", pid, own_provider, account_ref,
                       creds.get("provider_key"))
            return (False, "", "", "account belongs to a different provider")
        return (True, creds.get("access_token", ""), creds.get("token_type", "Bearer"), "")

    # ---- logging ----

    def log_message(self, auth, level: str, message: str):
        # Logging requires a valid session and the declared "log" method, but no
        # special permission.
        if not self.sessions.has_method(auth.session_token, auth.plugin_id, "log"):
            if self.method_violation_sink:
                try:
                    self.method_violation_sink(auth.plugin_id, "log")
                except Exception:
                    pass
            raise MethodNotDeclaredError(auth.plugin_id, "log")
        s = self.sessions.validate(auth.session_token, auth.plugin_id)
        pid = s["plugin_id"]
        lvl = {"debug": logging.DEBUG, "info": logging.INFO,
               "warning": logging.WARNING, "error": logging.ERROR}.get(level.lower(), logging.INFO)
        # Truncate to avoid log flooding
        log.log(lvl, "[plugin:%s] %s", pid, message[:2000])

    # ---- event emission ----

    def emit_event(self, auth, event_type: str, data: dict):
        pid = self._require(auth, Permission.EMIT_EVENTS.value, "emit_event")
        if self.event_sink:
            self.event_sink(source_plugin=pid, event_type=event_type, data=data)

    # ---- broker read (no member PII) ----

    def broker_get(self, auth, broker_id: int):
        pid = self._require(auth, Permission.BROKER_READ.value, "broker.get")
        return self.extended.broker_get(pid, broker_id)

    def broker_list(self, auth, limit: int):
        pid = self._require(auth, Permission.BROKER_READ.value, "broker.list")
        return self.extended.broker_list(pid, limit)

    def broker_history(self, auth, broker_id: int):
        pid = self._require(auth, Permission.BROKER_READ.value, "broker.history")
        return self.extended.broker_history(pid, broker_id)

    # ---- request lifecycle (status only, no member PII) ----

    def request_get_status(self, auth, request_id: int):
        pid = self._require(auth, Permission.REQUEST_READ.value, "request.get_status")
        return self.extended.request_get_status(pid, request_id)

    def request_mark_sent(self, auth, request_id: int, reason: str):
        pid = self._require(auth, Permission.REQUEST_WRITE.value, "request.mark_sent")
        return self.extended.request_mark_sent(pid, request_id, reason)

    def request_mark_confirmed(self, auth, request_id: int, reason: str):
        pid = self._require(auth, Permission.REQUEST_WRITE.value, "request.mark_confirmed")
        return self.extended.request_mark_confirmed(pid, request_id, reason)

    def request_mark_failed(self, auth, request_id: int, reason: str):
        pid = self._require(auth, Permission.REQUEST_WRITE.value, "request.mark_failed")
        return self.extended.request_mark_failed(pid, request_id, reason)

    # ---- constrained opt-out email trigger ----

    def trigger_optout_email(self, auth, request_id: int):
        pid = self._require(auth, Permission.TRIGGER_OPTOUT_EMAIL.value, "optout.trigger_email")
        return self.extended.trigger_optout_email(pid, request_id)

    # ---- host-mediated HTTP fetch ----

    def http_fetch(self, auth, method: str, url: str, body: str, headers: dict):
        pid = self._require(auth, Permission.HTTP_FETCH.value, "http.fetch")
        allowed = self.plugin_outbound_domains.get(pid, set())
        if not allowed:
            raise CapabilityError("no outbound_domains declared for this plugin")
        return self.extended.http_fetch(pid, method, url, body, headers, allowed)

    # ---- custom recheck scheduling ----

    def schedule_set_recheck(self, auth, request_id: int, recheck_after_ts: int, reason: str):
        pid = self._require(auth, Permission.SCHEDULE_WRITE.value, "schedule.set_recheck")
        return self.extended.schedule_set_recheck(pid, request_id, recheck_after_ts, reason)
