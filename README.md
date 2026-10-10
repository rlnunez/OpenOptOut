# OpenOptOut

**Open-source personal data removal pipeline.** Automated opt-out submission, confirmation tracking, and continuous defense against quiet data-broker re-listings.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![WCAG 2.2 AAA](https://img.shields.io/badge/Accessibility-WCAG_2.2_AAA-green.svg)](ACCESSIBILITY.md)
[![Security Policy](https://img.shields.io/badge/Security-Policy-brightgreen.svg)](SECURITY.md)

OpenOptOut is a free, self-hostable privacy automation platform built for two audiences from the same codebase:
- **Families** — Single system with role-based access so parents can manage their children's data and spouses can coordinate removals together.
- **Institutions** (libraries, schools, credit unions, non-profits) — White-label branding, SSO/LDAP/SIP2 authentication, patron self-service, PostgreSQL for scale, database encryption, and privacy reporting.

> **Our Mission:** OpenOptOut is a stopgap. Having to hunt down brokers and beg for your own data is proof of a broken system. You should own your personal records by default. Read our full mission statement and library advocacy notes in [`docs/MISSION.md`](docs/MISSION.md).

---

## Features

- 🛡️ **Encrypted Identity Vault** — Store all name variants, aliases, emails, phone numbers, and addresses in a zero-knowledge, encrypted vault.
- 🔍 **Automated Broker Discovery** — Scan broker databases to pinpoint where your personal listings appear before filing removals.
- ⚡ **Pluggable Removal Engine** — Execute opt-outs via declarative specs or sandboxed gRPC plugins with corporate parent-company batching.
- 📬 **Email Confirmation Tracking** — Monitor a dedicated inbox via OAuth 2.0 or IMAP to match and verify incoming broker removal confirmations automatically.
- 🔄 **Continuous Re-Check Defense** — Automatically re-verify and re-submit requests on a scheduled cadence so brokers cannot quietly re-list you.
- 🏛️ **Built for Scale & Institutions** — Multi-branch partitioning with SIP2/ILS library card login, OIDC/SAML 2.0 SSO, distributed Redis priority workers, and PostgreSQL.
- ♿ **WCAG 2.2 AAA Accessible** — High-contrast themes, dynamic font scaling (100%–150%), reduced motion safety, skip links, and full keyboard/screen-reader support.
- 🔒 **Defense-in-Depth Security** — SQLCipher full-database encryption, Fernet field-level encryption, ephemeral memory zeroization, and container sandboxing.

---

## Preview

| Family Dashboard | Identity Vault |
|:---:|:---:|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Identity Vault](docs/screenshots/vault.png) |
| *Status overview across all family members* | *Store name variants, addresses, phones, emails* |

---

## Quick Start

### One-Line Automated Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/rlnunez/OpenOptOut/main/install.sh | sh
```

The installer automatically detects your environment:
- Uses **Docker Compose** if Docker is installed and running.
- Installs **natively** (systemd + nginx, no containers) on Debian/Ubuntu systems without Docker.
- Safe to re-run: updates an existing checkout without overwriting `.env` configuration.
- To specify explicitly, use `| sh -s -- --docker` or `| sh -s -- --native`. See `install.sh --help` for details.

### Docker Compose (Manual)

```bash
# 1. Clone repository
git clone https://github.com/rlnunez/OpenOptOut.git openoptout
cd openoptout

# 2. Create environment file and generate secret key
cp .env.example .env
# Edit .env and set SECRET_KEY: openssl rand -hex 32

# 3. Start containers
docker compose up -d

# 4. Open http://localhost in your browser
#    The first registered user automatically becomes the Super Admin
```

For real production deployments accessible over a network, always enable HTTPS before inviting users. See [`docs/HTTPS.md`](docs/HTTPS.md).

---

## Documentation Hub

Comprehensive architectural specifications and deployment guides:

| Guide | Description |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture, pipeline stages, APScheduler jobs, failure diagnostics, and repository layout |
| [`docs/HTTPS.md`](docs/HTTPS.md) | Production HTTPS setup: built-in Caddy/Traefik front door, Cloudflare DNS/Tunnel, InCommon, and reverse proxies |
| [`docs/SSO.md`](docs/SSO.md) | Single sign-on integration: OIDC, SAML 2.0, Active Directory / LDAP, and library card (SIP2/SIP2S) logins |
| [`docs/DATABASE.md`](docs/DATABASE.md) | PostgreSQL scaling, enterprise auth (mTLS, IAM, Kerberos), SQLite migration, and SQLCipher encryption at rest |
| [`docs/EMAIL_SETUP.md`](docs/EMAIL_SETUP.md) | Dedicated removal inbox integration: OAuth 2.0 (Gmail/Outlook), App Passwords, and IMAP/SMTP setup |
| [`docs/ROLES.md`](docs/ROLES.md) | Role-based access control (RBAC): Super Admin, Admin, Manager, Parent, and Member permission boundaries |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Local developer environment setup, Playwright browser dependencies, and unit test execution |
| [`docs/NATIVE_INSTALL.md`](docs/NATIVE_INSTALL.md) | Container-free production deployment (systemd + nginx on Linux, Windows Service + IIS on Windows) |
| [`docs/UPGRADING.md`](docs/UPGRADING.md) | Update instructions, automated schema migrations, and legacy storage volume consolidation |
| [`docs/PLUGINS.md`](docs/PLUGINS.md) | Process-isolated gRPC broker plugin system, capability model, and developer SDK |
| [`ACCESSIBILITY.md`](ACCESSIBILITY.md) | WCAG 2.2 AAA conformance statement, high-contrast themes, typography scaling, and assistive technology guide |
| [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) | Community standards, ethical stewardship principles, and enforcement guidelines |
| [`SECURITY.md`](SECURITY.md) | Vulnerability disclosure policy, memory hygiene, cryptographic controls, and security scanning |
| [`docs/MISSION.md`](docs/MISSION.md) | Mission statement, library advocacy notes, and Article VII Library Bill of Rights context |
| [`docs/LEGISLATION.md`](docs/LEGISLATION.md) | Plain-language advocacy guide and policy principles for comprehensive data-broker legislation |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Comprehensive item-by-item architectural roadmap and implementation status |

---

## Community & Contributing

We welcome community contributions, particularly:
- **Security & Architectural Reviews** — Review our sandboxing, cryptography, and auth architecture (see [`CONTRIBUTING.md`](CONTRIBUTING.md)).
- **Broker Selectors & Plugins** — Map new broker form selectors or build gRPC plugins to expand coverage.
- **Accessibility Enhancements** — Verify workflows with screen readers and assistive devices (see [`ACCESSIBILITY.md`](ACCESSIBILITY.md)).
- **Bug Reports & Test Cases** — Help strengthen reliability across platforms.

All community members and contributors are expected to uphold our [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

---

## License & Disclaimer

**GNU Affero General Public License v3.0 (AGPL-3.0).** Copyright © 2026 Robert Nunez.

You are free to use, study, modify, and self-host this software. If you run a modified version as a network service, you must make your modified source code available to users of that service. See [`LICENSE`](LICENSE) for the complete license terms.

*Disclaimer: OpenOptOut submits opt-out requests on your behalf but cannot guarantee compliance from third-party data brokers. Re-check your listings periodically. OpenOptOut is not a legal service and does not provide legal advice.*
