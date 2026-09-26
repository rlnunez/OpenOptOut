# PrivacyShield

**Open-source personal data removal pipeline.** Remove yourself, your family, or an entire community from 400+ data brokers, track opt-out status, monitor confirmation emails, and automatically schedule re-checks so brokers can't quietly re-list you.

Built for two audiences from the same codebase:

- **Families** — one system, multiple members, role-based access so parents can manage their kids' data and spouses can manage each other's.
- **Institutions** (libraries, HR departments, credit unions) — white-label branding, SSO/LDAP/SIP2 authentication, patron self-service, PostgreSQL for scale, database encryption, and usage reporting.

> **License:** GNU AGPL-3.0. You may use, modify, and self-host freely; if you run a modified version as a network service, you must make your source available to its users. See [License](#license).

---

## Why this exists — and why it shouldn't have to

PrivacyShield is a **stopgap.** It should not need to exist.

That ordinary people must repeatedly hunt down hundreds of data brokers and beg, form by form, to remove their own information — only to be re-listed weeks later — is evidence of a broken system. Opting out, over and over, is a symptom, not a solution. People should own their own data by default; the burden should not fall on individuals to fight an industry built on quietly buying and selling their lives. And no one should have to **pay a third party** to reclaim what was always theirs — this project is free and open-source precisely because the right to your own information should never sit behind a paywall.

The real fix is not software — it is law. It is the responsibility of **state and federal government** to guarantee a genuine right to digital privacy: to not have your information collected, sold, and traded from broker to broker without meaningful consent, and to have it deleted permanently rather than temporarily. Until that right is guaranteed and enforced, tools like this are necessary — but necessity is not endorsement of the status quo. Use this to protect yourself and the people you care about today, and push for the day it isn't needed.

### A note to libraries

Article VII of the American Library Association's *Library Bill of Rights* states:

> All people, regardless of origin, age, background, or views, possess a right to privacy and confidentiality in their library use. Libraries should advocate for, educate about, and protect people's privacy, safeguarding all library use data, including personally identifiable information.

As one of the authors of this project — and someone who served on the Intellectual Freedom Committee's Privacy Sub-Committee (Jul 2018 – Jun 2022) and helped draft Article VII — I want to put a direct challenge to the libraries that hold these values as core to their mission. Data brokers traffic in exactly the personally identifiable information Article VII asks libraries to safeguard, which gives every library that takes the principle seriously both an opening and an obligation to help.

This is an invitation, not a demand. I know budgets are tight and that libraries are already stretched into work none of us were trained for in our graduate programs. But there is a place in this for whatever you can give:

- **Deploy it** for your patrons as a service, the way you offer reference help or internet access — it was built for institutional use (patron self-service, SSO/LDAP/SIP2, white-label branding), and it's free so budget is never the barrier. Smaller libraries that can't stand it up alone can band together or work with their state library system on shared or consortial deployment.
- **Contribute** as manpower allows — a broker script, a bug report, a few hours of staff time.
- **Teach your community**, which may matter most of all and needs no deployment at all: weave **digital privacy, social-media literacy, and basic cyber-safety** into the computer-basics courses you already run, or offer them as workshops — how data gets collected and sold, how to lock down an account, how to spot phishing, why a broker has your information and what to do about it. This reaches far more people than any tool, on nothing but the expertise your staff already have.
- **Academic libraries**, a particular appeal: you generally have the research capacity and instructional-design experience to build ready-to-use privacy curriculum — lesson plans, slides, handouts — that small public libraries can readily *deliver* but rarely have bandwidth to create. Sharing it across the academic/public divide, ideally routed through **state library commissions and departments** to vet and distribute, keeps every branch from reinventing the same workshop. There are surely better mechanisms than I can lay out here; the point is the resources and the reach already exist on opposite sides of a line we drew ourselves.

Finally, **state library associations, the ALA, and other library organizations across the political spectrum** should push for **non-partisan privacy legislation** with real teeth — laws written *without* the loopholes that let data brokers collect, sell, and re-sell information with impunity. Libraries are not, and should not be, political entities; but advocating for a value we hold — privacy — is not the same as taking a political side. Privacy belongs to everyone regardless of where they sit politically, and libraries have long been among its most credible voices. Individual libraries need not wait on the national bodies: work with your state association to help draft legislation, join existing efforts, or push however you see fit. For a plain-language starting point — what strong data-broker legislation should accomplish, the loopholes to avoid, and where law librarians and legal professionals can contribute — see [docs/LEGISLATION.md](docs/LEGISLATION.md) (an advocacy guide, not legal advice).

---

More than anything, I look forward to the day I can ship a final release of this project — an announcement, a deprecation notice, and guidance for anyone still running it — built around a single message:

> **This project is no longer needed. [House Resolution / Senate Bill XYZ] became law on [date], guaranteeing all within the United States the digital privacy and the right to own their own information that this tool was built to protect in its absence.**

That is the goal. Everything here is meant to make that day arrive sooner — and to protect people until it does.

---

## What it does

Data brokers collect your name, address, phone number, relatives, and more — then sell it to anyone who pays. PrivacyShield automates the removal process:

1. **Identity vault** — store all name variants, emails, phones, and addresses for each member (encrypted at rest)
2. **Broker list** — 400+ pre-loaded brokers with opt-out URLs and methods (form, email, manual), including property-record brokers
3. **Discovery bot** — searches broker sites for a member's listings before opting out, so you only act where there's actually a record
4. **Opt-out engine** — automated Playwright form-fill and SMTP email opt-out with per-member rate limits, user-agent rotation, and optional proxy/IP masking
5. **Email monitor** — polls your removal inbox via IMAP, matches confirmations to requests using UUID tracking keys
6. **Re-check scheduler** — automatically re-queues confirmed removals before brokers can re-list you, with four job-spreading modes
7. **Help & docs** — built-in guides for resistant vendors (Epsilon, Ekata, MyLife, etc.) plus admin-editable notes

**Institutional add-ons:**

8. **White-label branding** — logo, colors, system name, custom welcome and email footer text
9. **Authentication providers** — local, LDAP/Active Directory, SIP2/SIP2S (library patron cards), and OIDC SSO (Google, Microsoft, Okta, Auth0, Keycloak, generic)
10. **Dual-auth login** — separate Staff and Patron tabs so employees sign in one way and patrons another
11. **Encryption at rest** — SQLCipher for the whole database file plus Fernet field-level encryption for PII
12. **PostgreSQL support** — for patron-scale deployments, with enterprise connection auth (SSL, client certs, cloud IAM, Kerberos) and a one-click SQLite→Postgres migration tool
13. **Usage reporting** — enrollment trends, opt-out volume, broker compliance rates, per-member stats, CSV export
14. **Plugin system** — extend the app with process-isolated, OS-sandboxed, permission-gated plugins (custom form-filling, email parsing, event hooks, plugin storage). See [`docs/PLUGINS.md`](docs/PLUGINS.md)

---

## Screenshots

> _Dashboard, broker list, identity vault, scheduled re-checks, and help docs_
>
> _(Add screenshots here after first deployment)_

---

## Quick start

### One-line install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/rlnunez/privacyshield/main/install.sh | sh
```

Detects your situation and does the right thing: uses Docker if it's
installed and running, or — on a Debian/Ubuntu host run as root with no
Docker — installs natively (systemd + nginx, no containers) instead. Safe to
re-run (updates an existing checkout rather than duplicating it; never
touches an existing `.env`). Force one path explicitly with
`| sh -s -- --docker` or `| sh -s -- --native`; see `install.sh --help` for
every flag (custom install directory, git ref, fork URL, etc). Piping a
script straight into a shell is a judgment call — if you'd rather read it
first, that's exactly what the sections below walk through by hand.

### Docker (manual)

```bash
# 1. Clone
git clone https://github.com/rlnunez/privacyshield.git
cd privacyshield

# 2. Create environment file
cp .env.example .env
# Edit .env and set SECRET_KEY to a random string:
#   openssl rand -hex 32

# 3. Start
docker compose up -d

# 4. Open http://localhost in your browser
#    The first user to register becomes the super admin
```

That's it. The database is stored in a Docker volume so it persists across restarts.

For a real deployment reachable by other people, also turn on HTTPS — see
[Institutional deployments](#institutional-deployments) below or
[`docs/HTTPS.md`](docs/HTTPS.md) directly.

### Local development (no Docker)

This is a quick dev loop (hot reload, no systemd/nginx) — for an actual
production deployment without Docker (institutions that can't run container
runtimes), see [`docs/NATIVE_INSTALL.md`](docs/NATIVE_INSTALL.md) instead,
which covers systemd + nginx + certbot on Linux and a Windows Service + IIS +
win-acme on Windows.

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env      # edit SECRET_KEY
uvicorn main:app --reload
# API runs at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
# UI runs at http://localhost:3000
```

---

## First-time setup checklist

After your first login (which creates the super admin account):

- [ ] **Settings → Email** — configure your dedicated removal inbox (Gmail App Password recommended)
- [ ] **Brokers → Import CSV** — upload `incogni_brokers_enriched.csv` if you have one, or use the pre-loaded list
- [ ] **Family members** — add yourself and each family member
- [ ] **Identity vault** — for each member, add all name variants, emails, phones, and past/present addresses
- [ ] **Admin panel** — create accounts for other family members, set roles, grant cross-profile access
- [ ] **Settings → Scheduler** — configure run time and daily opt-out limits
- [ ] Test email connection before enabling the scheduler
- [ ] *(Optional)* **Settings → Plugin system** — only if you intend to extend the app with plugins. Leave disabled unless you need it; if you enable it, read [`docs/PLUGINS.md`](docs/PLUGINS.md) first, especially the security model for untrusted plugins.
- [ ] **HTTPS** — before real people use this, put it behind HTTPS: PrivacyShield manages it for you either way — via Docker's built-in Caddy container (`./scripts/enable-https.sh` / `scripts\enable-https.ps1`) or, for native (no-container) installs, via certbot/win-acme (`scripts/enable-https-native.sh`, or see `docs/NATIVE_INSTALL.md` on Windows) — or point an existing reverse proxy at it (IIS, nginx, a load balancer that already terminates TLS in front of PrivacyShield). The setup wizard's **deployment** step asks which applies. See [`docs/HTTPS.md`](docs/HTTPS.md).

---

## User roles

| Role | What they can do |
|---|---|
| `super_admin` | Full access to everything — all families, all settings, admin panel |
| `parent` | Login access, manages their own profile + any profiles granted by admin |
| `member` | Profile only, no login required — managed by parent(s) |

The first registered user is automatically `super_admin`. All subsequent registrations default to `parent`. Members are created by the super admin and don't need passwords unless you want to upgrade them to `parent` later.

**Family example:** You (super admin) create accounts for your sister-in-law Maria (parent) and her husband Carlos (parent), plus their children Sofia, Diego, and Ana (members). You grant Maria and Carlos mutual edit access to each other's profiles, and both edit access to the children. Maria and Carlos each see all four profiles when they log in. The children have no login.

---

## Institutional deployments

PrivacyShield can run as a white-labeled privacy service for a library, employer, or credit union. Everything below is configured in-app under **Admin → Branding** and **Admin → Database**.

- **White-label branding** — upload your logo, set your colors and system name, add a custom welcome message and opt-out email footer, and optionally hide the "Powered by PrivacyShield" line.
- **Authentication** — enable any mix of local accounts, LDAP/Active Directory, SIP2/SIP2S (library patron barcode + PIN, with presets for Koha, Sierra, Symphony, Polaris, Evergreen, and Alma), and OIDC SSO (Google, Microsoft Entra, Okta, Auth0, Keycloak, or generic).
- **Dual-auth login** — turn on the Staff and Patron tabs so employees authenticate via SSO/LDAP while patrons use their library card. Each tab has its own label and welcome text.
- **Registration control** — open, email-domain-restricted, invite-code-only, or admin-only. Invite codes support expiry and use limits.
- **Scale** — switch to PostgreSQL and use the job-spreading scheduler modes (window / rate-limited / distributed) so a nightly run for thousands of patrons doesn't burst all at once.
- **Reporting** — Admin → Reporting shows enrollment trends, opt-out volume, broker compliance rates, and per-member stats, exportable as CSV for board or grant reporting.
- **HTTPS** — this server might already have its own reverse proxy (nginx, Traefik, a load balancer, or IIS on Windows) terminating TLS in front of this and other services; PrivacyShield's setup wizard has a step for exactly this ("something else already terminates HTTPS"), so it won't suggest a conflicting HTTPS setup of its own on top of it. Point your existing proxy at PrivacyShield's web-serving port and set `FRONTEND_URL`. If Docker isn't an option at all — common at institutions that don't run container runtimes — see [`docs/NATIVE_INSTALL.md`](docs/NATIVE_INSTALL.md) for running PrivacyShield as a native systemd service (Linux) or Windows Service (Windows) instead. See [`docs/HTTPS.md`](docs/HTTPS.md) either way.

**Scale example — a large county library:** a system serving millions of residents could enroll tens of thousands of patrons. That deployment should run PostgreSQL (not SQLite), enable SIP2S for patron login, use distributed or rate-limited job spreading, turn on both encryption layers, and put residential proxies in front of the opt-out engine. See the in-app Help articles "Database scaling," "Enterprise database authentication," and "Avoiding broker blocking" for specifics.

---

## Email setup

PrivacyShield uses **one shared inbox** for all removal requests — outgoing opt-outs go from this address, and incoming confirmations are matched back to the right request using a UUID tracking key embedded in every email subject.

**Recommended: dedicated Gmail account**

1. Create `yourname.removals@gmail.com`
2. Enable 2-Step Verification
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. Generate an App Password for "Mail"
5. In PrivacyShield → Settings → Email, select the Gmail preset
6. Enter the address and App Password (not your Gmail password)
7. Click "Test connection"

Supported providers: **Gmail, Outlook, Yahoo, Fastmail, ProtonMail** (via Bridge), or any custom IMAP/SMTP server.

> ⚠️ Use a dedicated address. Brokers sometimes add opt-out requesters to new marketing lists — containing that in a separate inbox keeps your personal email clean.

**Alternative: OAuth (if App Passwords aren't available)** — some Google
Workspace and Microsoft 365 admin policies disable app passwords entirely, in
which case use the "Connect account (OAuth)" option in the setup wizard
instead: create an OAuth client in the provider's developer console (Google
Cloud Console for Gmail, Azure for Outlook), and register the exact redirect
URI the wizard shows you as an authorized redirect URI on that client before
clicking Connect — skipping that step is what produces Google's "doesn't
comply with OAuth 2.0 policy" / "redirect_uri_mismatch" error. That URI is
computed from whatever address you're using to reach PrivacyShield at the
time, so it needs re-registering if you later move to a different domain or
turn on HTTPS.

---

## Project structure

```
privacyshield/
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
│   │   ├── plugins.py             # Plugin install/enable/disable/violations
│   │   └── help.py                # Admin-editable documentation notes
│   ├── core/
│   │   ├── auth.py                # Password hashing, JWT, RBAC
│   │   ├── auth_providers.py      # LDAP/AD, SIP2/SIP2S, OIDC SSO
│   │   ├── encryption.py          # SQLCipher + Fernet field-level encryption
│   │   ├── db_connection.py       # Enterprise Postgres auth (SSL/mTLS/IAM/Kerberos)
│   │   ├── optout_engine.py       # Playwright form-fill + SMTP opt-out
│   │   ├── broker_health.py       # Broker health tracking + auto-disable
│   │   ├── broker_priority.py     # Broker priority (1–5): defaults, rules, import/export
│   │   ├── interpreter/           # Declarative broker-spec engine (add-on reframe)
│   │   │   ├── broker_spec.py     #   the declarative description format
│   │   │   ├── compiler.py        #   spec + member -> executable Job
│   │   │   └── executor.py        #   dry-run + Playwright executors
│   │   ├── scheduler.py           # APScheduler jobs (opt-out, email, recheck)
│   │   ├── proxy.py               # Residential proxy presets + rotation
│   │   ├── migrations.py          # Additive schema migrations
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
│       └── sdk/                   # Plugin author SDK
├── frontend/
│   └── src/
│       ├── pages/                 # Dashboard, Brokers, Family, IdentityVault,
│       │                         #   Scheduled, AdminPanel, Settings, Branding,
│       │                         #   Reporting, DatabaseAdmin, EmailMonitor,
│       │                         #   Discovery, Help, Plugins, BrokerHealth, BrokerPriority, Login
│       ├── components/            # Sidebar, Badge, …
│       └── hooks/                 # useAuth, useBranding
├── backend/tests/                 # Self-contained test runner (see tests/TESTING.md)
├── examples/plugins/              # Reference plugins (tracker, form-filler, watchdog)
├── examples/broker-specs/         # Reference broker descriptions (form, email)
├── docs/
│   ├── PLUGINS.md                 # Plugin system security model + author guide
│   ├── INTERPRETER.md             # Declarative broker-spec engine + format
│   ├── ROADMAP.md                 # Architectural roadmap (broker-addon engine)
│   ├── SSO.md                     # LDAP/SIP2/OIDC/SAML setup, certs, reverse proxies
│   ├── HTTPS.md                   # Docker (managed) vs. native vs. external reverse-proxy HTTPS
│   ├── NATIVE_INSTALL.md          # Running PrivacyShield with no Docker (systemd / Windows Service)
│   └── LEGISLATION.md             # Advocacy guide for privacy legislation
├── deploy/
│   ├── caddy/entrypoint.sh        # Generates Caddy's config from env vars (Docker path — docs/HTTPS.md)
│   ├── tests/acme_e2e.sh          # Real ACME issuance + renewal test (Caddy + Pebble)
│   └── native/                    # Native (no-Docker) install: systemd unit, nginx config,
│                                   #   install.sh (Linux), install-native.ps1 (Windows) —
│                                   #   see docs/NATIVE_INSTALL.md
├── scripts/
│   ├── enable-https.sh            # Guided HTTPS setup/teardown, Docker path, Linux/macOS
│   ├── enable-https.ps1           # Same, Windows PowerShell
│   ├── enable-https.cmd           # Double-click launcher for enable-https.ps1
│   └── enable-https-native.sh     # Guided HTTPS setup/teardown, native (no-Docker) path, Linux
├── docker-compose.yml
├── install.sh                     # One-line installer (curl | sh) — detects Docker vs. native
├── .env.example
├── CONTRIBUTING.md
├── LICENSE                        # AGPL-3.0
└── README.md
```

---

## Architecture

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
│  privacy_pipeline.db  in Docker volume      │
└─────────────────────────────────────────────┘
```

**Scheduler jobs (run inside the API container):**

| Job | When | What it does |
|---|---|---|
| Opt-out sender | Daily at configured time | Sends opt-out emails/forms up to daily limits |
| Email monitor | Every N minutes (default: 15) | Polls IMAP, matches UUID keys, marks confirmations |
| Recheck scanner | Daily (30 min after opt-out job) | Re-queues expired confirmed removals |

---

## Database

**SQLite by default** — fine for personal, family, and staff deployments (up to a few hundred users).

**PostgreSQL for scale** — required for patron-facing deployments (thousands of users). SQLite's file-level write locking will cause contention under heavy concurrent load; a large library serving tens of thousands of patrons should run Postgres.

Switch via a simple connection string:

```env
DATABASE_URL=postgresql://user:password@host:5432/privacyshield
```

Or use the **structured enterprise connection** (Admin → Database → Connection) for hardened auth — SSL/TLS modes, client-certificate mutual TLS, cloud IAM (AWS RDS / GCP Cloud SQL / Azure AD), or Kerberos/GSSAPI. Secrets are read only from environment variables or mounted files, never stored in the app.

**Migrating an existing SQLite install to Postgres:** use the built-in one-click tool at **Admin → Database → Migrate to Postgres**. It copies every table with integrity preservation and resets sequences. Keep a backup of the SQLite file for 30 days afterward.

### Encryption at rest

Two independent layers, both optional and configurable via `.env`:

- **SQLCipher** (`DB_ENCRYPTION_KEY`) — AES-256 encrypts the entire SQLite file
- **Field-level** (`FIELD_ENCRYPTION_KEY`) — Fernet-encrypts PII columns (names, addresses, phones, emails) before they're written

To migrate an existing unencrypted SQLite database to SQLCipher:

```bash
docker exec privacyshield-api python -m backend.core.encryption migrate
```

For Postgres, use provider-level encryption (RDS storage encryption, Azure TDE, Cloud SQL CMEK) alongside the field-level layer.

---

## Upgrading

```bash
git pull
docker compose down
docker compose build
docker compose up -d
```

The database schema is auto-migrated on startup via SQLAlchemy `create_all` (additive changes only). For destructive schema changes, a migration note will appear in the release notes.

**Upgrading from a pre-consolidation deployment:** older versions used three separate volumes (`db_data`, `screenshots`, `logo_data`); the current `docker-compose.yml` uses a single `app_data` volume mounted at `/data`. If you're upgrading and want to keep existing data, either (a) keep your old `docker-compose.yml` volume definitions, or (b) copy the contents of the old `db_data` volume into the new `app_data` volume before starting. New deployments need no action.

---

## Contributing

This project is early-stage. The most valuable contributions right now:

- **New broker entries** — if you find a data broker not in the list, add it via **Add brokers** in the UI and open a PR with the JSON export
- **Resistant vendor guides** — if you successfully remove from a difficult broker using a method not documented in Help, add a custom note and share it
- **Bug reports** — open an issue with your Docker version, browser, and steps to reproduce
- **Per-broker form selectors** — the opt-out engine fires real submissions, but each broker's form needs CSS selectors mapped (via Admin → Automation Scripts). Contributing verified selectors for brokers is one of the highest-value contributions.

By contributing, you agree your contributions are licensed under the project's AGPL-3.0 license.

Please do not commit `.env`, `*.db`, or `privacyshield_settings.json` — they contain credentials and PII (the `.gitignore` already excludes them).

---

## Security notes

- Credentials (IMAP/SMTP passwords, LDAP/SIP2/OIDC secrets) are encrypted at rest using Fernet symmetric encryption
- **PII field encryption** — names, addresses, phones, and emails can be Fernet-encrypted before database writes (`FIELD_ENCRYPTION_KEY`)
- **Full-database encryption** — SQLCipher AES-256 encrypts the entire SQLite file (`DB_ENCRYPTION_KEY`)
- **Secrets stay out of the app** — database and proxy credentials, certs, and keys are read only from environment variables or mounted files (Docker/K8s secrets, Vault), never stored in the database or settings, never logged
- The database contains PII — keep your Docker volume secure and off public-facing storage
- The `SECRET_KEY` env var must be set to a strong random value in production: `openssl rand -hex 32`
- Generate separate keys for `DB_ENCRYPTION_KEY` and `FIELD_ENCRYPTION_KEY` rather than reusing `SECRET_KEY`
- All API endpoints are authenticated; the only public route is `/api/health`
- Role-based access is enforced server-side — a parent cannot access another family's data even with direct API calls, and the child-per-parent limit is enforced on the server
- **Bot-evasion is honestly scoped** — user-agent rotation and proxies help against IP/UA blocking but do not defeat advanced fingerprinting; see the in-app Help for the full picture
- **Put it behind HTTPS** before real people use it — staff/patron passwords and SSO tokens should never cross the network in plain HTTP. Either let PrivacyShield manage it (`./scripts/enable-https.sh` / `.ps1`) or point an existing reverse proxy at it; see [`docs/HTTPS.md`](docs/HTTPS.md).

---

## Roadmap

**Shipped:**
- [x] Opt-out engine — Playwright form-fill and SMTP email sending
- [x] Email monitor UI — live inbox view with matched confirmations
- [x] Discovery bot — searches broker sites for listings before opting out
- [x] SQLite → Postgres one-click migration tool
- [x] Database encryption (SQLCipher + field-level)
- [x] Enterprise database auth (SSL, client certs, cloud IAM, Kerberos)
- [x] White-label branding + institutional auth (LDAP, SIP2/SIP2S, OIDC SSO)
- [x] Dual-auth login (staff + patron tabs)
- [x] Usage reporting with charts and CSV export
- [x] User-agent rotation + proxy/IP masking + job-spreading modes
- [x] Property-record broker support (deeds, mortgages, formal names)
- [x] Plugin system — process-isolated, OS-sandboxed, permission-gated extensions
- [x] SAML 2.0 SSO for staff (self-hosted Keycloak/Authentik to university Shibboleth IdPs), LDAPS/StartTLS hardening, SIP2-over-TLS with mandatory verification, and certificate-expiry monitoring/reminders — see [`docs/SSO.md`](docs/SSO.md)
- [x] Built-in HTTPS — Docker (managed via an optional Caddy container), native no-container installs (certbot/win-acme), or an existing reverse proxy (external) — see [`docs/HTTPS.md`](docs/HTTPS.md) and [`docs/NATIVE_INSTALL.md`](docs/NATIVE_INSTALL.md)
- [x] Version + git commit logged at startup and served from `GET /api/health` — no ambiguity about what code is actually running (see `docs/ROADMAP.md` item 16 for the larger in-app log viewer / adjustable verbosity work this is the first piece of)

**Planned:**
- [ ] Notification system — email/webhook alerts for overdue re-checks
- [ ] Further mobile-responsive UI improvements
- [ ] Public broker database — community-maintained list with open PRs
- [ ] Per-broker form-selector library — crowd-sourced automation scripts
- [ ] Plugin marketplace / signed plugin distribution

> **Real-world testing needed:** many enterprise integration paths (SIP2 client certs, cloud IAM, live proxy providers, specific ILS quirks) and the plugin system's gRPC/sandbox runtime are validated for correctness but need testing against real infrastructure in your environment before production use. Full plugin OS-sandboxing requires Linux + bubblewrap (installed in the Docker image).

---

## License

**GNU Affero General Public License v3.0 (AGPL-3.0).** Copyright © 2026 Robert Nunez.

You are free to use, study, modify, and self-host this software. The AGPL adds one key obligation beyond the regular GPL: **if you run a modified version as a network service (SaaS), you must offer that service's users access to your modified source code.** This keeps the project — and any derivatives, including hosted ones — open source, while ensuring the original author is always credited.

In short:
- ✅ Use it, fork it, customize it for your organization
- ✅ Deploy it internally or as a public service
- ✅ Credit is preserved through the retained copyright and license notices
- ⚠️ Derivatives must also be AGPL-3.0, and hosted/modified versions must share their source

See the [`LICENSE`](LICENSE) file for the full text. If you contribute improvements, consider opening a PR so the whole community benefits.

> **Note for maintainers:** the `LICENSE` file ships with the copyright block plus instructions to insert the canonical AGPL text. Run `bash scripts/finalize-license.sh` once (with internet access) to assemble the complete file, or select "GNU AGPL v3.0" in GitHub's license picker when creating the repo.

---

## Disclaimer

This tool submits opt-out requests on your behalf but cannot guarantee compliance from data brokers. Some brokers are legally required to honor removal requests under CCPA (California) or GDPR (EU); others are not. Re-check your listings periodically — brokers frequently re-list individuals from new data sources. PrivacyShield is not a legal service and does not provide legal advice.

---

## Playwright setup (local development)

When running locally (outside Docker), install Playwright's Firefox browser after installing Python dependencies:

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
playwright install firefox
playwright install-deps firefox
```

Docker handles this automatically in the build step.

## Automation failure screenshots

Failure screenshots from the automation engine are saved to `/data/screenshots/` inside the Docker volume. File names follow the pattern:

```
{error_type}_{broker_name}_{YYYYMMDD_HHMMSS}.png
```

Examples:
- `captcha_spokeo_com_20240615_020143.png` — CAPTCHA was detected
- `timeout_epsilon_com_20240615_020301.png` — page timed out
- `uncertain_nuwber_com_20240615_020412.png` — submitted but success unclear

To view screenshots, copy them out of the Docker volume:
```bash
docker cp privacyshield-api:/data/screenshots ./screenshots
```

## Pipeline flow

The full pipeline runs in this order:

1. **Discovery** (`/discovery`) — for each family member, searches Google and visits broker sites directly to find active listings. Creates pending `RemovalRequest` rows only for brokers where a listing was confirmed.

2. **Opt-out engine** — fires on the daily scheduler job (or manually). For each pending request:
   - `form` method: Playwright navigates to opt-out URL, fills fields using stored CSS selectors, submits
   - `email` method: sends SMTP email with UUID tracking key in subject line
   - `manual` method: queues for human action, marks as sent

3. **Email monitor** — polls IMAP inbox every N minutes. Scans unseen messages for UUID patterns, matches them to pending requests, marks as `confirmed`.

4. **Re-check scheduler** — daily scan for confirmed removals past their recheck date. Re-queues them as `pending` so they go through the pipeline again.

## Broker scripts

Per-broker form selectors are stored in the `broker_scripts` database table and editable via the API (`/api/automation/scripts/{broker_id}`). Each script stores:

- CSS selectors for name, email, address, city, state fields
- Submit button selector
- Success indicator (selector or text)
- Extra steps as JSON (for multi-step flows)
- Email template overrides for email-method brokers

The admin UI for managing scripts is in the Admin panel. This table is community-maintained — if you figure out the selectors for a broker, please contribute them back.
