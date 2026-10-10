# Architecture & Project Structure

OpenOptOut is structured as a decoupled web application consisting of a React single-page frontend, a FastAPI REST API with an embedded APScheduler worker, and a pluggable database backend (SQLite by default, PostgreSQL for institutional scale).

---

## System Architecture

```
┌─────────────────────────────────────────────┐
│  Browser (React + Tailwind)                 │
│  served by nginx on port 80                 │
└───────────────┬─────────────────────────────┘
                │ /api/*  proxied to FastAPI
┌───────────────▼─────────────────────────────┐
│  FastAPI (Python 3.12)  port 8000           │
│  JWT auth · role-based access control       │
│  APScheduler background worker              │
└───────────────┬─────────────────────────────┘
                │
┌───────────────▼─────────────────────────────┐
│  SQLite  (swap to Postgres via .env)        │
│  privacy_pipeline.db in Docker volume       │
└─────────────────────────────────────────────┘
```

### Background Scheduler Jobs

Background tasks run inside the API process via APScheduler:

| Job | When | What it does |
|---|---|---|
| **Opt-out sender** | Daily at configured time (burst), or spread out by window / rate-limited / distributed modes | Sends opt-out emails/forms up to the per-member and global daily limits |
| **Email monitor** | Every N minutes (default: 15) | Polls the inbox via IMAP, matches UUID tracking keys, marks confirmations |
| **Recheck scanner** | Daily (30 min after opt-out job) | Re-queues expired confirmed removals for verification |
| **Certificate monitor** | Every 24 hours (runs even when opt-out scheduling is off) | Checks LDAP, SIP2, SAML IdP, and OpenOptOut own HTTPS certificates; alerts admins before expiry |

---

## Pipeline Flow

The full personal data removal pipeline runs in four stages:

1. **Discovery** (`/discovery`) — For each family member, searches web sources and visits broker sites directly to find active listings. Creates pending `RemovalRequest` records only for brokers where a listing was confirmed.
2. **Opt-out engine** — Fires on the daily scheduler job (or manually). For each pending request:
   - `form` method: Playwright navigates to the broker opt-out URL, fills fields using stored CSS selectors, and submits the request.
   - `email` method: Sends an email (via SMTP or email-provider plugins) containing member identifiers and a unique UUID tracking key in the subject line.
   - `manual` method: Queues for human action and marks as sent.
3. **Email monitor** — Polls the dedicated IMAP removal inbox every N minutes. Scans unread messages for UUID patterns, matches them to pending requests, and marks them as `confirmed`.
4. **Re-check scheduler** — Performs a daily scan for confirmed removals that have reached their configured recheck interval (typically 90 days). Automatically re-queues them as `pending` so they go through the pipeline again before brokers can quietly re-list the individual.

---

## Broker Automation & Failure Diagnostics

### Broker Scripts
Per-broker form selectors are stored in the `broker_scripts` database table and editable via the API (`/api/automation/scripts/{broker_id}`) or through the Admin panel:
- CSS selectors for name, email, address, city, state fields
- Submit button selector
- Success indicator (selector or text)
- Extra steps as JSON (for multi-step flows)
- Email template overrides for email-method brokers

For modern add-on style brokers, see the declarative specification engine described in [`docs/INTERPRETER.md`](INTERPRETER.md).

### Automation Failure Screenshots
When an automated form-fill fails, the engine saves a screenshot to `/data/screenshots/` inside the container:
```
{error_type}_{broker_name}_{YYYYMMDD_HHMMSS}.png
```

Common filename prefixes:
- `captcha_spokeo_com_20240615_020143.png` — CAPTCHA was detected
- `timeout_epsilon_com_20240615_020301.png` — Page timed out
- `uncertain_nuwber_com_20240615_020412.png` — Form was submitted but success confirmation could not be verified

To view screenshots from a Docker deployment, copy them out of the container:
```bash
docker cp openoptout-api:/data/screenshots ./screenshots
```

---

## Project Structure

```
openoptout/
├── backend/
│   ├── main.py                    # FastAPI app entry point
│   ├── requirements.txt
│   ├── Dockerfile                 # installs Playwright, bubblewrap, libseccomp
│   ├── models/
│   │   └── database.py            # SQLAlchemy models (users, family, brokers,
│   │                              #   requests, plugins, violations, audit, …)
│   ├── routers/                   # HTTP API, one module per area
│   │   ├── auth.py                # Login, register, JWT, SSO/LDAP/SIP2
│   │   ├── admin.py               # User management, access grants
│   │   ├── brokers.py             # Broker list, import, single-add
│   │   ├── family.py              # Family members + identity vault
│   │   ├── requests.py            # Removal requests, requeue, snooze
│   │   ├── scheduler.py           # Scheduler status, triggers, per-member config
│   │   ├── settings.py            # Appearance, email, proxy, plugin-system config
│   │   ├── branding.py            # White-label branding + logo upload
│   │   ├── reporting.py           # Usage/enrollment/compliance reports + CSV
│   │   ├── database_admin.py      # SQLite→Postgres migration tooling
│   │   ├── email_monitor.py       # Inbox view of matched confirmations
│   │   ├── email_oauth.py         # OAuth connect flow for Gmail / Outlook mailboxes
│   │   ├── automation.py          # Per-broker automation scripts (form selectors)
│   │   ├── parent_companies.py    # Parent-company grouping + email opt-outs
│   │   ├── test_broker.py         # Test broker for validating email delivery
│   │   ├── wizard.py              # First-run setup wizard
│   │   ├── saml.py                # SAML 2.0 service-provider endpoints
│   │   ├── cert_monitor.py        # Certificate expiry status + HTTPS check
│   │   ├── plugins.py             # Plugin install/enable/disable/violations
│   │   ├── consortium.py          # Consortium, library systems, branches, SIP2 routing
│   │   ├── logs.py                # Diagnostic logs, download, verbosity API
│   │   └── help.py                # Admin-editable documentation notes
│   ├── core/
│   │   ├── auth.py                # Password hashing, JWT, RBAC
│   │   ├── auth_providers.py      # LDAP/AD, SIP2/SIP2S, OIDC SSO
│   │   ├── saml_sp.py             # SAML 2.0 service provider (pysaml2)
│   │   ├── sso_policy.py          # Shared sign-in policy for all external logins
│   │   ├── cert_monitor.py        # Daily LDAP/SIP2/SAML/HTTPS certificate checks
│   │   ├── encryption.py          # SQLCipher + Fernet field-level encryption
│   │   ├── db_connection.py       # Enterprise Postgres auth (SSL/mTLS/IAM/Kerberos)
│   │   ├── discovery.py           # Discovery bot (find listings before opting out)
│   │   ├── optout_engine.py       # Opt-out dispatch: interpreter, legacy form-fill, email
│   │   ├── email_send.py          # Email sending (SMTP or provider plugins)
│   │   ├── oauth_engine.py        # OAuth token handling for email providers
│   │   ├── optout_email_template.py # Opt-out email wording (incl. parent companies)
│   │   ├── parent_company.py      # Parent-company grouping + effectiveness tracking
│   │   ├── broker_health.py       # Broker health tracking + auto-disable
│   │   ├── broker_priority.py     # Broker priority (1–5): defaults, rules, import/export
│   │   ├── interpreter/           # Declarative broker-spec engine (add-on reframe)
│   │   │   ├── broker_spec.py     #   the declarative description format
│   │   │   ├── compiler.py        #   spec + member -> executable Job
│   │   │   ├── executor.py        #   dry-run + Playwright executors
│   │   │   ├── script_bridge.py   #   builds a spec from a broker stored script
│   │   │   └── live_test.py       #   run one spec against a real browser
│   │   ├── scheduler.py           # APScheduler jobs (opt-out, email, recheck, certs)
│   │   ├── proxy.py               # Residential proxy presets + rotation
│   │   ├── migrations.py          # Additive schema migrations
│   │   ├── logging_config.py      # Rotating file handler, ring buffer, sanitization
│   │   ├── version.py             # Version + commit reporting
│   │   └── settings_store.py      # Settings file helpers
│   └── plugins/                   # Process-isolated plugin system (see docs/PLUGINS.md)
│       ├── proto/plugin.proto     # gRPC host↔plugin contract
│       ├── permissions.py         # Permission + method-level allowlist catalog
│       ├── manager.py             # Launch, supervise, sandbox, hook dispatch
│       ├── sandbox.py             # bubblewrap/namespace/rlimit sandboxing
│       ├── seccomp_filter.py      # syscall filtering inside plugin processes
│       ├── broker.py              # Capability broker (permission + method gate)
│       ├── extended_capabilities.py # Broker/request/email/fetch/schedule APIs
│       ├── monitor.py             # Runtime violation + egress monitoring
│       ├── storage.py             # Per-plugin DB/file storage
│       ├── layout.py              # Typed plugin folders: <root>/<type>/<id>/
│       ├── bundled/email/         # Built-in email-provider plugins (Gmail, Outlook, Yahoo, SMTP)
│       └── sdk/                   # Plugin author SDK
├── frontend/
│   └── src/
│       ├── pages/                 # Dashboard, Brokers, Family, IdentityVault,
│       │                         #   Scheduled, AdminPanel, Settings, Branding,
│       │                         #   Reporting, DatabaseAdmin, EmailMonitor,
│       │                         #   Discovery, Help, Plugins, PluginHelp, BrokerHealth,
│       │                         #   BrokerPriority, BrokerSubmit, ParentCompanies,
│       │                         #   SetupWizard, Login
│       ├── components/            # Sidebar, Badge, …
│       └── hooks/                 # useAuth, useBranding
├── backend/tests/                 # Self-contained test runner (see tests/TESTING.md)
├── examples/plugins/              # Reference plugins by type: email/, forms/, general/
├── examples/broker-specs/         # Reference broker descriptions (form, email)
├── docs/
│   ├── ARCHITECTURE.md            # System architecture, pipeline flow, and project tree (this doc)
│   ├── DATABASE.md                # PostgreSQL scaling, enterprise auth, and encryption at rest
│   ├── DEVELOPMENT.md             # Local environment setup and dev loop
│   ├── PLUGINS.md                 # Plugin system security model + author guide
│   ├── INTERPRETER.md             # Declarative broker-spec engine + format
│   ├── ROADMAP.md                 # Architectural roadmap (broker-addon engine)
│   ├── SSO.md                     # LDAP/SIP2/OIDC/SAML setup, certs, reverse proxies
│   ├── HTTPS.md                   # Managed (Caddy/Traefik, Let's Encrypt or Cloudflare DNS), Cloudflare Tunnel, native, external
│   ├── NATIVE_INSTALL.md          # Running OpenOptOut with no Docker (systemd / Windows Service)
│   └── LEGISLATION.md             # Advocacy guide for privacy legislation
├── deploy/
│   ├── caddy/entrypoint.sh        # Generates Caddy config from env vars (Docker path — docs/HTTPS.md)
│   ├── caddy/Dockerfile           # Caddy + Cloudflare DNS + rate-limit modules (caddy-extended service)
│   ├── cloudflare/ip-ranges.txt   # Cloudflare's IP ranges, for CLOUDFLARE_PROXY=on
│   ├── traefik/entrypoint.sh      # Same, for the optional Traefik front door (FRONT_DOOR=traefik)
│   ├── tests/acme_e2e.sh          # Real ACME issuance + renewal test (Caddy + Pebble)
│   ├── tests/acme_e2e_traefik.sh  # Same, for the Traefik front door
│   └── native/                    # Native (no-Docker) install: systemd unit, nginx config,
│                                   #   install.sh (Linux), install-native.ps1 (Windows) —
│                                   #   see docs/NATIVE_INSTALL.md
├── scripts/
│   ├── enable-https.sh            # Guided front door + certificate setup/teardown, Docker path, Linux/macOS
│   ├── enable-https.ps1           # Same, Windows PowerShell
│   ├── enable-https.cmd           # Double-click launcher for enable-https.ps1
│   ├── update-cloudflare-ips.sh   # Refreshes deploy/cloudflare/ip-ranges.txt
│   └── enable-https-native.sh     # Guided HTTPS setup/teardown, native (no-Docker) path, Linux
├── docker-compose.yml
├── install.sh                     # One-line installer (curl | sh) — detects Docker vs. native
├── .env.example
├── CONTRIBUTING.md
├── LICENSE                        # AGPL-3.0
└── README.md
```
