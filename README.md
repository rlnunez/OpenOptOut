# PrivacyShield

**Open-source personal data removal pipeline.** Remove yourself, your family, or an entire community from 400+ data brokers, track opt-out status, monitor confirmation emails, and automatically schedule re-checks so brokers can't quietly re-list you.

Built for two audiences from the same codebase:

- **Families** — one system, multiple members, role-based access so parents can manage their kids' data and spouses can manage each other's.
- **Institutions** (libraries, HR departments, credit unions) — white-label branding, SSO/LDAP/SIP2 authentication, patron self-service, PostgreSQL for scale, database encryption, and usage reporting.

> **License:** GNU AGPL-3.0. You may use, modify, and self-host freely; if you run a modified version as a network service, you must make your source available to its users. See [License](#license).

---

## Why this exists — and why it shouldn't have to

PrivacyShield is a **stopgap.** It should not need to exist.

That ordinary people must repeatedly hunt down hundreds of data brokers and beg, form by form, to remove their own information — only to be re-listed weeks later — is evidence of a broken system. Opting out, over and over, is a symptom, not a solution. People should own their own data by default, and no one should have to **pay a third party** to reclaim what was always theirs. This project is free and open-source precisely because the right to your own information should never sit behind a paywall.

The real fix is not software — it is law. It is the responsibility of **state and federal governments** to guarantee a genuine right to digital privacy: to not have your information collected, sold, and traded from broker to broker without meaningful consent, and to have it deleted permanently rather than temporarily. Until that right is guaranteed and enforced, tools like this are necessary — but necessity is not endorsement of the status quo. Use this to protect yourself and the people you care about today, and push for the day it isn't needed.

### A note to libraries

Article VII of the American Library Association's *Library Bill of Rights* states:

> All people, regardless of origin, age, background, or views, possess a right to privacy and confidentiality in their library use. Libraries should advocate for, educate about, and protect people's privacy, safeguarding all library use data, including personally identifiable information.

As one of the authors of this project — and someone who served on the Intellectual Freedom Committee's Privacy Sub-Committee (Jul 2018 – Jun 2022) and helped draft Article VII — I want to put a direct challenge to the libraries that hold these values as core to their mission. Data brokers traffic in exactly the personally identifiable information Article VII asks libraries to safeguard, which gives every library that takes the principle seriously both an opening and an obligation to help.

This is an invitation, not a demand. I know budgets are tight and that libraries are already stretched into work none of us were trained for in our graduate programs. But there is a place in this for whatever you can give:

- **Deploy it** for your staff and/or patrons as a service, the way you offer reference help or internet access — it was built for institutional use (patron self-service, SSO/LDAP/SIP2, white-label branding). 
- **Contribute** as manpower allows, however you can. Advocate, champion, provide code, report a bug, suggest an improvement, help write suggested wording for legislation (if you have the legal understanding). 
- **Teach your community**, which may matter most of all and needs no deployment at all: weave **digital privacy, social-media literacy, and cyber-safety** into the computer courses you already run, or offer them as workshops.

Finally, **state library associations, the ALA, and other library organizations across the political spectrum** should push for **non-partisan privacy legislation** with real teeth — laws written *without* the loopholes that let data brokers collect, sell, and re-sell information with impunity. Libraries are not, and should not be, political entities; but advocating for a value we hold — privacy — is not the same as taking a political side. For a plain-language starting point — what strong data-broker legislation should accomplish, the loopholes to avoid, and where law librarians and legal professionals can contribute — see [docs/LEGISLATION.md](docs/LEGISLATION.md) (an advocacy guide, not legal advice).

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
- **White-label branding** — custom app name, logo, accent colors, and footer HTML
- **Patron self-service** — patrons manage their own removals without seeing other users' data
- **Single sign-on** — OIDC (Google Workspace, Microsoft 365, Okta), SAML 2.0, LDAP / Active Directory, and SIP2 / SIP2S (library cards)
- **PostgreSQL support** — seamless scaling for thousands of concurrent users
- **Database encryption** — SQLCipher full-database encryption + Fernet column-level encryption
- **Usage reporting** — exportable metrics (total opted-out records, active requests, broker response rates)

---

## Screenshots

| Family Dashboard | Identity Vault |
|:---:|:---:|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Identity Vault](docs/screenshots/vault.png) |
| *Status overview across all family members* | *Store name variants, addresses, phones, emails* |

---

## Quick start

### One-line install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/rlnunez/Privacy-Shield/main/install.sh | sh
```

Detects your situation and does the right thing: uses Docker if it's installed and running, or — on a Debian/Ubuntu host run as root with no Docker — installs natively (systemd + nginx, no containers) instead. Safe to re-run (updates an existing checkout rather than duplicating it; never touches an existing `.env`). Force one path explicitly with `| sh -s -- --docker` or `| sh -s -- --native`; see `install.sh --help` for every flag (custom install directory, git ref, fork URL, etc). Piping a script straight into a shell is a judgment call — if you'd rather read it first, that's exactly what the sections below walk through by hand.

### Docker (manual)

```bash
# 1. Clone
git clone https://github.com/rlnunez/Privacy-Shield.git privacyshield
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

The database is stored in a Docker volume so it persists across restarts. For a real deployment reachable by other people, also turn on HTTPS — see [docs/HTTPS.md](docs/HTTPS.md).

### Local development (no Docker)

For a local development environment with hot reload (FastAPI backend + Vite React frontend) or running Playwright tests directly, see the [Local Development Guide](docs/DEVELOPMENT.md). For institutional production deployments without Docker (systemd + nginx / Windows Service + IIS), see [docs/NATIVE_INSTALL.md](docs/NATIVE_INSTALL.md).

---

## First-time setup checklist

On a fresh install the app shows a create-administrator screen instead of a login page; that account becomes the super admin. A guided **setup wizard** then walks through database, email, branding, and HTTPS deployment. Every step is skippable, and everything it sets can be changed later in Settings. The checklist below covers the same ground plus what comes after:

- [ ] **Email** (wizard or Settings → Email) — connect your dedicated removal inbox via OAuth 2.0 (recommended) or App Password (see [Email setup](#email-setup))
- [ ] **Brokers → Import CSV** — upload `incogni_brokers_enriched.csv` if you have one, or use the pre-loaded list
- [ ] **Family members** — add yourself and family members (Settings → Family Members)
- [ ] **Identity Vault** — fill in name variants, former addresses, and phone numbers for each member (the more identifiers, the better the removal match)
- [ ] **Discovery scan** (optional) — run Discovery to identify which brokers actually list your family before submitting removals
- [ ] **Run removals** — click "Run pending" on the Dashboard, or let the daily scheduler handle it automatically
- [ ] **HTTPS** (production) — run `./scripts/enable-https.sh` (or `.ps1`) to enable Let's Encrypt certificates before inviting users (see [docs/HTTPS.md](docs/HTTPS.md))

---

## User roles

PrivacyShield uses role-based access control. The first registered user is automatically a **Super Admin**.

| Role | What they can do | Best for |
|---|---|---|
| **Super Admin** | Everything: system settings, branding, email config, user roles, database management, view all family data | The person running the server |
| **Admin** | Manage users, view reports, manage broker scripts; cannot change branding, email config, or delete the instance | IT staff, department heads |
| **Manager** | Delegated administrative tasks (e.g. plugin management, broker review) without full system access | Staff managing operations |
| **Parent** | Add/edit family members, manage identity vault, trigger removals, view status | Household heads, library staff |
| **Member** | View their own removal status and identity vault; cannot view other members' data | Children, patrons, individual employees |

---

## Institutional deployments

PrivacyShield is designed from the ground up for libraries, schools, credit unions, and non-profits:

- **Patron self-service:** Users register with their email or library card and manage only their own (and their dependents') data.
- **Single sign-on:** Integrate with your existing identity provider using OIDC, SAML 2.0, LDAP, or SIP2 (see [docs/SSO.md](docs/SSO.md)).
- **White-label branding:** Set your institution's name, logo, accent colors, and custom privacy policy link in the Admin panel.
- **Enterprise database:** Switch to PostgreSQL with mTLS, Kerberos, or Cloud IAM authentication (see [docs/DATABASE.md](docs/DATABASE.md)).

---

## Email setup

PrivacyShield needs an email account to send removal requests and receive confirmations.

> ⚠️ **Use a dedicated address.** Brokers sometimes add opt-out requesters to new marketing lists — containing that in a separate inbox keeps your personal email clean.

Supported providers: **Gmail, Outlook, Yahoo, Fastmail, ProtonMail** (via Bridge), or any standard IMAP/SMTP server.

- **OAuth 2.0 (Recommended — Highest Security):** Connect your inbox using modern token-based OAuth via the setup wizard or Settings → Email (supported for Gmail and Outlook). OAuth eliminates static stored passwords, restricts access strictly to required mail scopes, avoids weakening enterprise tenant policies in Google Workspace or Microsoft 365, and supports automatic token refresh and immediate revocation without altering your main account credentials.
- **App Passwords / SMTP (Fallback):** For providers that do not support OAuth integrations (such as Fastmail, Yahoo, or custom IMAP/SMTP servers), generate a provider-specific App Password in your provider's security settings (e.g. Google Account → Security → App Passwords). Never use your primary account password.

---

## Documentation Hub

Detailed technical guides and architectural specifications are organized in [`docs/`](docs/):

| Guide | Description |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture, pipeline stages, APScheduler jobs, failure diagnostics, and full repository structure |
| [`docs/DATABASE.md`](docs/DATABASE.md) | PostgreSQL scaling, enterprise auth (mTLS, IAM, Kerberos), SQLite migration, and encryption at rest |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Local developer environment setup, Playwright dependencies, and test suite execution |
| [`docs/HTTPS.md`](docs/HTTPS.md) | Production HTTPS setup: managed Caddy container, native certbot/win-acme, and reverse proxies |
| [`docs/SSO.md`](docs/SSO.md) | Single sign-on: OIDC, SAML 2.0, Active Directory / LDAP, and library card (SIP2/SIP2S) authentication |
| [`docs/NATIVE_INSTALL.md`](docs/NATIVE_INSTALL.md) | Production deployment without containers (systemd + nginx on Linux, Windows Service + IIS on Windows) |
| [`docs/INTERPRETER.md`](docs/INTERPRETER.md) | Declarative broker-spec interpretation engine and modern add-on format |
| [`docs/PLUGINS.md`](docs/PLUGINS.md) | Process-isolated gRPC plugin system, capability model, and developer SDK |
| [`docs/LEGISLATION.md`](docs/LEGISLATION.md) | Plain-language advocacy guide and policy principles for comprehensive data-broker legislation |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Comprehensive architectural roadmap and work-item status |

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

We welcome community contributions! High-value areas include:

- **Security & code review** — review our sandboxing, cryptography, and auth architecture (see below).
- **New broker entries** — add brokers via the UI and export JSON.
- **Per-broker form selectors** — map CSS selectors for automated submissions in the Admin panel.
- **Resistant vendor guides** — document working removal methods for difficult brokers.
- **Bug reports & test cases** — help improve platform stability.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for full contribution guidelines, testing instructions, and developer setup.

---

## Security notes

- Credentials (IMAP/SMTP passwords, LDAP/SIP2/OIDC secrets) are encrypted at rest using Fernet symmetric encryption.
- **PII field encryption** — names, addresses, phones, and emails can be Fernet-encrypted before database writes (`FIELD_ENCRYPTION_KEY`).
- **Full-database encryption** — SQLCipher AES-256 encrypts the entire SQLite file (`DB_ENCRYPTION_KEY`). See [`docs/DATABASE.md`](docs/DATABASE.md).
- **Secrets stay out of the app** — database and proxy credentials, certs, and keys are read only from environment variables or mounted files (Docker/K8s secrets, Vault), never stored in the database or settings, never logged.
- The database contains PII — keep your Docker volume secure and off public-facing storage.
- The `SECRET_KEY` env var must be set to a strong random value in production: `openssl rand -hex 32`.
- Generate separate keys for `DB_ENCRYPTION_KEY` and `FIELD_ENCRYPTION_KEY` rather than reusing `SECRET_KEY`.
- All API endpoints are authenticated; the only public route is `/api/health`.
- Role-based access is enforced server-side — a parent cannot access another family's data even with direct API calls, and the child-per-parent limit is enforced on the server.
- **Bot-evasion is honestly scoped** — user-agent rotation and proxies help against IP/UA blocking but do not defeat advanced fingerprinting; see the in-app Help for the full picture.
- **Put it behind HTTPS** before real people use it — staff/patron passwords and SSO tokens should never cross the network in plain HTTP. See [`docs/HTTPS.md`](docs/HTTPS.md).

---

## Development disclosure & security review

PrivacyShield handles sensitive personal information, which demands rigorous security. As the original developer, my personal background in advanced security architecture very is limited. To implement complex subsystems like the Bubblewrap sandbox, gRPC capability broker, SQLCipher database encryption, and SSO integrations, I utilized AI assistants (specifically Claude and Gemini) to help design and write these components. In addition, I also used them to bounce ideas off of for the projects direction, help keep track of the roadmap, and aid in testing. I am one person that has limited time in the day. 

While I have actively reviewed, tested, and worked to understand the code introduced, I am human and know that AI-generated code can carry subtle edge cases. If you have expertise in application security, Linux sandboxing, or cryptography, **community code reviews and security feedback are deeply appreciated.**

Ideally, PrivacyShield will undergo a formal, independent security audit prior to wide-scale institutional deployment. In the meantime, please review the architecture, challenge our assumptions, and report any potential vulnerabilities responsibly via GitHub issues or private disclosure.

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
- [x] Version + git commit logged at startup and served from `GET /api/health` — no ambiguity about what code is actually running
- [x] Broker health tracking with automatic disable of repeatedly failing brokers, plus per-broker enable/disable and priority
- [x] Parent-company email opt-outs — one email to a parent company covering all its child sites, with effectiveness tracking
- [x] First-run setup wizard (database, email, branding, HTTPS deployment)
- [x] OAuth email connection for Gmail and Outlook, via bundled email-provider plugins
- [x] Declarative broker-spec interpreter, live for brokers with an automation script — see [`docs/INTERPRETER.md`](docs/INTERPRETER.md)

**Planned:**
- [ ] Independent security audit & penetration testing — see [`docs/ROADMAP.md`](docs/ROADMAP.md#22-independent-security-audit--penetration-testing)
- [ ] Notification system — email/webhook alerts for overdue re-checks
- [ ] Further mobile-responsive UI improvements
- [ ] Public broker database — community-maintained list with open PRs
- [ ] Per-broker form-selector library — crowd-sourced automation scripts
- [ ] Plugin marketplace / signed plugin distribution

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the complete item-by-item architectural roadmap and implementation status.

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
