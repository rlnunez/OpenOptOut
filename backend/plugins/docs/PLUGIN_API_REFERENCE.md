# OpenOptOut Plugin API & Developer Reference Specification

This specification provides the comprehensive technical manual for developing, packaging, and deploying extensions for the OpenOptOut platform. It details all supported plugin categories, protocol interfaces (gRPC and REST), SDK methods, security controls, manifest schemas, and proposed endpoint enhancements.

---

## 1. Architecture & Execution Model

OpenOptOut employs a **zero-trust, process-isolated plugin architecture**. Third-party code never runs inside the main FastAPI process or the core distributed worker process:

```
┌────────────────────────────────────────────────────────────────────────┐
│                         OpenOptOut Host Core                           │
│  FastAPI Web Service / Worker Fleet Node (Python 3.10+)                │
│                                                                        │
│  ┌─────────────────────────┐           ┌─────────────────────────────┐ │
│  │ HostCapabilityBroker    │           │ PluginManager               │ │
│  │ - Token verification    │           │ - Lifecycle management      │ │
│  │ - Permission gating     │           │ - Sandbox supervision       │ │
│  │ - Method allowlisting   │           │ - Violation tracking        │ │
│  │ - PII redaction         │           │ - Heartbeat probes          │ │
│  └───────────┬─────────────┘           └──────────────┬──────────────┘ │
└──────────────┼────────────────────────────────────────┼────────────────┘
               │                                        │
      Unix Domain Socket                       Process Supervision
      (read-only HostService)                  (fork/exec with limits)
               │                                        │
┌──────────────▼────────────────────────────────────────▼────────────────┐
│               Bubblewrap / Linux Namespace Sandbox Boundary            │
│  - Mounts: code directory read-only, ephemeral /tmp private storage    │
│  - Capabilities: dropped (PR_SET_NO_NEW_PRIVS)                         │
│  - Namespaces: IPC, UTS, User, and Network (unless 'network' granted)  │
│  - Seccomp-BPF: sys_ptrace, bpf, reboot, mount prohibited              │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                   Plugin Child Process (Python)                  │  │
│  │  openoptout_sdk -> PluginService (gRPC Server on plugin.sock)    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

### Key Security Boundaries
1. **Bidirectional gRPC IPC over Unix Domain Sockets:** All communication occurs over private Unix domain sockets (`host.sock` and `plugin.sock`) bind-mounted into an ephemeral runtime directory. TCP sockets are blocked in sandboxed mode.
2. **Session Authentication:** Every request from a plugin to the host carries an ephemeral session token generated during handshake.
3. **Method-Level Allowlisting:** Coarse permissions are insufficient. Plugins must declare the exact host methods they invoke in `manifest.json`. Undeclared calls trigger immediate plugin termination, a critical audit log event, and revocation of execution grants.
4. **Filesystem Isolation:** The plugin's code directory is mounted read-only (`ro-bind`). The plugin cannot modify its own code or persist unauthorized binaries. Persistent storage is provided strictly via host-brokered key-value APIs (`plugin.storage`).

---

## 2. Typed Directory Structure

Plugins are organized into specialized subdirectories under `<plugins_root>/` (default: `/opt/openoptout/data/plugins/`):

```
<plugins_root>/
├── brokers/          # Declarative broker specs (Roadmap Item 1/2)
│   └── <plugin_id>/
│       ├── manifest.json
│       ├── spec.json
│       └── (optional logo.png / notes.md)
│
├── forms/            # Complex multi-stage page handlers
│   └── <plugin_id>/
│       ├── manifest.json
│       └── plugin.py
│
├── captcha/          # Pluggable challenge solvers (Item 4)
│   └── <plugin_id>/
│       ├── manifest.json
│       └── plugin.py
│
├── discovery/        # Patron listing discovery bots (Item 7.3)
│   └── <plugin_id>/
│       ├── manifest.json
│       └── plugin.py
│
├── email/            # Email transport & OAuth providers (Item 10/11)
│   └── <plugin_id>/
│       ├── manifest.json
│       └── plugin.py
│
├── themes/           # Visual design tokens & branding (Data-Only)
│   └── <plugin_id>/
│       ├── manifest.json
│       ├── theme.json
│       └── assets/ (logo.svg, logo.png, favicon.ico)
│
├── languages/        # i18n localization packs (Data-Only, Item 17)
│   └── <plugin_id>/
│       ├── manifest.json
│       └── messages.json
│
└── general/          # Event listeners, webhooks, and integrations
    └── <plugin_id>/
        ├── manifest.json
        └── plugin.py
```

### Type Constraints Matrix

| Plugin Type | Subdirectory | Required Hooks | Allowed Permissions | Process Model |
|---|---|---|---|---|
| `brokers` | `plugins/brokers/` | *(None)* | `broker_read`, `settings_read`, `storage`, `fill_forms`, `read_pii` | **Data-only by default** (`spec.json`); optional Python process |
| `forms` | `plugins/forms/` | `fill_form` | `fill_forms`, `read_pii`, `broker_read`, `settings_read`, `storage` | Sandboxed Python process |
| `captcha` | `plugins/captcha/` | `solve_captcha` | `solve_captcha`, `network`, `http_fetch`, `settings_read`, `storage` | Sandboxed Python process |
| `discovery` | `plugins/discovery/` | *(None)* | `read_pii`, `network`, `http_fetch`, `broker_read`, `settings_read`, `storage`, `emit_events` | Sandboxed Python process |
| `email` | `plugins/email/` | `email_provider` | `email_provider`, `read_pii`, `network`, `settings_read`, `storage` | Sandboxed Python process (Trusted Class) |
| `themes` | `plugins/themes/` | *(Prohibited)* | *(Prohibited — 0 permissions)* | **Data-only** (No code execution) |
| `languages` | `plugins/languages/` | *(Prohibited)* | *(Prohibited — 0 permissions)* | **Data-only** (No code execution) |
| `general` | `plugins/general/` | *(None)* | All except `email_provider`, `solve_captcha`, `fill_forms` | Sandboxed Python process |

---

## 3. Manifest Specification (`manifest.json`)

Every plugin bundle must contain a `manifest.json` at its root.

### Complete Schema Reference

```json
{
  "id": "slug-identifier",
  "name": "Human-Readable Plugin Name",
  "version": "1.0.0",
  "author": "Organization or Author Name",
  "description": "Comprehensive explanation of plugin functionality.",
  "type": "brokers | forms | captcha | discovery | email | themes | languages | general",
  "api_version": "1.0",
  "entrypoint": "plugin.py",
  "permissions": [
    "storage",
    "http_fetch"
  ],
  "methods": [
    "storage.get",
    "storage.set",
    "http.fetch",
    "log"
  ],
  "hooks": [
    "solve_captcha"
  ],
  "events": [
    "optout_sent",
    "confirmation_received"
  ],
  "outbound_domains": [
    "api.solverservice.com"
  ],
  "max_memory_mb": 128,
  "max_cpu_seconds": 30,
  "timeout_seconds": 15,
  "spec_file": "spec.json",
  "captcha_plugin_id": "recaptcha-v2-solver",
  "difficulty": "easy | medium | hard",
  "is_property_broker": false
}
```

### Field Definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string` | **Yes** | Unique lowercase alphanumeric slug with hyphens (e.g., `fastpeoplesearch-solver`). |
| `name` | `string` | **Yes** | Display name shown in administrative interfaces. |
| `version` | `string` | **Yes** | Semantic version string (`MAJOR.MINOR.PATCH`). |
| `author` | `string` | **Yes** | Author or maintainer attribution. |
| `type` | `string` | **Yes** | Must match one of the defined category types. |
| `description` | `string` | No | Operational overview and documentation summary. |
| `entrypoint` | `string` | Conditional | Relative path to executable script (e.g. `plugin.py`). **Must be empty or omitted for `themes`, `languages`, and declarative `brokers`**. |
| `permissions` | `list[string]` | No | High-level privilege categories requested from the host. |
| `methods` | `list[string]` | Conditional | Exhaustive list of exact host API methods called by the plugin. |
| `hooks` | `list[string]` | Conditional | Extension hooks implemented by the plugin. |
| `events` | `list[string]` | No | Lifecycle events the plugin subscribes to when declaring `on_event`. |
| `outbound_domains` | `list[string]` | Conditional | Mandatory allowlist of external FQDNs if `network` or `http_fetch` is requested. |
| `max_memory_mb` | `int` | No | Linux `RLIMIT_AS` memory ceiling in megabytes (default: 128MB, maximum: 512MB). |
| `max_cpu_seconds` | `int` | No | Linux `RLIMIT_CPU` total compute seconds allowed per invocation (default: 30s). |
| `timeout_seconds` | `int` | No | Maximum wall-clock execution time for individual RPC calls before termination (default: 15s). |
| `spec_file` | `string` | No | Relative path to declarative broker specification for `brokers` add-ons (default: `spec.json`). |
| `captcha_plugin_id` | `string` | No | Recommended or required CAPTCHA solver plugin ID for `brokers` add-ons. |
| `difficulty` | `string` | No | Broker opt-out difficulty rating (`easy`, `medium`, `hard`). |
| `is_property_broker` | `bool` | No | Flag indicating if broker exposes real estate/property deed listings. |

---

## 4. Category-Specific Implementation Guides

### 4.1. Removal Plugins

OpenOptOut supports two distinct approaches for broker opt-out automation:

#### Approach A: Declarative Broker Add-ons (`plugins/brokers/<id>/`) — Recommended
Declarative add-ons require **zero Python code** and execute directly within the core platform's compiled interpreter.

**Directory Structure:**
```
plugins/brokers/fastpeoplesearch/
├── manifest.json
└── spec.json
```

**`manifest.json`:**
```json
{
  "id": "fastpeoplesearch",
  "name": "FastPeopleSearch Add-on",
  "version": "1.1.0",
  "author": "Community",
  "type": "brokers",
  "spec_file": "spec.json",
  "captcha_plugin_id": "recaptcha-v2-solver",
  "difficulty": "medium",
  "is_property_broker": false
}
```

**`spec.json` (`BrokerSpec` Schema):**
```json
{
  "broker_id": "fastpeoplesearch",
  "name": "FastPeopleSearch",
  "method": "form",
  "opt_out_url": "https://www.fastpeoplesearch.com/removal",
  "steps": [
    {
      "action": "navigate",
      "url": "https://www.fastpeoplesearch.com/removal"
    },
    {
      "action": "fill",
      "selector": "input#email",
      "value": "{email}"
    },
    {
      "action": "click",
      "selector": "input#check-agreement"
    },
    {
      "action": "solve_captcha",
      "selector": ".g-recaptcha"
    },
    {
      "action": "click",
      "selector": "button#submit-removal"
    },
    {
      "action": "wait_for",
      "selector": ".confirmation-notice",
      "timeout_ms": 10000
    }
  ],
  "success_criteria": {
    "url_contains": "/removal/success",
    "text_present": "removal request has been received"
  }
}
```

**Supported Spec Actions:**
- `navigate`: Navigates to a specific URL.
- `fill`: Enters text into an input matched by CSS selector. Supports patron placeholders (`{first_name}`, `{last_name}`, `{email}`, `{phone}`, `{city}`, `{state}`, `{zip}`, `{address}`).
- `click`: Clicks element matched by CSS selector.
- `click_matching`: Iterates over elements and clicks the one matching specific inner text.
- `select`: Selects a dropdown `<option>` by value or label.
- `press`: Dispatches keyboard events (`Enter`, `Tab`, `Escape`).
- `wait_for`: Pauses execution until a DOM selector or text appears.
- `scroll`: Scrolls target element or page into viewport.
- `frame`: Switches execution context into a child `<iframe>`.
- `solve_captcha`: Dispatches an inline challenge to the configured CAPTCHA solver.

---

#### Approach B: Custom Form Handlers (`plugins/forms/<id>/`)
When a broker utilizes dynamic state machines, anti-bot obfuscation, or multi-step verification wizards that exceed declarative modeling, use a custom Python form plugin.

**`manifest.json`:**
```json
{
  "id": "complex-broker-handler",
  "name": "Complex Broker Form Handler",
  "version": "1.0.0",
  "author": "OpenOptOut Team",
  "type": "forms",
  "entrypoint": "plugin.py",
  "permissions": ["fill_forms", "read_pii", "broker_read", "storage"],
  "hooks": ["fill_form"],
  "methods": ["broker.get", "storage.get", "storage.set", "log"]
}
```

**`plugin.py`:**
```python
from openoptout_sdk import Plugin, manifest, FormResult, Action

plugin = Plugin(manifest(
    id="complex-broker-handler",
    name="Complex Broker Form Handler",
    version="1.0.0",
    author="OpenOptOut Team",
    type="forms",
    permissions=["fill_forms", "read_pii", "broker_read", "storage"],
    hooks=["fill_form"],
    methods=["broker.get", "storage.get", "storage.set", "log"],
))

@plugin.fill_form
def handle_form(request):
    """
    Called by the host with page DOM and member fields.
    Returns structured actions for the host browser to execute.
    """
    plugin.log.info(f"Inspecting form for broker {request.broker_name}")

    # Check if page indicates already submitted
    if "Your request is in progress" in request.page_html:
        return FormResult(handled=True, status="submitted", actions=[])

    # Extract field values provided by host
    fields = {f.key: f.value for f in request.fields}
    first_name = fields.get("first_name", "")
    last_name = fields.get("last_name", "")
    email = fields.get("email", "")

    # Return actions for host Playwright browser to execute
    actions = [
        Action(type="fill", selector="#fname", value=first_name),
        Action(type="fill", selector="#lname", value=last_name),
        Action(type="fill", selector="#contact_email", value=email),
        Action(type="click", selector="#agree_terms"),
        Action(type="click", selector="button.submit-btn"),
        Action(type="wait_for", selector=".alert-success", timeout_ms=5000),
    ]

    return FormResult(handled=True, status="in_progress", actions=actions)

if __name__ == "__main__":
    plugin.run()
```

---

### 4.2. CAPTCHA Solver Plugins (`plugins/captcha/<id>/`)

Pluggable solvers handle automated challenges without embedding proprietary solving logic into the core open-source engine.

**`manifest.json`:**
```json
{
  "id": "enterprise-captcha-solver",
  "name": "Enterprise CAPTCHA Solver",
  "version": "1.0.0",
  "author": "Security Ops",
  "type": "captcha",
  "entrypoint": "plugin.py",
  "permissions": ["solve_captcha", "http_fetch", "settings_read", "storage"],
  "hooks": ["solve_captcha"],
  "methods": ["http.fetch", "settings.get", "storage.get", "storage.set", "log"],
  "outbound_domains": ["api.captchaservice.internal"]
}
```

**`plugin.py`:**
```python
import json
from openoptout_sdk import Plugin, manifest, SolveCaptchaResponse

plugin = Plugin(manifest(
    id="enterprise-captcha-solver",
    name="Enterprise CAPTCHA Solver",
    version="1.0.0",
    author="Security Ops",
    type="captcha",
    permissions=["solve_captcha", "http_fetch", "settings_read", "storage"],
    hooks=["solve_captcha"],
    methods=["http.fetch", "settings.get", "storage.get", "storage.set", "log"],
    outbound_domains=["api.captchaservice.internal"],
))

@plugin.solve_captcha
def solve(challenge):
    plugin.log.info(f"Received {challenge.type} challenge for {challenge.page_url}")

    # Read API credentials securely from host settings
    api_key = plugin.settings.get("captcha_api_key")
    if not api_key:
        plugin.log.warning("No API key configured; deferring challenge to human operator")
        return SolveCaptchaResponse(defer_to_human=True)

    if challenge.type in ("recaptcha_v2", "hcaptcha", "turnstile"):
        payload = json.dumps({
            "clientKey": api_key,
            "task": {
                "type": challenge.type,
                "websiteURL": challenge.page_url,
                "websiteKey": challenge.site_key
            }
        })

        # Use host-mediated HTTP fetch (safest pattern: plugin opens no sockets)
        resp = plugin.http.post(
            "https://api.captchaservice.internal/createTask",
            body=payload,
            headers={"Content-Type": "application/json"}
        )

        if resp.get("status_code") == 200:
            result = json.loads(resp.get("body", "{}"))
            token = result.get("solution", {}).get("token")
            if token:
                return SolveCaptchaResponse(solved=True, token=token)

        return SolveCaptchaResponse(solved=False, error="Provider failed to solve challenge")

    # For unknown challenge types, defer to human operator queue
    return SolveCaptchaResponse(defer_to_human=True)

if __name__ == "__main__":
    plugin.run()
```

---

### 4.3. Discovery Plugins (`plugins/discovery/<id>/`)

Discovery bots crawl search endpoints and data broker listing queries to locate patron profile URLs before removals are dispatched.

**`manifest.json`:**
```json
{
  "id": "broker-discovery-crawler",
  "name": "Broker Directory Discovery Crawler",
  "version": "1.0.0",
  "author": "OpenOptOut Research",
  "type": "discovery",
  "entrypoint": "plugin.py",
  "permissions": ["read_pii", "http_fetch", "broker_read", "emit_events", "storage"],
  "hooks": ["on_event"],
  "methods": ["http.fetch", "broker.list", "emit_event", "storage.get", "storage.set", "log"],
  "events": ["discovery_query_dispatched"],
  "outbound_domains": ["api.duckduckgo.com", "html.duckduckgo.com"]
}
```

**`plugin.py`:**
```python
import urllib.parse
from openoptout_sdk import Plugin, manifest

plugin = Plugin(manifest(
    id="broker-discovery-crawler",
    name="Broker Directory Discovery Crawler",
    version="1.0.0",
    author="OpenOptOut Research",
    type="discovery",
    permissions=["read_pii", "http_fetch", "broker_read", "emit_events", "storage"],
    hooks=["on_event"],
    methods=["http.fetch", "broker.list", "emit_event", "storage.get", "storage.set", "log"],
    outbound_domains=["html.duckduckgo.com"],
))

@plugin.on_event
def handle_event(event):
    if event.event_type != "discovery_query_dispatched":
        return {"ok": True}

    payload = event.data
    patron_name = payload.get("name")
    city = payload.get("city", "")
    state = payload.get("state", "")
    target_broker = payload.get("broker_domain", "")

    query = f'site:{target_broker} "{patron_name}" "{city}" "{state}"'
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    # Query search index via host-mediated fetch
    resp = plugin.http.get(search_url)
    if resp.get("status_code") == 200:
        html = resp.get("body", "")
        # Parse links pointing to broker domain (mock parser for demonstration)
        import re
        matches = re.findall(rf'https://{re.escape(target_broker)}/profile/[a-zA-Z0-9_-]+', html)

        for match_url in set(matches):
            plugin.log.info(f"Discovered profile URL: {match_url}")
            # Emit discovered URL back to host ingestion pipeline
            plugin.emit_event("discovery_listing_found", {
                "member_id": payload.get("member_id"),
                "broker_domain": target_broker,
                "profile_url": match_url,
                "confidence": 0.95
            })

    return {"ok": True}

if __name__ == "__main__":
    plugin.run()
```

---

### 4.4. Theme Plugins (`plugins/themes/<id>/`) — Data-Only

Theme plugins provide visual customization, dark mode palettes, and institutional branding for libraries and universities. They contain **no executable code** and run with **zero subprocess overhead**.

**Directory Structure:**
```
plugins/themes/civic-library/
├── manifest.json
├── theme.json
└── assets/
    ├── logo.svg
    └── favicon.ico
```

**`manifest.json`:**
```json
{
  "id": "civic-library-theme",
  "name": "Civic Public Library Brand Theme",
  "version": "1.0.0",
  "author": "Civic IT Department",
  "type": "themes",
  "description": "Accessible high-contrast municipal library theme with custom color tokens."
}
```

**`theme.json` (CSS Design Token Schema):**
```json
{
  "colors": {
    "primary": "#0056b3",
    "primary_hover": "#004085",
    "secondary": "#6c757d",
    "background": "#f8f9fa",
    "surface": "#ffffff",
    "border": "#dee2e6",
    "text_main": "#212529",
    "text_muted": "#6c757d",
    "accent": "#17a2b8",
    "status_success": "#28a745",
    "status_warning": "#ffc107",
    "status_danger": "#dc3545"
  },
  "dark": {
    "primary": "#3390ff",
    "primary_hover": "#1a7eff",
    "secondary": "#a0aec0",
    "background": "#121418",
    "surface": "#1c1f26",
    "border": "#2e3440",
    "text_main": "#f1f3f5",
    "text_muted": "#a0aec0"
  },
  "typography": {
    "font_family_sans": "Inter, system-ui, -apple-system, sans-serif",
    "font_family_mono": "JetBrains Mono, Menlo, monospace",
    "border_radius": "0.375rem"
  },
  "assets": {
    "logo_path": "assets/logo.svg",
    "favicon_path": "assets/favicon.ico"
  },
  "custom_css": ".navbar { box-shadow: 0 2px 4px rgba(0,0,0,0.08); }"
}
```

---

### 4.5. Language Pack Plugins (`plugins/languages/<id>/`) — Data-Only

Language packs provide community translations and Right-to-Left (RTL) layout parameters without modifying backend Python dictionaries.

**Directory Structure:**
```
plugins/languages/lang-ar/
├── manifest.json
└── messages.json
```

**`manifest.json`:**
```json
{
  "id": "lang-ar",
  "name": "Arabic Language Pack (العربية)",
  "version": "1.0.0",
  "author": "Community Translators",
  "type": "languages",
  "description": "Complete Arabic translation with full RTL mirroring parameters."
}
```

**`messages.json` (Categorized Dictionary Schema):**
```json
{
  "locale": "ar",
  "locale_name": "العربية",
  "direction": "rtl",
  "messages": {
    "nav": {
      "dashboard": "لوحة القيادة",
      "requests": "طلبات الإزالة",
      "identity": "خزينة الهوية",
      "brokers": "وسطاء البيانات",
      "settings": "الإعدادات",
      "logout": "تسجيل الخروج"
    },
    "status": {
      "pending": "قيد الانتظار",
      "submitted": "تم الإرسال",
      "confirmed": "تم التأكيد",
      "failed": "فشل"
    },
    "actions": {
      "submit": "إرسال",
      "cancel": "إلغاء",
      "save": "حفظ التغييرات"
    }
  }
}
```

---

### 4.6. Email Provider Plugins (`plugins/email/<id>/`)

Email provider plugins adapt corporate and institutional mail systems (Google Workspace, Microsoft 365, generic IMAP/SMTP) to the standard OpenOptOut email transport.

**`manifest.json`:**
```json
{
  "id": "custom-smtp-transport",
  "name": "Custom SMTP Relay Transport",
  "version": "1.0.0",
  "author": "Enterprise Mail Team",
  "type": "email",
  "entrypoint": "plugin.py",
  "permissions": ["email_provider", "read_pii", "network", "settings_read", "storage"],
  "hooks": ["email_provider"],
  "methods": ["settings.get", "storage.get", "storage.set", "log"],
  "outbound_domains": ["mail.organization.internal"]
}
```

**Key RPC Methods Implemented by Plugin:**
1. `EmailProviderInfo`: Reports provider capabilities, configuration requirements, and protocol flags.
2. `EmailProviderSend`: Dispatches an outbound opt-out legal notice to a data broker recipient. Recipient is host-verified against broker specifications.
3. `EmailProviderList`: Reads unread inbox replies and filters for removal confirmation notices.

---

### 4.7. General & Lifecycle Plugins (`plugins/general/<id>/`)

General plugins subscribe to platform lifecycle events to integrate with enterprise security information and event management (SIEM), Slack, Discord, or custom auditing tools.

**`plugin.py`:**
```python
import json
from openoptout_sdk import Plugin, manifest

plugin = Plugin(manifest(
    id="slack-audit-notifier",
    name="Slack Audit Notifier",
    version="1.0.0",
    author="Security Operations",
    type="general",
    permissions=["receive_events", "http_fetch", "settings_read", "storage"],
    hooks=["on_event"],
    methods=["http.fetch", "settings.get", "log"],
    events=["optout_failed", "broker_auto_disabled"],
    outbound_domains=["hooks.slack.com"]
))

@plugin.on_event
def handle_event(event):
    webhook_url = plugin.settings.get("slack_webhook_url")
    if not webhook_url:
        return {"ok": False, "error": "Webhook URL not configured"}

    text = f"🚨 *OpenOptOut Alert*: `{event.event_type}` occurred for entity `{event.entity_id}`."
    plugin.http.post(
        webhook_url,
        body=json.dumps({"text": text}),
        headers={"Content-Type": "application/json"}
    )
    return {"ok": True}

if __name__ == "__main__":
    plugin.run()
```

---

## 5. Host Capability API (gRPC `HostService`)

When running inside the sandbox, plugins interact with the host exclusively through `HostService`. Each method requires a specific permission and manifest declaration.

| Host Method | Required Permission | Description |
|---|---|---|
| `storage.get` | `storage` | Retrieve a string key from plugin-isolated persistent storage. |
| `storage.set` | `storage` | Write a string value to plugin-isolated storage. |
| `storage.delete` | `storage` | Delete a key from plugin storage. |
| `storage.list` | `storage` | List all keys associated with this plugin. |
| `settings.get` | `settings_read` | Read a non-secret setting (secrets and credentials are systematically scrubbed). |
| `settings.set` | `settings_write` | Update a setting scoped strictly to this plugin. |
| `broker.get` | `broker_read` | Retrieve public broker metadata (`name`, `method`, `difficulty`, `status`). |
| `broker.list` | `broker_read` | Enumerate active data brokers. |
| `broker.history` | `broker_read` | Retrieve aggregate opt-out statistics for a broker (no member PII). |
| `request.get_status` | `request_read` | Read status and timestamps of an opt-out request. |
| `request.mark_sent` | `request_write` | Transition request to `sent` (logged with before/after audit diff). |
| `request.mark_confirmed` | `request_write` | Transition request to `confirmed` (logged with audit diff). |
| `request.mark_failed` | `request_write` | Transition request to `failed` (logged with audit diff). |
| `optout.trigger_email` | `trigger_optout_email` | Triggers the canonical template email for an email-method request. |
| `http.fetch` | `http_fetch` | Host executes an HTTP GET or POST on behalf of the plugin to declared domains. |
| `schedule.set_recheck` | `schedule_write` | Overrides the periodic recheck timestamp for a confirmed request. |
| `emit_event` | `emit_events` | Emits a custom event into the host's internal event bus. |
| `log` | *(None)* | Appends a structured log entry to the host's rotating diagnostic log. |

---

## 6. Management REST API Reference (`/api/plugins/*`)

Administrators and automated orchestration tools manage plugins via the platform's REST API:

### Endpoints

| Method | Endpoint | Permission | Description |
|---|---|---|---|
| `GET` | `/api/plugins` | `plugins.view` | List all installed plugins, operational statuses, and granted permissions. |
| `GET` | `/api/plugins/types` | `plugins.view` | Enumerate supported plugin categories, folder targets, and permission matrices. |
| `GET` | `/api/plugins/available` | `plugins.view` | Scan `<plugins_root>/` for uninstalled bundles on disk. |
| `POST` | `/api/plugins/upload` | `plugins.upload` | Upload a zip bundle. Extracts safely into `<plugins_root>/<type>/<id>/`. |
| `POST` | `/api/plugins/upload/inspect` | `plugins.upload` | Pre-flight validation of an uninstalled zip file (schema, type, errors). |
| `POST` | `/api/plugins/install` | Super Admin | Register a discovered plugin in the database (installed in disabled state). |
| `POST` | `/api/plugins/{id}/enable` | Super Admin | Review declared methods, grant permissions, and launch child process. |
| `POST` | `/api/plugins/{id}/disable` | Super Admin | Gracefully stop the running process and mark disabled. |
| `DELETE` | `/api/plugins/{id}` | Super Admin | Terminate process and purge database record. |
| `GET` | `/api/plugins/{id}/audit` | `plugins.view` | View security violation logs, lifecycle transitions, and capability diffs. |
| `GET` | `/api/plugins/status` | `plugins.view` | Inspect host sandbox runtime (Bubblewrap availability, seccomp filters). |
| `GET` | `/api/plugins/docs/{doc}` | `plugins.view` | Fetch markdown documentation (`using`, `writing`, or `api`). |

---

## 7. Recommended API & Endpoint Enhancements

Based on an exhaustive review of the plugin subsystem, the following endpoint and protocol enhancements are recommended for future platform milestones:

### 1. First-Class Discovery Hook (`rpc DiscoverListings`)
- **Current State:** Discovery bots operate either via custom `on_event` handlers or internal worker runners (`core/distributed/worker.py`).
- **Proposed Enhancement:** Add `rpc DiscoverListings (DiscoverListingsRequest) returns (DiscoverListingsResponse)` to `PluginService` in `plugin.proto`.
- **Benefit:** Allows third-party discovery bot plugins to implement structured discovery tasks with uniform parameters (`name`, `city`, `state`, `broker_domain`), returning validated `Listing` objects directly into the distributed worker queue.

### 2. Interactive Plugin Dry-Run Endpoint (`POST /api/plugins/{id}/test`)
- **Current State:** A plugin can only be verified by enabling it live and waiting for real opt-out or event triggers.
- **Proposed Enhancement:** Add `POST /api/plugins/{id}/test` accepting a simulated payload (mock HTML, test CAPTCHA image, or mock email).
- **Benefit:** Allows administrators to test solvers and form handlers in a sandboxed staging sandbox before granting production permissions.

### 3. Dynamic Theme Compilation & CSS Endpoint (`GET /api/branding/themes/{id}/styles.css`)
- **Current State:** Themes are loaded statically from JSON and merged on the frontend.
- **Proposed Enhancement:** Add `GET /api/branding/themes/{id}/styles.css` that dynamically compiles design tokens, CSS variables, and font assets into a minified stylesheet.
- **Benefit:** Enables instant server-side theming and external portal embedding for consortium member libraries.

### 4. Real-Time Plugin Diagnostic Stream (`GET /api/plugins/{id}/logs/stream` via SSE)
- **Current State:** Logs are aggregated into the central rotating ring buffer (`/data/logs/openoptout.log`).
- **Proposed Enhancement:** Provide a Server-Sent Events (SSE) streaming endpoint filtering logs, stderr output, and gRPC execution traces specifically for a single plugin.
- **Benefit:** Drastically improves the debugging workflow for plugin authors developing custom integrations.

### 5. Standalone Broker Spec Linter API (`POST /api/plugins/brokers/validate-spec`)
- **Current State:** Broker specs (`spec.json`) are only validated upon complete directory scan or zip upload.
- **Proposed Enhancement:** Add a lightweight endpoint accepting raw JSON and returning immediate selector diagnostics, syntax warnings, and migration hints.
- **Benefit:** Enables browser extension editors and web-based IDEs to validate community broker specs in real time.
