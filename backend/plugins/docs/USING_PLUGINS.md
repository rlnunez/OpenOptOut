# Using Plugins (Administrator Guide)

PrivacyShield supports **process-isolated, sandboxed plugins** so third parties
can extend the app — custom form-filling strategies, email parsers, event
reactions, and plugin-scoped storage — without being able to touch the host's
memory, database, credentials, or (unless granted) the network.

This guide covers the security model, the permissions plugins can request, and how to install, enable, and safely operate plugins as an administrator.

---

## Why this design

The app holds sensitive personal data, sometimes for minors and library patrons.
Plugins are untrusted third-party code. A naive "drop a .py file in a folder and
import it" approach gives that code full access to everything the host process
can see — PII, IMAP/SMTP passwords, database, filesystem, network. There is no
reliable way to sandbox in-process Python (`import os` defeats it).

So PrivacyShield never executes plugin code in its own interpreter. Each plugin
runs as a **separate OS process**, and the host and plugin communicate over
**gRPC**. Everything a plugin can do goes through a small, **capability-gated**
API that the host enforces. On Linux with bubblewrap, plugins additionally run
inside namespace/resource sandboxes.

---

## Security model

### 1. Process isolation
Every plugin is a subprocess. A crash, hang, or infinite loop cannot take down
the host — the manager supervises with liveness pings, per-call timeouts, and
hard process-group kills. Three crashes auto-disables the plugin.

### 2. Capability gating
The plugin calls back into the host only through the `HostService` gRPC API.
Every call carries a session token (issued at launch, unique per run) and is
checked against the plugin's **granted** permissions. If a plugin didn't get
`storage`, storage calls are refused. If it didn't get `read_pii`, hook payloads
arrive with member field values redacted to empty strings.

### 3. Explicit, human trust gate
Plugins install **disabled**. A super admin must open the plugin, see each
requested permission with its **risk level** and description, and explicitly
grant them to enable it. Nothing runs until a person decides to trust it.

### 4. OS sandboxing (Linux)
When launching a plugin the host applies the strongest available controls:

| Control | Mechanism | Effect |
|---|---|---|
| Filesystem | bubblewrap (`bwrap`) | Host FS hidden; only the plugin's own dir is writable; private `/tmp` |
| Network | network namespace | **No network at all** unless the plugin was granted `network` |
| Memory / CPU | POSIX `RLIMIT_*` | Hard caps on address space, CPU seconds, processes, file descriptors |
| Namespaces | `unshare` fallback | PID/mount isolation if bubblewrap absent |
| Privileges | never root | Plugins run unprivileged; core dumps disabled |

The host logs its effective posture at startup — **FULL** or **PARTIAL** — and
the Plugins admin page shows it. On macOS (development) or a container without
bubblewrap, only resource limits + the process boundary apply, and the UI warns
that untrusted plugins are **not** fully contained.

> **Operator action:** for production with untrusted third-party plugins, deploy
> on Linux and install bubblewrap. The provided Dockerfile installs it.

### 5. Secrets never reach plugins
The settings accessor refuses any key that looks like a credential (`password`,
`secret`, `token`, `_enc`, etc.), even with `settings_read`. Plugins get their
own scoped settings namespace and non-secret globals only.

---


## Permissions

| Permission | Risk | Grants |
|---|---|---|
| `read_pii` | high | Member field values (names, addresses, phones, emails) in hook calls |
| `network` | high | Outbound network (sandbox blocks it otherwise) |
| `storage` | low | The plugin's own isolated key/value store |
| `settings_read` | low | Read non-secret settings |
| `settings_write` | medium | Write the plugin's own settings |
| `emit_events` | medium | Push custom events into the host event bus |
| `fill_forms` | medium | Provide a custom form-filling strategy |
| `parse_email` | medium | Interpret confirmation emails |
| `receive_events` | low | Be notified of lifecycle events |

A hook requires its matching permission (`fill_form`→`fill_forms`,
`parse_email`→`parse_email`, `on_event`→`receive_events`). The host refuses to
enable a plugin whose declared hook lacks its permission.

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


## The exfiltration path: `read_pii` + `network`, blocked by default

Every other control in this document governs the host's own API surface — what
a plugin can ask the *host* to do. It does not stop a plugin that holds both
`read_pii` (member data arrives in hook payloads) and `network` (its own
process can open a raw socket inside the sandbox) from writing its own code to
send that data anywhere: its own HTTP POST, its own SMTP connection, anything.
That is the one path where a plugin's own code — not a host API call — could
exfiltrate member data. It gets a dedicated, stricter control:

**Blocked at manifest validation, before installation is even possible.** A
manifest requesting both `read_pii` and `network` is invalid unless it also
sets `requires_pii_network_exception: true` and provides a
`pii_network_justification` of real substance (20+ characters, not filler) plus
a non-empty `outbound_domains` list. Without all three, the plugin cannot be
installed — this isn't an admin choice at that point, it's a hard manifest
error.

**A second, separate confirmation at enable time — not the normal grant flow.**
Even with a valid exception declared, granting both permissions together
requires `confirm_pii_network_exception` as a distinct field on the enable
request, shown in the UI as its own red-bordered block with the author's
justification and declared domains, separate from the ordinary permission
checkboxes. Missing it refuses the enable with a 409 and echoes back the
justification/domains so the admin can decide. Every grant is logged to the
audit trail as `pii_network_exception_granted`, separately from ordinary
"enabled" entries.

**Heavy monitoring for the life of the process.** Any plugin running with both
permissions granted is flagged for heavy monitoring the moment it launches:
- Socket-count tolerance drops from the normal baseline to almost zero — even
  a single unexpected connection beyond the host's loopback channel is flagged.
- Outbound byte volume is tracked via the plugin's own network-namespace device
  counters (`/proc/<pid>/net/dev`, excluding loopback). More than 5MB
  transferred since launch is treated as a `critical` violation and the plugin
  is disabled immediately — the same auto-disable policy as every other
  violation type.
- This is on top of, not instead of, the domain restriction that already
  applies to `http.fetch` — heavy monitoring is watching the plugin's *own*
  socket use, which `http.fetch`'s domain allowlist does not cover, since
  `http.fetch` is a separate, host-mediated path a well-behaved plugin can
  choose instead of raw `network`.

**What this does not do.** It does not make raw network access from a
`read_pii`-holding plugin *safe* — a sufficiently small, infrequent transfer
could stay under the byte threshold, and detection still lags prevention on a
host without full OS sandboxing. The honest position: avoid granting this
combination at all if there's any other way to accomplish the plugin's goal —
`http.fetch` with a domain allowlist, or splitting the plugin into a
PII-handling half and a network-handling half that only exchange non-PII data,
are both safer designs than holding both permissions in one process.

---


## Safety controls (kill-switch, lockdown, monitoring)

Three layers of admin-facing safety sit on top of the sandbox.

### Master kill-switch ("Deny")
Settings → Plugin system → **Deny & stop all plugins** immediately stops every
running plugin process and marks the whole system *denied*. While denied, the
plugin controls are locked and nothing can launch — even enabled plugins stay
down across restarts. Re-allowing requires a typed confirmation (`ALLOW`), and
does **not** auto-restart anything: the admin must deliberately re-enable the
system and each plugin. Use this the instant something looks wrong.

### Lockdown mode
A toggle that makes the violation policy maximally strict: **any single detected
violation auto-disables the offending plugin immediately**. Recommended whenever
untrusted third-party plugins are installed. (Even without lockdown, the default
is already to auto-disable on the first violation — lockdown also records the
action as a lockdown event and applies uniformly.)

### Runtime violation monitor
While plugins run, the host polls each plugin process (via `/proc` on Linux) for
signs of leak or escape attempts and records them to an audit trail shown on the
Plugins page:

| Violation | Meaning | Severity |
|---|---|---|
| `child_process` | Plugin spawned a subprocess (attempted exec/fork) | critical |
| `external_file` | Open write handle outside its sandbox dir | critical |
| `network_socket` | Opened a network socket beyond the host channel | critical |
| `memory_exceeded` | Resident memory over its manifest cap | high |
| `dir_bloat` | Its storage dir grew abnormally (possible staging) | medium |

On detection the plugin is stopped, marked disabled so it won't relaunch, and
the violation is surfaced in the UI with what it attempted and the action taken.

> **Prevention vs. monitoring — read this.** The monitor is a *safety net and
> audit trail*, not the primary defense. On a fully sandboxed host the dangerous
> actions are already *prevented* at the OS layer (see below); the monitor
> mostly confirms the sandbox is holding and catches resource abuse. On a host
> *without* full sandboxing, the monitor is detect-then-kill — it reacts quickly
> but a determined plugin could act in the gap before the kill lands. That is
> why untrusted plugins should only run on Linux with bubblewrap.

### seccomp syscall filtering (prevention)
Inside each plugin process, before any plugin code runs, a seccomp-bpf filter is
installed that blocks dangerous syscalls at the kernel level and cannot be
removed by the plugin (`NO_NEW_PRIVS`):

- process/exec: `execve`, `execveat`, `fork`, `vfork`, `clone`, `clone3`
- escape/priv: `ptrace`, `mount`, `pivot_root`, `chroot`, `setuid`/`setgid` family, `bpf`, `kexec_*`, `init_module`, `unshare`, `setns`

This turns "spawn a process" or "load a kernel module" from something the monitor
*detects after the fact* into something the kernel *refuses outright*. If
libseccomp bindings aren't importable in the running interpreter, the runner
logs that syscall filtering is inactive and relies on namespace + resource
limits; the admin UI reports the reduced posture. Network egress is blocked by
the network namespace (no interface) rather than seccomp, so the host↔plugin
loopback channel keeps working.

---

## Operating the system

1. **Enable the system** — Settings → Plugin system → enable, choose storage
   backend (database or file), set the plugins directory. Restart the server.
2. **Install a plugin** — either drop its folder into the plugins directory (it
   appears under "Discovered on disk" → Install), or upload a `.zip` bundle on
   the Plugins page.
3. **Enable + grant** — click Enable, review the requested permissions and their
   risk, uncheck any you don't want to grant (hook-required ones are mandatory),
   confirm. The plugin launches immediately.
4. **Monitor** — the Plugins page shows live status, crash counts, last errors,
   and a per-plugin audit log (install/enable/disable/crash/auto-disable).
5. **Disable / uninstall** — one click; the process is stopped and the token
   revoked.

### Verifying the runtime before you trust it

Two scripts prove the plugin runtime actually works on your host (run them
inside the backend container, where grpcio and the compiled stubs exist):

- **`python -m plugins.smoke_test`** — launches a real plugin over real gRPC and
  exercises the full round-trip: the host initializes the plugin, pings it,
  delivers an event, the plugin's handler calls a host capability
  (storage) back, and the value is confirmed persisted host-side, then a clean
  shutdown. Exit code 0 means the protocol and capability plumbing work. Run this
  once after deploying, and any time you change the proto or the SDK.
- **`python -m plugins.preflight_sandbox`** — reports what OS-level isolation
  your host can actually provide (bubblewrap, seccomp, rlimits) and prints the
  posture: FULL, PARTIAL, MINIMAL, or NONE. Run untrusted third-party plugins
  only when this reports FULL. It also prints the exact sandboxed launch command
  the manager will use, so you can see the isolation for yourself.

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
