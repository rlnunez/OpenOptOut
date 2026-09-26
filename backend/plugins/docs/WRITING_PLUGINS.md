# Writing Plugins (Developer Guide)

PrivacyShield supports **process-isolated, sandboxed plugins** so third parties
can extend the app — custom form-filling strategies, email parsers, event
reactions, and plugin-scoped storage — without being able to touch the host's
memory, database, credentials, or (unless granted) the network.

This guide covers the extension points, host capabilities, manifest format, and SDK a developer uses to write a plugin.

---

## Extension points (hooks)

### `fill_form` — custom broker automation
The host calls the plugin with the broker, the current page HTML, and (if
`read_pii` granted) the member's field values. The plugin returns a list of
**browser actions** (fill/click/select/wait). The host executes them in its own
sandboxed Playwright browser — **the plugin never drives a browser itself**, so
the browser and its network access stay in the host. Return `handled=False` to
let the built-in engine run instead.

### `parse_email` — custom confirmation parsing
For brokers whose confirmation emails don't use the standard UUID key. The host
passes the message and the list of pending tracking keys; the plugin returns
whether it matched and which request it confirms. Falls back to the built-in
UUID matcher if no plugin handles it.

### `on_event` — lifecycle reactions
Fired for `optout_sent`, `optout_failed`, `confirmation_received`, and custom
events other plugins emit. Fire-and-observe. PII in event data is redacted
unless `read_pii` is granted.

### `solve_captcha` — pluggable CAPTCHA solving
The extension point for the CAPTCHA wall. When a form opt-out hits a CAPTCHA, the
host invokes this hook (if a plugin declares it). The plugin receives a
`CaptchaChallenge` (type, site_key, page_url, an optional screenshot, and meta
hints) and returns one of:
- `{"solved": True, "token": "..."}` — a solution token to inject.
- `{"defer_to_human": True}` — the plugin can't/won't solve it; use the human path.
- `{"solved": False, "error": "..."}` — solving failed.

Requires the `solve_captcha` permission. A solver that calls an external solving
service also needs `network` + declared `outbound_domains` — and that combination
is high-risk and reviewed accordingly. The core never solves CAPTCHAs itself;
this hook is how a deployment plugs in its own strategy (human-in-the-loop, a
paid service, an AI solver). Declaring the hook without a solver registered, or
with no solver plugin installed at all, means CAPTCHA-gated brokers fall through
to the human path.

Example:
```python
@plugin.solve_captcha
def solve(challenge):
    if challenge.type == "recaptcha_v2":
        token = my_service.solve(challenge.site_key, challenge.page_url)
        return {"solved": True, "token": token}
    return {"defer_to_human": True}
```

---


## Beyond hooks: calling into the pipeline

The three hooks above are things the *host* calls on the *plugin*. The SDK also
exposes host capabilities the *plugin* can call — each gated by its own
permission and declared method (see [Method-level allowlisting](#method-level-allowlisting-least-privilege)
above). These are the areas most likely to matter beyond storage/settings:

### Broker read (`plugin.brokers`) — read-only, no member PII
```python
plugin.brokers.get(broker_id)        # {"name", "method", "difficulty", "status"}
plugin.brokers.list(limit=100)       # same fields, many brokers
plugin.brokers.history(broker_id)    # {"total_requests", "confirmed_count", "failed_count", "pending_count"}
```
Every field returned is a broker attribute or an aggregate count — never a
member's name, address, or contact info. Requires `broker_read`.

### Request lifecycle (`plugin.requests`) — status only, no member PII
```python
plugin.requests.get_status(request_id)                    # {"status", "sent_at", "confirmed_at", ...}
plugin.requests.mark_sent(request_id, reason="...")
plugin.requests.mark_confirmed(request_id, reason="...")
plugin.requests.mark_failed(request_id, reason="...")
```
Reads need `request_read`. **Writes need `request_write` and are treated as
high-risk**: every mark_* call is logged to the audit trail with a before/after
status diff and the reason string you supply — visible to the super admin, so
there's a clear record of what a plugin changed and why. The diff is built from
status enums and timestamps only, never member fields.

### Constrained opt-out email (`plugin.optout`) — not freeform email
```python
plugin.optout.trigger_email(request_id)   # {"ok": bool, "error": str}
```
This does not let a plugin compose or send arbitrary email. It calls the exact
same `send_opt_out_email()` function the built-in opt-out engine itself uses —
same template, same recipient-resolution logic, same SMTP config — for one
specific **pending**, **email-method** request. The plugin supplies only a
request id. Requires `trigger_optout_email` (high risk — it does send real
outbound email, even though the content is fixed).

### Host-mediated HTTP fetch (`plugin.http`) — the host makes the call
```python
plugin.http.get(url, headers=None)
plugin.http.post(url, body="", headers=None)
```
The plugin never opens its own socket for this — the **host** performs the
fetch and returns the response. It is restricted to domains the plugin declared
in its manifest's `outbound_domains`; a request to any other host is refused
and logged as a violation. Requires `http_fetch`. This is the intended path for
a plugin that needs occasional outbound calls without holding the broader
`network` permission (which allows a plugin's own process to reach the network
directly, inside the sandbox's namespace rules).

### Custom recheck scheduling (`plugin.schedule`)
```python
plugin.schedule.set_recheck(request_id, recheck_after_unix_ts, reason="...")
```
Overrides the default recheck interval for one confirmed request. Diff-logged
like request-lifecycle writes. Requires `schedule_write`.

---


## Method-level allowlisting (least privilege)

Permissions are coarse — holding `storage` could, in principle, unlock reading,
writing, *and* deleting. PrivacyShield tightens this to the individual method.
Every plugin must declare in its manifest the **exact host methods** it will
call, and the broker refuses any method not on that list — even when the plugin
holds the broader permission.

The callable host methods are:

| Method | Permission it needs | Does |
|---|---|---|
| `storage.get` | `storage` | Read its own stored values |
| `storage.set` | `storage` | Write its own stored values |
| `storage.delete` | `storage` | Delete its own stored values |
| `storage.list` | `storage` | List its own stored keys |
| `settings.get` | `settings_read` | Read a non-secret setting |
| `settings.set` | `settings_write` | Write its own setting |
| `emit_event` | `emit_events` | Emit an event to the host |
| `log` | (none) | Write to the plugin log |
| `broker.get` | `broker_read` | Look up one broker (name/method/difficulty/status) |
| `broker.list` | `broker_read` | List brokers (same fields) |
| `broker.history` | `broker_read` | Aggregate opt-out counts for a broker |
| `request.get_status` | `request_read` | Read a request's status/timestamps |
| `request.mark_sent` | `request_write` | Mark a request sent (audit-diffed) |
| `request.mark_confirmed` | `request_write` | Mark a request confirmed (audit-diffed) |
| `request.mark_failed` | `request_write` | Mark a request failed (audit-diffed) |
| `optout.trigger_email` | `trigger_optout_email` | Send the existing opt-out email template for one request |
| `http.fetch` | `http_fetch` | Host-mediated GET/POST to a declared domain |
| `schedule.set_recheck` | `schedule_write` | Set a custom recheck time (audit-diffed) |

Declare them in the manifest under `methods`:

```json
"permissions": ["storage"],
"methods": ["storage.get", "storage.set", "log"]
```

That plugin can read and write its store and log — but a call to
`storage.delete` is refused **and treated as a security violation**, because it
reached for capability surface it never disclosed.

**What happens on an undeclared-method call:** the broker refuses it, the
manager records a `critical` violation, a banner is raised on the Plugins page,
the plugin is **disabled immediately**, and it is flagged `needs_reapproval`.
It cannot be re-enabled until a super admin re-opens it, reviews the declared
method list, and re-approves (the enable call must set `acknowledge_methods`).
This makes the manifest a binding contract: the code can only do what the
manifest says, and any drift takes the plugin offline until a human re-reviews.

The enable page shows the person exactly which methods, event types, and (if
`network` is granted) outbound domains the plugin declared — so they approve a
precise, visible capability surface rather than a vague permission bucket.

### Declared inbound and egress

- **`events`** — the event types an `on_event` plugin expects (e.g.
  `optout_sent`, `confirmation_received`). Shown to the admin; informational.
- **`outbound_domains`** — if the plugin requests `network`, it declares the
  domains it intends to contact. These are surfaced prominently (network egress
  is high-risk) so the admin sees exactly where a networked plugin will reach.

---


## Writing a plugin

A plugin is a directory with a `manifest.json` and an entrypoint (default
`plugin.py`) that uses the SDK.

### manifest.json
```json
{
  "id": "my-plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "author": "you",
  "description": "What it does.",
  "permissions": ["receive_events", "storage"],
  "hooks": ["on_event"],
  "methods": ["storage.get", "storage.set", "log"],
  "events": ["optout_sent", "confirmation_received"],
  "entrypoint": "plugin.py",
  "max_memory_mb": 128,
  "max_cpu_seconds": 15,
  "timeout_seconds": 10
}
```

### plugin.py
```python
from privacyshield_sdk import Plugin, manifest, FormResult

plugin = Plugin(manifest(
    id="my-plugin", name="My Plugin", version="1.0.0", author="you",
    permissions=["receive_events", "storage"], hooks=["on_event"],
    methods=["storage.get", "storage.set", "log"],
))

@plugin.on_event
def handle(event):
    plugin.log.info(f"event {event.event_type}")
    n = int(plugin.storage.get("count") or "0") + 1
    plugin.storage.set("count", str(n))
    return {"ok": True}

if __name__ == "__main__":
    plugin.run()
```

The SDK exposes, once the host completes the handshake:
- `plugin.storage` — `.get/.set/.delete/.list` (needs `storage`)
- `plugin.settings` — `.get/.set` (needs `settings_read`/`settings_write`)
- `plugin.log` — `.debug/.info/.warning/.error` (routed to the host log)
- decorators `@plugin.on_event`, `@plugin.fill_form`, `@plugin.parse_email`

Calls to capabilities you didn't request are refused by the host.

### Packaging
Zip the plugin directory (with `manifest.json` at the root or one level down)
and upload it, or place the folder directly in the plugins directory.

### Building the protocol stubs (for local plugin development)
The SDK imports the compiled gRPC stubs. Generate them once:
```bash
bash backend/plugins/proto/compile.sh
```

---


## Limitations & honest caveats

- **Full OS sandboxing is Linux-only.** Without bubblewrap, plugins are bounded
  by resource limits and the process boundary but not filesystem/network
  namespaces. Don't run untrusted plugins on such a host.
- **gRPC is required.** If `grpcio` isn't installed or the stubs aren't
  compiled, the plugin system stays inactive (the rest of the app is unaffected).
- **A granted permission is real trust.** `read_pii` + `network` together means
  a plugin can receive personal data and make network calls — grant that
  combination only to plugins you genuinely trust.
- **This has not been battle-tested against a determined attacker.** The design
  follows least-privilege and defense-in-depth, but for high-stakes untrusted
  code you should add your own container-level isolation (separate container per
  plugin, network policies) on top.
