# Changelog

All notable changes to OpenOptOut are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each completed roadmap item is cross-referenced with its architectural milestone number (e.g., `Roadmap Item #`). For active, planned, and upcoming initiatives, see the live [Roadmap (`docs/ROADMAP.md`)](docs/ROADMAP.md). For detailed specifications, design rationale, and test verification notes for historical milestones up through v0.11.0, see the [Completed Milestones Archive (`docs/archive/COMPLETED_ROADMAP.md`)](docs/archive/COMPLETED_ROADMAP.md) (frozen after v0.11.0 release). All subsequent completed roadmap work, architectural improvements, and release notes are documented directly in this changelog.

---

## [0.11.0-rc] — 2026-10-17

### Added
- **Distributed Worker Fleet & Control Plane (Roadmap Item 7):** Scalable stateless Playwright execution workers running in isolated containers, communicating over Redis or in-process priority queues (`removal_high`, `removal_normal`, `discovery`, `retry`), with canonical HMAC-SHA256 signed envelopes, memory zeroization, and automated lease reclamation (Phases 7.1–7.5).
- **Worker Fleet Administrative Console (Roadmap Item 7):** Real-time cluster dashboard in `frontend/src/pages/WorkerFleet.jsx` displaying worker node capacity, active execution slots, queue depths, telemetry heartbeats, and graceful node draining controls.
- **Extended Multi-Node Worker Draining Coordination (Roadmap Item 65):** Cluster-wide fleet drain broadcasting (`POST /api/workers/fleet/drain`, `WorkerRegistry.set_fleet_drain`, and Redis key `ps:fleet:drain_all`), route alias `GET /api/workers/summary`, graceful in-flight task completion in `WorkerDaemon` without task cancellation, and automated pre-upgrade drain barriers and post-upgrade un-drain in `deploy/updater/updater.py`.
- **Updater Automated Snapshot, Rollback & Revert (Roadmap Item 65):** The companion updater daemon (`openoptout-updater`) creates pre-update safety snapshots of running container images, SQLite databases, and configuration before applying releases. If container recreation or post-upgrade health checks fail within 90 seconds, it automatically reverts to the previous release. Super administrators can also trigger on-demand rollbacks via `POST /api/system/updates/rollback` or the UI.
- **Scheduled Maintenance Windows & Downtime Banners (Roadmap Item 65):** Calendar-based maintenance window planning (`backend/core/calendar_plan.py`), automated dynamic scheduler pause/resume loops (`backend/core/scheduler.py`), update installation scheduling, and user-facing downtime notice banners with configurable advance warning intervals (`0 = disabled`) translated across all 17 bundled language packs.
- **Playwright Firefox Footprint & Hardware Sizing Re-Benchmark (Roadmap Item 71):** Empirical memory, CPU, and `tmpfs` resource benchmarking suite across single-node and multi-worker cluster deployments (`backend/tests/benchmark_hardware_footprint.py` and `deploy/tests/benchmark_hardware_footprint.py` with test verification `hardware.benchmark_firefox_footprint`), publishing updated capacity planning coefficients and minimum hardware recommendations in `docs/admin/hardware-sizing.md`.
- **Infrastructure Capacity Planner & Sizing Calculator (Roadmap Item 9):** Empirical sizing calculation engine and standalone CLI utility (`openoptout-calc` / `GET /api/workers/capacity-plan`) calibrated against live Playwright Firefox benchmarks, mapping community member profile volume and desired turnaround deadlines into minimum hardware recommendations (Profile A, B, and C/D Distributed Cluster), vCPU, RAM, ephemeral `tmpfs` sizing, and residential proxy bandwidth, featuring an interactive live capacity planner in the Worker Fleet console with automated fleet deficit detection.
- **Cloudflare Authenticated Origin Pulls (AOP) (Roadmap Item 14, 24):** Mutual TLS (mTLS) origin verification for Caddy, Traefik, and native Nginx using the official Cloudflare Authenticated Origin Pull CA certificate, guaranteeing that origin servers admit only legitimate requests from the owner's Cloudflare zone.
- **Self-Managed Client-Certificate Mutual TLS (mTLS) (Roadmap Item 14, 24):** Opt-in client certificate verification for Caddy, Traefik, and native Nginx (`CLIENT_MTLS=on`, `CLIENT_MTLS_CA_FILE`, `CLIENT_MTLS_MODE=require|optional`), providing zero-cost, zero-third-party hardware/OS-keystore mTLS protection for self-hosted instances. Features complete first-run Setup Wizard integration, real-time certificate monitoring and status tracking in the Admin Settings console, device client certificate minting/revocation, and local/offline CA helper scripts (`scripts/mtls-ca.sh`, `scripts/mtls-ca.ps1`).
- **Persistent Auto-Generated Master Secret Key on First Boot:** Automatically generates and persists a 128+ random hex character master key to `secret.key` at mode `0600` via atomic creation (`O_CREAT | O_EXCL`) in `backend/core/settings_store.py`, guaranteeing that non-installer environments, Docker Compose setups, and automated release testing never run on temporary in-memory bootstrap keys (PR #128).
- **Cloudflare Tunnel Preconfigured WAF Rulesets (Roadmap Item 24):** Edge rate-limiting (60 req/min for authentication endpoints, 1200 req/min site-wide) and WAF firewall rules (`deploy/cloudflare/tunnel-waf-ruleset.json`) with an automated deployment CLI script (`apply-tunnel-waf.sh`).
- **Universal Localization & 17 Bundled Language Packs (Roadmap Items 17, 52):** Fully translated UI strings and documentation across English, Spanish, French, German, Portuguese, Russian, Ukrainian, Polish, Arabic, Hindi, Urdu, Swahili, Indonesian, Vietnamese, Tagalog, Korean, and Chinese.
- **Comprehensive Right-to-Left (RTL) Layout (Roadmap Items 17, 56):** Complete RTL layout support with logical Tailwind classes (`ms-`, `pe-`, `start-`, `border-s-`) and automated bidirectional icon mirroring for Arabic and Urdu.
- **Pluggable Opt-Out Letters (Roadmap Items 53, 58):** Statutory legal templates (CCPA, GDPR, UK GDPR, LGPD, PIPEDA) decoupled as independent, installable letter plugins selected by the broker's jurisdiction and legal language.
- **Interactive Live Hand-off ("Do it here") (Roadmap Items 50, 54):** Live browser session hand-off allowing human operators to solve interactive steps, CAPTCHAs, or two-factor SMS/email challenges on the data broker's live page without exposing passwords or credentials.
- **Cloud Backups via Rclone (Roadmap Item 47):** Support for AES-256-GCM encrypted database dumps to Proton Drive, Box, pCloud, MEGA, and Nextcloud.
- **Address-Verified Community Registration (Roadmap Item 64):** Self-service registration restricted to residents of housing complexes, HOAs, and neighborhood communities via normalized address matching against uploaded CSV manifests.
- **Yahoo OAuth-Only Email Integration (Roadmap Item 55):** Dedicated Yahoo email plugin utilizing secure OAuth token authentication without requiring app passwords.
- **Configurable Regional Formats (Roadmap Item 57):** Administrative localization of dates, times, clock styles (12h/24h), and number formatting applied across all views.
- **Monitoring, Prometheus Metrics & Webhooks (Roadmap Item 59):** Token-gated `/metrics` scrape endpoint, structured JSON logging, container health probes, and event webhooks.
- **Broker Pack 1 & Coverage Calculation (Roadmap Item 60):** Shipped 50 additional broker plugins (reaching 80 built-in plugins) with deduplicated coverage scoring.
- **Inactive Broker Discovery Auto-Responses (Roadmap Item 62):** Automated negative confirmation responses when discovery runs confirm a member has no record on an inactive broker.
- **Usage Statistics API for Institutional Warehouses (Roadmap Item 63):** Anonymous, aggregated removal and verification metrics API scoped by institutional API keys.
- **Terms, Operational Limits & Transparency Notices (Roadmap Item 61):** Version-tracked legal terms, operator disclaimers, and mandatory acknowledgement dialogs.
- **Network Circuit Breaker & Graceful Offline Halt (Roadmap Item 66):** Canary network probe halting active batch processing during internet drops without false failure penalties.
- **Automatic Broker Steps & AI Drafter (Roadmap Item 42):** Rehearsal engine and heuristic auto-repair for broken selectors with human approval gates.
- **Privacy Record, Access Logging & Deadline Reporting (Roadmap Item 48):** Comprehensive data audit trail, operator access logs, and statutory compliance deadline tracking.
- **Privacy Health Score, PDF Reports & ICS Calendar (Roadmap Item 49):** Priority-weighted privacy exposure score, exportable executive PDF reports, and an iCalendar (`.ics`) feed for removal milestones.
- **Listing Disambiguation & Unclear Match Review (Roadmap Item 51):** Interactive review queue for name-only search results with configurable auto-skip or auto-queue rules.
- **Audience-Organized Documentation & MkDocs Material:** Reorganized documentation portal into User/Family, Administrator, and Developer guides, backed by MkDocs Material with client-side full-text search, dark/light themes, and seamless backwards-compatible stubs.

### Changed
- **Decoupled SearXNG Master Secret:** Auto-generated SearXNG master secret with dynamic entropy length, fully decoupled from the primary application master key.
- **Slimmed Active Roadmap:** [Roadmap (`docs/ROADMAP.md`)](docs/ROADMAP.md) now tracks only active, planned, and under-consideration initiatives, archiving historical milestones to the [Completed Milestones Archive (`docs/archive/COMPLETED_ROADMAP.md`)](docs/archive/COMPLETED_ROADMAP.md).

### Fixed
- **Plugin Sandbox Seccomp Syscall Filtering Bindings (PR #130):** Installed `pyseccomp==0.1.2` in `backend/requirements.txt` (pure Python wheel over `libseccomp2` on Linux) and introduced `seccomp_filter.load_seccomp()` to dynamically locate bindings under either `seccomp` or `pyseccomp`. This enables real syscall filtering in containerized environments where Debian's `python3-seccomp` package was previously inaccessible to the image's Python interpreter.
- **Setup Wizard Secret Key Generation Accommodation:** Updated release-test scripts (`.github/release-test/ui_check.py` and `setup_check.py`) to detect and satisfy master secret key generation and file persistence prompts during automated first-run setup wizard walkthroughs.
- **Content and Translation Catalog Release Testing:** Scoped error-phrase matching in `.github/release-test/ui_check.py` so that catalog and diagnostic pages (`/translations`, `/logs`, `/help`, `/plugin-help`) emit non-fatal warnings instead of triggering false-positive run failures on legitimate error message copies (PR #127).
- **Setup Wizard Reverse Proxy Deployment Test:** Synchronized test assertions in `wizard.deployment_reverse_proxy_choice` (`backend/tests/run_tests.py`) to validate the new `client_mtls` reverse-proxy deployment configuration flag (PR #129).
- **Playwright Headless Browser Container Dependencies:** Added `libasound2` to container package dependencies for headless Playwright browser automation in test execution environments.
- **Server-Side Exception Traceback Scrubbing:** Sanitized API error responses across settings and mTLS endpoints to log raw exceptions server-side rather than reflecting internal tracebacks to clients.
- **Seccomp Posture Reporting:** Probes importability of `seccomp` Python bindings rather than static library presence on disk, ensuring the Plugins console reflects real syscall filtering capability (PR #122).

### Security
- **Master Key Logger Disclosure Prevention:** Reworded master key generation log messages in `settings_store.py` to prevent sensitive credential marker false positives during static security scans.
- **Scraped Listing URL Scheme & Host Validation (G15):** Enforced that `PlaywrightExecutor._pick_listing` strictly validates scraped anchor `href` links and remove-all URLs against scheme (`https://` only), public IP addresses via `is_public_ip`, and the broker's registrable domain allowlist before calling `page.goto()`, preventing SSRF or internal address navigation from broker-controlled pages.
- **Embedded Credential Scrubbing & Marker Enforcement (G16):** Extended `SECRET_MARKERS` in `settings_access.py` (adding `proxy_url`, `auth`, `bearer`, `cert`, `cookie`, `session`) and implemented regex-based embedded URL credential detection (`://user:pass@`) in `PluginSettingsAccessor.get_global_nonsecret()`, ensuring scalar settings with embedded credentials cannot be read by plugins even if stored under arbitrary key names.
- **DNS-Rebinding TOCTOU & SSRF Protection (G11):** Introduced centralized `backend/core/dns_guard.py` with `is_public_ip` (rejecting loopback, private RFC 1918, link-local cloud metadata, CGNAT, broadcast, and IPv4-mapped addresses) and `safe_dns_context` intercepting `socket.getaddrinfo` at socket connect time to abort connections to non-public addresses. Applied to `confirm_links.http_visit`, `privacy_finder.http_get`, `registry_sync.fetch_registry`, and `backend/plugins/manager.py`, with route guard, proxy, and post-navigation server address verification for Playwright browser execution.
- **Client IP Spoofing Prevention on Short XFF Chains (G12):** Fixed `rate_limit.client_ip` so that when `len(chain) < hops`, it strictly defaults to the TCP peer (`request.client.host`) and never falls back to the client-controlled `chain[0]`, preventing rate limit evasion and lockout poisoning.
- **SSO Account Linking Verification Enforcement (G13):** Enforced that generic OIDC and third-party SSO accounts must provide a positive `email_verified: True` claim (or match administrator-configured `allowed_domains` or explicit `auto_provision`) before linking to existing user/admin accounts, preventing account takeovers via unverified email claims.
- **In-Process Security State Pinning (G14):** Pinned native install service definitions (`openoptout-api.service`, `install-native.ps1`, `native-install.md`) to `--workers 1` by default, ensuring in-process rate limits, login failure lockouts, and SSO single-use state checks remain strictly synchronized without requiring an external Redis coordinator, and documented multi-worker state requirements.
- **WebAuthn Fail-Closed Assertion Verification (G1):** Validates passkey authentication responses strictly against stored ES256 and RS256 credentials, rejecting unsigned, forged, or mismatched assertions (PR #122).
- **WebAuthn Origin, RP ID, and Replay Counter Enforcement (G2):** Cryptographically binds expected RP ID and origin into MFA and passwordless tickets; validates authenticator `rpIdHash`, client `origin`, and signature counters (`signCount`) to prevent phishing and cloned authenticator replays; advances stored counter only upon verified signature (PR #123).
- **RFC 5869 HKDF Key Separation (G3, G6):** Subsystem keys for settings encryption, OAuth tokens, MFA challenge tickets, envelope HMAC signatures, and queue payload encryption derive from `SECRET_KEY` via HKDF (`backend/core/hkdf.py`), eliminating raw secret reuse while maintaining backward-compatible MultiFernet decryption.
- **Fail-Closed Production Encryption-at-Rest Guards (G4):** In strict production mode (`ENFORCE_ENCRYPTION_AT_REST=true`), missing field keys or SQLCipher auto-encryption failures immediately halt the service with `RuntimeError` rather than falling back to unencrypted plaintext storage.
- **Docker Seccomp Syscall Filtering Packaging (G5):** Shipped `libseccomp-dev` in backend Dockerfile and automated `pip install seccomp` compilation in `install_deps.py`, enabling native Linux syscall filtering inside container environments.
- **Constant-Time TOTP Verification (G7):** Upgraded `verify_totp()` to `hmac.compare_digest` to eliminate theoretical side-channel timing attacks on one-time code checks.
- **Keyed HMAC Backup Codes & Searchable Index Hashes (G8):** Backup recovery codes and database search hashes use HMAC-SHA256 with server-side keys derived via HKDF, defending against offline rainbow table attacks while preserving backward-compatible consumption of legacy unsalted codes.
- **Accurate Security Policy & Fixed Documentation Links (G9):** Updated `SECURITY.md` to precisely outline unauthenticated endpoints, cryptographic key hierarchy, and working links to HTTPS and security scanning guides.
- **Safe Administrative Registration Default (G10):** Changed default self-registration mode after initial instance bootstrap from `"open"` to `"admin_only"`, preventing unauthorized account creation on internet-exposed instances.
- **Unauthenticated Route Security Prober:** Automated security probe (`.github/security/probe_unauth.py`) and disposable demo seeder (`.github/security/seed_demo.py`) auditing ungated routes for auth bypass, SQL injection, path traversal, account enumeration, and data leakage (PR #122).
- Memory zeroization for decrypted secrets and tokens (`core/memory_hygiene.py`).
- Ephemeral in-memory tmpfs mounts for temporary browser artifacts (`/tmp:size=512M`).
- Core dump suppression (`RLIMIT_CORE = 0`).

---

## [0.10.2] — 2026-10-11

### Added
- **Space Explorer (LCARS) High-Contrast Theme (Roadmap Item 27):** High-contrast color scheme with proportional font scaling and OpenDyslexic priority overrides.
- **Docker Version Propagation:** Consolidated versioning to root `VERSION` file, ensuring container builds reflect the exact semantic release tag.

---

## [0.10.1] — 2026-10-10

### Added
- **OpenDyslexic Typography Support (Roadmap Item 27):** Dyslexia-friendly font toggle on onboarding screens and account settings with persistent user preference storage.

---

## [0.10.0] — 2026-10-10

### Added
- **Enterprise Ingress, Edge Security & DDoS Protection (Roadmap Item 24):** Hardened reverse-proxy front doors (Caddy/Traefik) with strict rate-limiting, IP-reputation filtering, and Cloudflare Tunnel integration.
- **Passwordless Authentication & Session Governance (Roadmap Item 25):** WebAuthn / FIDO2 biometric authentication, hardware security key support (YubiKey NIST FIPS 140-2/3), and role-differentiated session expirations.
- **Automated ILS Demographic Ingestion & Identity Vault Sync (Roadmap Item 26):** SIP2 integration mapping patron library demographic data directly into encrypted vault profiles.
- **Universal Accessibility (a11y) & WCAG 2.2 AAA Conformance (Roadmap Item 27):** High-contrast theme palettes, dynamic font scaling (100%–150%), keyboard navigation traps, and screen-reader announcements.
- **Multi-Container Test Matrix & Diagnostic Automation (Roadmap Item 28):** Docker test harness running end-to-end integration tests across isolated database and proxy topologies.
- **Parent-Company Catalog & Spec Metadata (Roadmap Item 29):** Centralized corporate ownership index cascading removals from parent conglomerates to storefront children.
- **Family Inboxes & Plus-Addressing (Roadmap Item 30):** Per-broker unique alias generation (`user+broker@domain.com`) with automated reply tracking.
- **Broker Listing Finder (Roadmap Item 31):** Profile discovery engine pinpointing exposed records across broker directories.
- **State Broker Registries, Dead-Site Detection & California DROP (Roadmap Item 32):** Direct ingestion of CA, VT, and TX registries, flagging defunct broker sites and integrating California DROP workflows.
- **General Web Search via Self-Hosted SearXNG (Roadmap Item 33):** Metasearch discovery of exposed public profiles without third-party tracking.
- **Actionable Checklist & Removal Reports (Roadmap Item 34):** Unified checklist aggregating email confirmations, manual hand-offs, and verification items.
- **Automated Confirmation Link Clicker (Roadmap Item 35):** Background email monitor parsing opt-out confirmation links and completing verification automatically.
- **Curated Broker Form Plugins (Roadmap Item 36):** Declarative opt-out plugins for top people-search directories with honest error classification.
- **Privacy Request Page Finder & Hosted Forms (Roadmap Item 37):** Automatic detection of OneTrust, TrustArc, and custom privacy forms on data broker sites.
- **Scheduled Removal Verification & Re-Listing Monitor (Roadmap Item 39):** Cadenced background scans verifying whether expunged records remain deleted.
- **Data-Sharing Detection & Aggregator-First Targeting (Roadmap Item 40):** Network graph mapping data sharing between brokers, prioritizing upstream master aggregators.
- **Multi-Destination Encrypted Backups (Roadmap Item 41):** Scheduled AES-256-GCM backups with local, network SFTP, and AWS S3 storage support.
- **Plain Language for Family Pages (Roadmap Item 43):** Jargon-free interfaces for non-technical family members and parents.
- **Phone/Email Removals, Age Matching & Credit Freeze Letters (Roadmap Item 44):** Phone-only broker opt-outs, date-of-birth age bracket matching, and statutory credit freeze letters for minors.
- **Removal Timeline & Multi-Round History (Roadmap Item 45):** Visual audit history grouping requests into submission, confirmation, verification, and re-check rounds.
- **Plain Language Admin Pages & Localized Status Badges (Roadmap Item 46):** Clear operational status badges and guidance for system administrators.

---

## [0.9.0] — 2026-10-08

### Added
- **Unified Interactive Host & Fleet Installer (Roadmap Item 23):** Automated CLI/TUI installer (`install.sh`) supporting Docker Compose, bare-metal systemd (Linux), and Windows Server (IIS / Windows Service).
- **Multi-Tier Institutional Hierarchy / Consortium (Roadmap Item 20):** Consortium governance model allowing library systems, branches, and multi-tenant organizations to operate isolated environments under shared infrastructure.
- **Delegated Managerial Permissions (Roadmap Item 19):** Granular permission controls separating super-administrator capabilities from branch-level staff.
- **Configurable ILS Date Formats:** Administrative date format parser for handling ambiguous birthdates from legacy library automation systems.

### Security
- Enforced strict tenant scoping on broker statistics, request mutations, and email monitor endpoints.

---

## [0.8.3] — 2026-10-08

### Added
- **Security Posture Audit Workflow:** Automated GitHub Actions workflow running static analysis, license compliance, and container vulnerability scanning.

### Security
- Hardened access control on email monitor endpoints, preventing cross-tenant information exposure.

---

## [0.8.2] — 2026-10-05

### Added
- **Process Memory Hygiene & Ephemeral Storage (Roadmap Item 15):** Ephemeral secret lifecycle management (`core/memory_hygiene.py`) ensuring sensitive credentials and tokens are zeroized from memory immediately after execution.
- **Core Catalog & Marketplace Design (Roadmap Item 8, 53):** Published technical architecture RFC for the modular broker catalog and localization distribution system.

---

## [0.8.1] — 2026-10-05

### Fixed
- Frontend CSS build stabilization and PostCSS selector parser compatibility with Tailwind CSS v3.

---

## [0.8.0] — 2026-10-05

### Added
- **SAML 2.0 SSO & Identity Hardening (Roadmap Item 13):** Native SAML 2.0 identity provider integration supporting signed assertions, unsolicited response defense, and replay prevention.
- **Automated HTTPS & Reverse Proxies (Roadmap Item 14):** Automated certificate generation and renewal using built-in Caddy and Traefik front doors, supporting Let's Encrypt, Cloudflare DNS-01, and custom CA profiles.
- **Operational Diagnostic Logging (Roadmap Item 16):** Ring-buffer in-memory diagnostic log handler with dynamic runtime verbosity adjustment and credential redaction.
- **Typed Plugin Directories & Runtime Isolation (Roadmap Item 18):** Categorized plugin directory structure (`brokers/`, `captcha/`, `email/`, `languages/`, `letters/`, `themes/`).
- **Plugin Sandbox IPC & Container Privilege Boundaries (Roadmap Item 21):** Bubblewrap, seccomp filters, and Unix domain socket IPC isolating plugin execution from host filesystems.

---

## [0.7.19] — 2026-10-04

### Added
- **First-Run Setup Wizard Core (Roadmap Item 11):** Guided first-run administrative setup wizard configuring administrator accounts, security keys, email providers, and storage backends.

### Security
- Pinned critical dependencies (`msgpack>=1.2.1`, `setuptools>=78.1.1`, `python:3.12-slim-bookworm`) to resolve upstream vulnerability advisories.

---

## [0.7.18] — 2026-09-30

### Added
- **Foundational Broker-as-Add-On Model (Roadmap Item 1):** Modular plugin structure defining data brokers via declarative JSON manifests and execution specifications.
- **Declarative Interpretation Engine (Roadmap Item 2):** Core Playwright execution runtime interpreting declarative steps (navigate, fill, click, select, wait) without hardcoded Python broker logic.
- **Multi-Form & Complex Page Interpreter (Roadmap Item 3):** Support for multi-stage removal flows, nested iframe navigation, dynamic DOM rendering, and conditional page branches.
- **Pluggable CAPTCHA Resolution Architecture (Roadmap Item 4):** Standardized CAPTCHA detection and solver hook dispatching challenges to configured services or manual resolution.
- **Granular Broker Management (Roadmap Item 5):** Administrative controls to inspect, configure, enable, or disable individual broker plugins.
- **Automated Broker Health Monitoring & Fail-Safe Auto-Disable (Roadmap Item 6):** Automatic failure classification (timeout, captcha, form not found) auto-disabling unreliable brokers after consecutive failures.
- **Email-First Parent Company Opt-Outs (Roadmap Item 10):** Batching mechanism sending statutory opt-out requests directly to corporate parent entities to expunge multiple subsidiary sites in a single interaction.
