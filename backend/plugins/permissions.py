"""
Plugin permission model.

Permissions are declared in a plugin's manifest and granted explicitly by a
super admin when the plugin is enabled. Every host capability call validates
the caller's session token AND that the permission was granted.

Because plugins run in isolated subprocesses (see runner/), a plugin that was
not granted a permission physically cannot obtain the corresponding data —
the host refuses the RPC and returns nothing. This is real enforcement, not
advisory: the plugin has no in-process access to the host at all.
"""

from enum import Enum
from dataclasses import dataclass, field, fields
from typing import Optional


class Permission(str, Enum):
    """
    The complete set of capabilities a plugin may request.
    Keep this list tight — every permission is attack surface.
    """
    READ_PII        = "read_pii"        # receive member field values in hooks
    STORAGE         = "storage"         # plugin-scoped key/value storage
    SETTINGS_READ   = "settings_read"   # read non-secret settings
    SETTINGS_WRITE  = "settings_write"  # write plugin-scoped settings
    NETWORK         = "network"         # make outbound network calls (sandbox-enforced)
    EMIT_EVENTS     = "emit_events"     # push custom events into the host bus
    FILL_FORMS      = "fill_forms"      # register a form-filling strategy
    PARSE_EMAIL     = "parse_email"     # register an email parser
    SOLVE_CAPTCHA   = "solve_captcha"   # register a CAPTCHA-solving strategy
    EMAIL_PROVIDER  = "email_provider"  # register an email transport (send/receive)
    RECEIVE_EVENTS  = "receive_events"  # receive lifecycle event notifications
    BROKER_READ           = "broker_read"            # read-only broker lookups (no member data)
    REQUEST_READ          = "request_read"           # read a request's status (no member PII)
    REQUEST_WRITE         = "request_write"          # mark a request sent/confirmed/failed
    TRIGGER_OPTOUT_EMAIL  = "trigger_optout_email"    # send the EXISTING opt-out email template
    HTTP_FETCH            = "http_fetch"              # host-mediated outbound HTTP to declared domains
    SCHEDULE_WRITE        = "schedule_write"          # set a custom recheck time

    @classmethod
    def all(cls) -> list[str]:
        return [p.value for p in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls._value2member_map_


# Human-readable descriptions + risk level, surfaced in the admin UI so the
# person enabling a plugin understands exactly what they're granting.
PERMISSION_INFO = {
    Permission.READ_PII.value: {
        "label": "Read personal data",
        "risk": "high",
        "description": "Receives member names, addresses, phones, and emails in hook calls. "
                       "Without this, the plugin only sees redacted/structural data.",
    },
    Permission.STORAGE.value: {
        "label": "Plugin storage",
        "risk": "low",
        "description": "Read and write the plugin's own isolated key/value store. "
                       "Cannot access other plugins' data or host tables.",
    },
    Permission.SETTINGS_READ.value: {
        "label": "Read settings",
        "risk": "low",
        "description": "Read non-secret configuration values. Secrets (passwords, keys) are never exposed.",
    },
    Permission.SETTINGS_WRITE.value: {
        "label": "Write settings",
        "risk": "medium",
        "description": "Create or modify the plugin's own settings values.",
    },
    Permission.NETWORK.value: {
        "label": "Network access",
        "risk": "high",
        "description": "Make outbound network connections. When OS sandboxing is active, "
                       "network is blocked unless this permission is granted.",
    },
    Permission.EMIT_EVENTS.value: {
        "label": "Emit events",
        "risk": "medium",
        "description": "Push custom events into the host event bus, which other plugins may receive.",
    },
    Permission.FILL_FORMS.value: {
        "label": "Custom form filling",
        "risk": "medium",
        "description": "Provide a custom strategy for filling broker opt-out forms. The plugin "
                       "describes actions; the host executes them in its own sandboxed browser.",
    },
    Permission.PARSE_EMAIL.value: {
        "label": "Email parsing",
        "risk": "medium",
        "description": "Interpret inbound confirmation emails and match them to pending requests.",
    },
    Permission.SOLVE_CAPTCHA.value: {
        "label": "CAPTCHA solving",
        "risk": "low",
        "description": "Receive CAPTCHA challenges during opt-outs and return a solution (or "
                       "defer to a human). On its OWN this is low-risk: a local solver — a bundled "
                       "model or a local human-in-the-loop — makes no outbound calls and leaks "
                       "nothing (the sandbox blocks network without the 'network' permission). It "
                       "becomes HIGH-risk only when combined with 'network', which means the solver "
                       "sends the challenge (and possibly page context) to an outside service.",
    },
    Permission.EMAIL_PROVIDER.value: {
        "label": "Email provider (transport)",
        "risk": "high",
        "description": "Register an email transport (Gmail, Outlook, Yahoo, IMAP/SMTP, ...) that "
                       "sends opt-out emails and reads confirmations. Email providers are a TRUSTED "
                       "CLASS: sending member identifiers to a mail API is their legitimate job, so "
                       "they are allowed the read_pii + network combination. In exchange the host "
                       "code-inspects them for hidden or hardcoded recipients and ENFORCES the "
                       "actual recipient at send time — the plugin may only send to the address the "
                       "host supplies, and the host verifies what it reports sending to.",
    },
    Permission.RECEIVE_EVENTS.value: {
        "label": "Receive events",
        "risk": "low",
        "description": "Be notified of lifecycle events (opt-out sent, confirmation received, scheduled ticks).",
    },
    Permission.BROKER_READ.value: {
        "label": "Read broker data",
        "risk": "low",
        "description": "Look up broker info (name, opt-out method, difficulty, status) and aggregate "
                       "opt-out stats. Never returns member names, addresses, or other PII.",
    },
    Permission.REQUEST_READ.value: {
        "label": "Read request status",
        "risk": "low",
        "description": "Read a removal request's status (pending/sent/confirmed/failed) and timestamps. "
                       "Never returns member PII — only the request's own bookkeeping fields.",
    },
    Permission.REQUEST_WRITE.value: {
        "label": "Change request status",
        "risk": "high",
        "description": "Mark a removal request as sent, confirmed, or failed. This changes real "
                       "opt-out records. Every write is logged to the audit trail with a before/after "
                       "diff of the status fields (never member PII).",
    },
    Permission.TRIGGER_OPTOUT_EMAIL.value: {
        "label": "Trigger opt-out email",
        "risk": "high",
        "description": "Send the EXISTING opt-out email template for one pending request, using the "
                       "host's own SMTP configuration. The plugin cannot write custom content, choose a "
                       "different recipient, or send unrelated email — only trigger the same flow the "
                       "opt-out engine itself uses.",
    },
    Permission.HTTP_FETCH.value: {
        "label": "Host-mediated HTTP fetch",
        "risk": "medium",
        "description": "Ask the host to make one outbound HTTP request to a domain the plugin declared "
                       "in its manifest, and return the response. The plugin never opens its own network "
                       "socket — the host makes the call, so it can log and restrict it to declared domains.",
    },
    Permission.SCHEDULE_WRITE.value: {
        "label": "Custom recheck scheduling",
        "risk": "medium",
        "description": "Set a custom recheck-after time for one confirmed request, instead of the "
                       "default interval. Logged to the audit trail with the old and new time.",
    },
}


# Which hook each permission unlocks. Used to validate that a plugin declaring
# a hook also requested the matching permission.
HOOK_PERMISSION = {
    "fill_form":     Permission.FILL_FORMS.value,
    "parse_email":   Permission.PARSE_EMAIL.value,
    "on_event":      Permission.RECEIVE_EVENTS.value,
    "solve_captcha": Permission.SOLVE_CAPTCHA.value,
    "email_provider": Permission.EMAIL_PROVIDER.value,
}


# ── Method-level allowlist catalog ────────────────────────────────────────────
# The complete set of host/SDK methods a plugin can call, each mapped to the
# permission that governs it and a human-readable description for the enable
# page. A plugin's manifest must list EXACTLY the methods it will call; the
# broker refuses (and flags as a violation) any call to a method not in the
# manifest, even if the plugin holds the broader permission.
#
# This is least-privilege at method granularity: holding `storage` no longer
# implies all four storage methods — the plugin must name each one it uses.
HOST_METHODS = {
    "storage.get":    {"permission": Permission.STORAGE.value,        "label": "Read its own stored values"},
    "storage.set":    {"permission": Permission.STORAGE.value,        "label": "Write its own stored values"},
    "storage.delete": {"permission": Permission.STORAGE.value,        "label": "Delete its own stored values"},
    "storage.list":   {"permission": Permission.STORAGE.value,        "label": "List its own stored keys"},
    "settings.get":   {"permission": Permission.SETTINGS_READ.value,  "label": "Read non-secret settings"},
    "settings.set":   {"permission": Permission.SETTINGS_WRITE.value, "label": "Write its own settings"},
    "log":            {"permission": None,                            "label": "Write to the plugin log"},
    "emit_event":     {"permission": Permission.EMIT_EVENTS.value,    "label": "Emit events to the host"},

    # ── Broker data (read-only lookup) ──────────────────────────────────────
    "broker.get":     {"permission": Permission.BROKER_READ.value,    "label": "Look up one broker's info (name, method, difficulty, status)"},
    "broker.list":     {"permission": Permission.BROKER_READ.value,    "label": "List brokers (id/name/method/difficulty/status only)"},
    "broker.history":  {"permission": Permission.BROKER_READ.value,    "label": "Read a broker's aggregate opt-out stats (counts only, no member data)"},

    # ── Request lifecycle (high-risk write, audited with diffs) ────────────
    "request.get_status":   {"permission": Permission.REQUEST_READ.value,  "label": "Read a request's status (no member PII)"},
    "request.mark_sent":     {"permission": Permission.REQUEST_WRITE.value, "label": "Mark a pending request as sent"},
    "request.mark_confirmed":{"permission": Permission.REQUEST_WRITE.value, "label": "Mark a sent request as confirmed"},
    "request.mark_failed":   {"permission": Permission.REQUEST_WRITE.value, "label": "Mark a request as failed"},

    # ── Constrained opt-out email trigger (not freeform email) ─────────────
    "optout.trigger_email": {"permission": Permission.TRIGGER_OPTOUT_EMAIL.value,
                             "label": "Send the EXISTING opt-out email template for one pending request (no custom content, no other recipients)"},

    # ── Host-mediated HTTP fetch (host makes the call, not the plugin) ─────
    "http.fetch": {"permission": Permission.HTTP_FETCH.value,
                   "label": "Ask the host to make one outbound HTTP GET/POST to a declared domain and return the response"},

    # ── Custom recheck scheduling ───────────────────────────────────────────
    "schedule.set_recheck": {"permission": Permission.SCHEDULE_WRITE.value,
                             "label": "Set a custom recheck-after time for one confirmed request"},

    # ── Email-provider credential lookup (own account's token only) ────────
    "email.get_credentials": {"permission": Permission.EMAIL_PROVIDER.value,
                              "label": "Read the current access token for its own connected email account"},
}

# Map a manifest method name -> the broker capability it authorizes. Used by the
# broker to check the incoming call against the plugin's declared method set.
METHOD_CATALOG = set(HOST_METHODS.keys())

# Methods whose writes are treated as HIGH-RISK: recorded to the audit trail
# with a before/after diff (values only, never member PII) in addition to the
# normal violation/audit machinery every method already gets.
HIGH_RISK_WRITE_METHODS = {
    "request.mark_sent", "request.mark_confirmed", "request.mark_failed",
    "optout.trigger_email", "schedule.set_recheck",
}


# ── Plugin types ──────────────────────────────────────────────────────────────
# Every plugin declares one type in its manifest ("type": "email", ...). The type
# decides which subdirectory of the plugins root it installs into
# (<root>/<type>/<id>/) and which rules it must satisfy. The directory is a
# convenience; these rules are what make the type a real boundary.
#
#   required_hooks       the plugin must declare these hooks
#   allowed_permissions  the only permissions this type may request. Host API
#                        methods each need a permission (HOST_METHODS), so this
#                        also limits which APIs the type can call.
#   data_only            the plugin is data the host loads (translations, design
#                        tokens), never code: no entrypoint, hooks, permissions,
#                        methods or egress, and it is never launched as a process.
_P = lambda *names: frozenset(names)
PLUGIN_TYPES = {
    "email": {
        "label": "Email providers", "required_hooks": {"email_provider"},
        # Sending opt-outs means member identifiers go to the mail API.
        "allowed_permissions": _P("email_provider", "read_pii", "network", "settings_read", "storage"),
    },
    "captcha": {
        "label": "CAPTCHA solvers", "required_hooks": {"solve_captcha"},
        # A challenge carries no member data; a solver may call a solving service.
        "allowed_permissions": _P("solve_captcha", "network", "http_fetch", "settings_read", "storage"),
    },
    "forms": {
        "label": "Form handlers", "required_hooks": {"fill_form"},
        # Fills member fields into a page the host already has open: no network.
        "allowed_permissions": _P("fill_forms", "read_pii", "broker_read", "settings_read", "storage"),
    },
    "discovery": {
        "label": "Discovery bots",   # no discovery hook exists yet
        # Searching for a member's listings needs their name and the network, so
        # read_pii + network still goes through the declared-exception gate.
        "allowed_permissions": _P("read_pii", "network", "http_fetch", "broker_read",
                                  "settings_read", "storage", "emit_events"),
    },
    "brokers": {
        "label": "Broker add-ons",   # broker specs (roadmap item 1)
        "allowed_permissions": _P("broker_read", "settings_read", "storage", "fill_forms", "read_pii"),
    },
    "themes":    {"label": "Themes",         "data_only": True, "allowed_permissions": _P()},
    "languages": {"label": "Language packs", "data_only": True, "allowed_permissions": _P()},
    "general": {
        "label": "General",   # event hooks, email parsers, anything else
        # Everything except the permissions that belong to a specialized type.
        "allowed_permissions": frozenset(p.value for p in Permission)
                               - {"email_provider", "solve_captcha", "fill_forms"},
    },
}

# Hooks that belong to exactly one type. A plugin declaring one of these must
# be of that type, so e.g. a "general" plugin can't quietly act as an email
# provider (the trusted class with its own egress exemptions).
SPECIALIZED_HOOKS = {
    "email_provider": "email",
    "solve_captcha":  "captcha",
    "fill_form":      "forms",
}


def infer_plugin_type(hooks) -> str:
    """Best-guess type for a manifest that predates the `type` field."""
    for hook in hooks or []:
        if hook in SPECIALIZED_HOOKS:
            return SPECIALIZED_HOOKS[hook]
    return "general"


def methods_for_permission(permission: str) -> list[str]:
    """All host methods a given permission could unlock (for UI display)."""
    return [m for m, info in HOST_METHODS.items() if info["permission"] == permission]



def _as_text(v, name: str) -> str:
    """Manifest text field: keep strings, turn plain numbers/booleans into text,
    treat null as empty, and reject lists/objects."""
    if isinstance(v, str):
        return v
    if v is None:
        return ""
    if isinstance(v, (bool, int, float)):
        return str(v).lower() if isinstance(v, bool) else str(v)
    raise ValueError(f"manifest field '{name}' must be text, not {type(v).__name__}")

@dataclass
class PluginManifest:
    """Parsed and validated plugin manifest."""
    id:          str
    name:        str
    version:     str
    author:      str
    description: str = ""
    api_version: str = "1.0"
    type:        str = ""              # one of PLUGIN_TYPES; "" = legacy manifest
    permissions: list[str] = field(default_factory=list)
    hooks:       list[str] = field(default_factory=list)
    methods:     list[str] = field(default_factory=list)   # exact host methods it calls
    events:      list[str] = field(default_factory=list)   # event types it expects (on_event)
    outbound_domains: list[str] = field(default_factory=list)  # allowed egress (if network)
    entrypoint:  str = "plugin.py"     # file the runner executes
    # Resource limits (operator can override; these are per-plugin ceilings)
    max_memory_mb:   int = 256
    max_cpu_seconds: int = 30          # per hook call
    timeout_seconds: int = 20          # per hook call wall-clock
    # read_pii + network is BLOCKED BY DEFAULT (a plugin that can see member
    # data and also reach the network is the combination that can exfiltrate
    # it). A plugin that genuinely needs both must set this to true AND supply
    # a written justification — see validate() below. This does not itself
    # grant anything; it only unlocks the ADMIN's ability to consider granting
    # both permissions, via a distinct, separately-confirmed enable step.
    requires_pii_network_exception: bool = False
    pii_network_justification: str = ""
    # Broker add-on specific metadata (Roadmap Item 1)
    spec_file: str = "spec.json"
    broker_id: str = ""
    captcha_plugin_id: str = ""
    is_property_broker: bool = False
    difficulty: str = "medium"

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty = valid)."""
        errors = []
        if not self.id or not self.id.replace("-", "").replace("_", "").isalnum():
            errors.append("id must be a non-empty alphanumeric slug (dashes/underscores allowed)")
        if not self.name:
            errors.append("name is required")
        if not self.version:
            errors.append("version is required")
        if not self.author:
            errors.append("author is required")
        errors.extend(self._type_errors())
        for p in self.permissions:
            if not Permission.is_valid(p):
                errors.append(f"unknown permission: {p}")
        for h in self.hooks:
            if h not in HOOK_PERMISSION:
                errors.append(f"unknown hook: {h}")
            else:
                required = HOOK_PERMISSION[h]
                if required not in self.permissions:
                    errors.append(f"hook '{h}' requires permission '{required}'")
        # Method-level allowlist validation
        for m in self.methods:
            if m not in METHOD_CATALOG:
                errors.append(f"unknown host method: {m}")
                continue
            needed = HOST_METHODS[m]["permission"]
            if needed and needed not in self.permissions:
                errors.append(f"method '{m}' requires permission '{needed}'")
        # A plugin that declares no methods but requests capability permissions
        # is suspicious but allowed (it simply won't be able to call anything).
        if self.max_memory_mb < 32 or self.max_memory_mb > 2048:
            errors.append("max_memory_mb must be between 32 and 2048")
        # Outbound domains only meaningful if network is granted
        if self.outbound_domains and Permission.NETWORK.value not in self.permissions:
            errors.append("outbound_domains declared but 'network' permission not requested")

        # ── read_pii + network is BLOCKED BY DEFAULT ──────────────────────────
        # This is the combination that lets a plugin see member data AND reach
        # the network to send it somewhere. A plugin requesting both must
        # explicitly flag the narrow exception path with a real justification;
        # otherwise the manifest is invalid and the plugin cannot be installed.
        has_pii = Permission.READ_PII.value in self.permissions
        has_net = Permission.NETWORK.value in self.permissions
        # Email-provider plugins are a TRUSTED CLASS: sending member identifiers to
        # a mail API is their legitimate function, so read_pii + network is expected
        # rather than a red flag. They are exempt from the blanket block, but NOT
        # from scrutiny — the host code-inspects them for hidden/hardcoded
        # recipients (see the manifest inspector) and enforces the actual recipient
        # at send time. Outbound domains must still be declared.
        is_email_provider = Permission.EMAIL_PROVIDER.value in self.permissions and \
            "email_provider" in self.hooks
        if has_pii and has_net and not is_email_provider:
            if not self.requires_pii_network_exception:
                errors.append(
                    "manifest requests BOTH 'read_pii' and 'network' — this combination is "
                    "blocked by default because it can exfiltrate member data. Set "
                    "requires_pii_network_exception=true and provide pii_network_justification "
                    "to declare the narrow exception, which still requires separate admin approval."
                )
            elif not self.pii_network_justification or len(self.pii_network_justification.strip()) < 20:
                errors.append(
                    "requires_pii_network_exception is set but pii_network_justification is "
                    "missing or too short (must clearly explain why both are needed)"
                )
            if not self.outbound_domains:
                errors.append(
                    "the read_pii + network exception requires outbound_domains to be declared "
                    "(no undeclared-destination egress is allowed even under the exception)"
                )
        # Email providers must still declare their outbound domains (which mail API
        # they talk to), so the host and admin can see and the sandbox can enforce.
        if is_email_provider and has_net and not self.outbound_domains:
            errors.append(
                "email-provider plugin with 'network' must declare outbound_domains "
                "(the mail API/host it sends through)"
            )
        # A wildcard ("*") outbound domain means "operator-defined host" — only an
        # email provider may use it (e.g. a generic SMTP plugin whose server the
        # operator configures). It is NOT a blanket "reach anywhere": the host must
        # bind the actual allowed destination to the operator's configured
        # smtp_host/imap_host at enable time. A NON-email plugin may never wildcard.
        if "*" in (self.outbound_domains or []):
            if not is_email_provider:
                errors.append(
                    "wildcard '*' in outbound_domains is only allowed for email-provider "
                    "plugins (operator-defined mail server); this plugin may not use it"
                )
            # else: allowed, but the host must bind the concrete host at enable time.
        if self.effective_type == "brokers":
            if ".." in (self.spec_file or "") or (self.spec_file or "").startswith(("/", "\\")):
                errors.append("spec_file must be a relative path without directory traversal")
        return errors

    @property
    def effective_type(self) -> str:
        """The declared type, or for a legacy manifest the type inferred from
        its hooks. This is what decides where the plugin is installed."""
        return self.type or infer_plugin_type(self.hooks)

    @property
    def type_inferred(self) -> bool:
        return not self.type

    @property
    def is_data_only(self) -> bool:
        return bool(PLUGIN_TYPES.get(self.effective_type, {}).get("data_only"))

    def _type_errors(self) -> list[str]:
        # Which permissions a type may request is checked for every manifest,
        # including legacy ones (no `type`), against the type inferred from its
        # hooks: it's a security limit. The structural rules below apply once a
        # manifest declares its type, so older plugins keep installing.
        errors = []
        allowed = PLUGIN_TYPES.get(self.effective_type, {}).get("allowed_permissions")
        if allowed is not None and not PLUGIN_TYPES.get(self.effective_type, {}).get("data_only"):
            for p in self.permissions:
                if Permission.is_valid(p) and p not in allowed:
                    errors.append(f"a '{self.effective_type}' plugin may not request the '{p}' "
                                  f"permission (allowed: {', '.join(sorted(allowed)) or 'none'})")
        if not self.type:
            return errors
        rules = PLUGIN_TYPES.get(self.type)
        if rules is None:
            return [f"unknown plugin type '{self.type}' "
                    f"(expected one of: {', '.join(PLUGIN_TYPES)})"]
        for hook in rules.get("required_hooks", ()):
            if hook not in self.hooks:
                errors.append(f"a '{self.type}' plugin must declare the '{hook}' hook")
        for hook in self.hooks:
            owner = SPECIALIZED_HOOKS.get(hook)
            if owner and owner != self.type:
                errors.append(f"the '{hook}' hook is only allowed in '{owner}' plugins, "
                              f"not '{self.type}'")
        if rules.get("data_only"):
            for fld in ("hooks", "permissions", "methods", "outbound_domains"):
                if getattr(self, fld):
                    errors.append(f"a '{self.type}' plugin is data only and may not declare {fld}")
            if self.entrypoint:
                errors.append(f"a '{self.type}' plugin is data only and may not have an entrypoint")
        return errors

    @property
    def has_wildcard_outbound(self) -> bool:
        """True if this (email-provider) plugin defers its outbound host to
        operator configuration. The host must bind the real host at enable time."""
        return "*" in (self.outbound_domains or [])

    @classmethod
    def from_dict(cls, d: dict) -> "PluginManifest":
        if not isinstance(d, dict):
            raise ValueError("manifest must be a JSON object")
        ptype = d.get("type", "") or ""
        # Data-only types and declarative broker add-ons have no code, so no default entrypoint.
        is_declarative_broker = (ptype == "brokers" and "entrypoint" not in d)
        default_entry = "" if (PLUGIN_TYPES.get(ptype, {}).get("data_only") or is_declarative_broker) else "plugin.py"
        m = cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            version=d.get("version", ""),
            author=d.get("author", ""),
            description=d.get("description", ""),
            api_version=d.get("api_version", "1.0"),
            type=ptype,
            permissions=d.get("permissions", []),
            hooks=d.get("hooks", []),
            methods=d.get("methods", []),
            events=d.get("events", []),
            outbound_domains=d.get("outbound_domains", []),
            entrypoint=d.get("entrypoint", default_entry),
            max_memory_mb=int(d.get("max_memory_mb", 256)),
            max_cpu_seconds=int(d.get("max_cpu_seconds", 30)),
            timeout_seconds=int(d.get("timeout_seconds", 20)),
            requires_pii_network_exception=bool(d.get("requires_pii_network_exception", False)),
            pii_network_justification=d.get("pii_network_justification", ""),
            spec_file=d.get("spec_file", "spec.json"),
            broker_id=d.get("broker_id", ""),
            captcha_plugin_id=d.get("captcha_plugin_id", ""),
            is_property_broker=bool(d.get("is_property_broker", False)),
            difficulty=d.get("difficulty", "medium"),
        )
        # Manifests come from uploaded plugins. A number where text is expected
        # (e.g. "version": 1.0) used to crash validate() with AttributeError,
        # breaking plugin scanning and the Plugins page. Plain numbers/booleans are
        # turned into text (so manifests stored by older versions still load);
        # anything else is rejected with a ValueError, which callers report.
        for f in fields(m):
            v = getattr(m, f.name)
            if f.type is str:
                setattr(m, f.name, _as_text(v, f.name))
            elif f.type == list[str]:
                if not isinstance(v, list):
                    raise ValueError(f"manifest field '{f.name}' must be a list")
                setattr(m, f.name, [_as_text(x, f.name) for x in v])
        return m

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "version": self.version,
            "author": self.author, "description": self.description,
            "api_version": self.api_version, "type": self.type,
            "permissions": self.permissions,
            "hooks": self.hooks, "methods": self.methods, "events": self.events,
            "outbound_domains": self.outbound_domains, "entrypoint": self.entrypoint,
            "max_memory_mb": self.max_memory_mb,
            "max_cpu_seconds": self.max_cpu_seconds,
            "timeout_seconds": self.timeout_seconds,
            "requires_pii_network_exception": self.requires_pii_network_exception,
            "pii_network_justification": self.pii_network_justification,
            "spec_file": self.spec_file,
            "broker_id": self.broker_id,
            "captcha_plugin_id": self.captcha_plugin_id,
            "is_property_broker": self.is_property_broker,
            "difficulty": self.difficulty,
        }
