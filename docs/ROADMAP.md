# PrivacyShield — Architectural Roadmap

Status: **Active development.** This document outlines the architectural roadmap for PrivacyShield. The platform centers on a modular **interpretation engine that executes broker add-ons**, decoupling the core orchestration from individual broker opt-out implementations.

The guiding architectural principle: **the core does not contain broker-specific logic.** The core engine interprets declarative specifications detailing how a broker's opt-out functions (web forms, emails, required language/templates, multi-step flows) and executes them. Brokers are packaged as declarative specifications and optional isolated code extensions maintained independently.

---

## Architectural Vision

Each data broker is modeled as an installable add-on describing its opt-out flow — page selectors, input fields, email requirements, locale specifications, and CAPTCHA or multi-step handling. The core platform provides:
1. **Interpretation Engine:** Executes declarative opt-out descriptions and orchestrates browser automation.
2. **Pluggable Challenge Layer:** Detects CAPTCHAs and routes challenges to configured solvers or human operators.
3. **Automated Health Monitoring:** Continuously tracks broker success rates and auto-disables broken flows to preserve system resources.
4. **Decoupled Distribution:** Modular packaging (Git repository advancing to a curated directory) enabling independent updates of broker specifications.

---

## Status at a Glance

| # | Item | Status |
|---|------|--------|
| 1 | Broker-as-add-on model | Complete |
| 2 | Declarative interpretation engine | Complete — operational in live path; legacy engine maintained as fallback |
| 3 | Multi-form & complex page interpreter | Complete |
| 4 | Pluggable CAPTCHA resolution | Complete |
| 5 | Granular broker management | Complete |
| 6 | Automated broker health monitoring | Complete |
| 7 | Distributed execution: control plane & worker fleet | Phased plan established (5 migration phases) |
| 8 | Add-on distribution: Git repo to marketplace | Planned |
| 9 | Infrastructure capacity planner | Planned — pending empirical performance benchmarking |
| 10 | Email-first opt-outs via parent companies | Complete |
| 11 | First-run setup wizard | Complete |
| 12 | School district authentication (Parent Portal SSO) | On-Demand (District Request Only) |
| 13 | SAML 2.0 SSO & identity hardening | Complete |
| 14 | Built-in HTTPS with automated certificates | Complete |
| 15 | Process memory hygiene & credential lifecycle | Complete |
| 16 | Operational visibility & diagnostic logging | Complete |
| 17 | Internationalization (i18n): language packs & RTL | Complete |
| 18 | Typed plugin directories & runtime isolation | Complete |
| 19 | Delegated managerial permissions | Complete |
| 20 | Multi-tier institutional hierarchy (Consortium) | Complete |
| 21 | Plugin sandbox IPC & resource limits | Complete |
| 22 | Independent security audit & penetration testing | Planned |

---

## Work Items

### 1. Broker-as-add-on model
**Goal:** Decouple broker-specific logic from the core platform by packaging each data broker as an independent add-on.

**Architecture:**
- **Add-on Packaging & Layout:** Standardized under `<plugins_root>/brokers/<plugin_id>/` featuring `manifest.json` (`type: "brokers"`), declarative `spec.json` (adhering to `BrokerSpec`), and optional assets/hooks.
- **Specification Scope:** Defines opt-out method (`form`, `email`, `manual`), field mappings, selector actions, success assertions, email templates, and preferred CAPTCHA solver bindings (`captcha_plugin_id`).
- **Validation & Safe Execution:** Preflight validation (`plugins/broker_addon.py`) verifies declarative syntax and prevents directory traversal. Pure declarative broker add-ons require 0 permissions, zero code execution, and default to no subprocess launch, ensuring maximum safety.
- **Catalog Synchronization:** Uploading or installing a broker add-on synchronizes directly with the core `Broker` model (`Broker.plugin_id`), and disabling or uninstalling deactivates the associated broker.
- **Opt-Out Engine Integration:** `optout_engine.py` checks for installed broker add-ons before falling back to legacy broker scripts.

**Status:** Complete.

---

### 2. Declarative interpretation engine
**Goal:** Provide a centralized runtime in the core engine that parses and executes declarative broker specifications without hardcoded broker logic.

**Architecture:**
- **Engine Capabilities:** Automated form submission via Playwright, templated email generation, and multi-step flow execution.
- **Execution Pipeline:** `DryRunExecutor` for validation/simulation and `PlaywrightExecutor` for live interaction. `script_bridge` dynamically compiles existing `BrokerScript` definitions into executable `BrokerSpec` instances.
- **Migration Strategy:** The declarative engine and the legacy combination-matrix engine (`_fill_one_combo`) coexist during the migration phase. The objective is full retirement of the legacy engine once all brokers are represented via declarative specs.

**Status:** Complete. Wired into the live execution path (`execute_optout`); legacy engine retained as migration fallback. See [`docs/INTERPRETER.md`](INTERPRETER.md).

---

### 3. Multi-form & complex page interpreter (add-on hook)
**Goal:** Support complex, multi-page, or dynamic broker flows via declarative step extensions and specialized plugin handlers rather than expanding hardcoded engine logic.

**Architecture:**
- **Declarative Complex Page Primitives:** Extended `BrokerSpec` step vocabulary (`click_matching`, `press`, `frame`, `scroll`) allowing declarative specs to traverse multi-page search results, keyboard submissions, scroll-driven loading, and embedded iframes without writing Python code.
- **Dynamic Iframe Context Switching:** `PlaywrightExecutor` manages frame targeting (`frame` step), automatically switching interaction context into embedded `iframe` forms and resetting back to the main document context.
- **Rich Page Context Delegation:** The host inspects the browser state and injects comprehensive metadata (`current_url`, `page_title`, `has_iframes`, `stage_index`, and DOM HTML) into the `fill_form` hook payload, allowing plugins to determine exactly which step of a multi-page wizard is active.
- **Multi-Stage Iterative Takeover:** `PlaywrightExecutor` supports chained multi-stage takeover loops (`next_stage: True`), allowing form plugins to handle progressive wizard workflows (e.g. Stage 0: Search Directory → Stage 1: Select Profile → Stage 2: Submit Opt-Out Form) while all browser automation and network access remain strictly isolated in the host.
- **Reference Multi-Step Implementation:** Reference plugin (`examples/plugins/forms/example-multistep-filler/`) demonstrating progressive multi-stage broker interaction, record matching, and iframe submission.

**Status:** Complete.

---

### 4. Pluggable CAPTCHA resolution architecture
**Goal:** Provide an extensible challenge-resolution framework allowing deployments to configure automated solvers or human-in-the-loop fallbacks based on policy and requirements.

**Architecture:**
- **Core Neutrality:** The core engine detects challenges, pauses execution, and delegates challenge resolution via the `solve_captcha` plugin hook.
- **Challenge Contract:** Passes challenge metadata (type, site-key, target URL, and screenshot) to registered solver plugins.
- **Broker-Preferred Solver Binding:** Each broker can specify an optional preferred CAPTCHA solver (`Broker.captcha_plugin_id`), which the plugin manager queries first before falling back to general solvers or the human path. Configurable via API and the broker management table.
- **Human-in-the-Loop Fallback:** Operator notification and manual verification queue (`CaptchaChallenge` model and `/api/captcha` endpoints) for deployments operating without automated solving services.
- **Operator Dashboard & Verification Seam:** Dedicated queue interface (`frontend/src/pages/CaptchaQueue.jsx`) with challenge screenshots, direct broker form links, token submission, and one-click manual completion verification.
- **Scheduler & Health Integration:** Paused challenges hold associated removal requests without consuming daily scheduler quotas or prematurely tripping broker auto-disable health thresholds.
- **Security Boundary:** Challenge solvers adhere to strict network egress controls and access-token policies.
- **Scope & Limitations:** Exposing integration seams makes solver add-ons possible, but does not solve CAPTCHAs without an active solver plugin or manual operator intervention.

**Status:** Complete.

---

### 5. Granular broker management
**Goal:** Allow administrators to toggle individual brokers on or off to conserve resources and tailor coverage.

**Architecture:**
- Backed by `Broker.enabled` in the database model.
- Disabled brokers are bypassed by scheduled batch jobs and the manual runner.

**Status:** Complete.

---

### 6. Automated broker health monitoring & fail-safe auto-disable
**Goal:** Automatically detect failing brokers, classify errors, and disable non-functional integrations to preserve batch execution reliability.

**Architecture:**
- Implemented in `core/broker_health.py` and `BrokerHealth` data models.
- Classifies failures into timeouts, selector mismatches, CAPTCHA walls, and network errors.
- Automatic threshold-based disabling after repeated consecutive failures; successful runs reset the failure counter.
- Flags problematic brokers with `needs_review` in the administration panel.

**Status:** Complete.

---

### 7. Distributed execution: control plane & worker fleet
**Goal:** Horizontally scale automated browser operations by separating the administrative API/control plane from stateless headless browser execution workers.

**Target Architecture:**
- **Control Plane:** Web interface, REST API, database orchestration, scheduling producer, and health monitoring.
- **Worker Fleet:** Stateless worker nodes executing Playwright browser automations and SMTP transmissions from a centralized task queue.
- **Task Queue:** Distributed job queue (Redis-backed in production, zero-dependency in-process fallback for standalone installs) replacing in-process monolithic scheduling.
- **Chunked Batching:** Workload chunking with per-broker rate limiting, concurrency caps, and fault isolation.

**Architectural Implications:**
- **Database:** Requires PostgreSQL for multi-node deployments (SQLite remains supported for single-node installations).
- **Security & Sandboxing:** Worker nodes host the Bubblewrap execution sandbox; credentials and PII transfers across worker boundaries must be strictly scoped, serialized into encrypted job envelopes, and never expose direct database ORM handles.
- **Proxy Management:** Coordinated proxy pools across distributed workers to prevent rate-limit collisions.

**Capacity Planning Model:**
Worker capacity is determined by form-automation concurrency and browser memory overhead rather than simple patron counts:
```
operations_per_cycle = active_profiles × avg_enabled_brokers_per_profile
worker_throughput    = concurrent_slots_per_worker × (3600 / avg_seconds_per_form_optout)
workers_needed       = operations_per_cycle ÷ (worker_throughput × hours_in_completion_window)
```

**Multi-Phase Migration Strategy (Sequential Sessions):**

To ensure operational stability and maintain continuous testability without disrupting standalone single-node installations, Item 7 is structured into five progressive, independently verifiable phases:

* **Phase 7.1 — Job Envelope & Secure Payload Serialization (Data Boundary):**
  - Define `JobEnvelope` schema encapsulating compiled `Job`, job ID, broker metadata, HMAC signature, and encrypted patron payload.
  - Define `JobResultEnvelope` schema encapsulating `ExecResult`, execution trace, screenshots, challenge metadata, and timing.
  - Decouple execution from ORM entities: workers operate exclusively on serialized envelopes without direct database connection requirements.
  - *Verification:* Pure Python unit tests validating round-trip envelope serialization, tampering rejection, and cryptographic zeroization.

* **Phase 7.2 — Unified Queue Abstraction & Pluggable Backends (Transport Boundary):**
  - Implement abstract `JobQueue` interface (`enqueue`, `dequeue`, `acknowledge`, `requeue`, `publish_result`).
  - Implement `InProcessJobQueue`: thread-safe in-memory queue preserving zero-dependency single-container operations (default).
  - Implement `RedisJobQueue`: distributed queue backend supporting priority channels (`high`, `normal`, `retry`) and dead-letter queues.
  - *Verification:* Test suite runs against `InProcessJobQueue` by default, with optional Redis integration tests when configured.

* **Phase 7.3 — Stateless Worker Node Daemon (Execution Boundary):**
  - Implement standalone worker daemon (`backend/worker.py`) that boots independently of the FastAPI web application.
  - Worker lifecycle: pulls envelopes from `JobQueue`, initializes sandboxed Playwright/Bubblewrap contexts, executes via `PlaywrightExecutor`, and emits `JobResultEnvelope`.
  - Process supervisor integration with concurrency slots (`WORKER_CONCURRENCY=N`) and graceful SIGTERM draining.
  - *Verification:* Worker unit tests driving mock headless jobs and verifying result publishing without touching the control plane.

* **Phase 7.4 — Control Plane Ingestion & Dynamic Scheduling (Orchestration Boundary):**
  - Transition `core/scheduler.py` from an in-process executor to an enqueuing producer (`enqueue_pending_optouts`).
  - Implement asynchronous result ingestion service on the control plane: updates `RemovalRequest` statuses, triggers parent company cascade confirmations, logs broker health metrics, and routes CAPTCHA challenges to the operator queue.
  - Lease management & orphan reclamation: automated detection and requeuing of jobs from crashed or unresponsive workers.
  - *Verification:* End-to-end integration test validating scheduler produce → queue → worker execute → control plane ingest.

* **Phase 7.5 — Fleet Monitoring, Admin Telemetry & Orchestration (Operations Boundary):**
  - Worker heartbeat registry (`worker_id`, host, active slots, vCPU/RAM telemetry, uptime).
  - Administrative fleet management dashboard (`frontend/src/pages/WorkerFleet.jsx` and `routers/workers.py` gated by `settings.system`) displaying active nodes, queue depths, and throughput.
  - Distributed Docker Compose topology (`docker-compose.distributed.yml`) featuring scaled worker services (`--scale worker=4`).
  - *Verification:* Smoke test running multi-container distributed opt-out runs under Docker Compose.

**Status:** In Progress (Phased Migration Plan Established).

---

### 8. Add-on distribution: Git repository to curated marketplace
**Goal:** Establish a modular distribution channel for community broker specs, solver plugins, and language packs.

**Phases:**
- **Phase 1 (Git-Backed Catalog):** Structured Git repository allowing automated installation and dependency resolution.
- **Phase 2 (Curated Marketplace):** Web directory providing discovery, ratings, version tracking, and cryptographic signature verification.

**Security Architecture:**
- Cryptographic code signing and manifest provenance checks.
- Sandboxed execution, permission gating, and static code inspection before plugin activation.

**Status:** Planned.

---

### 9. Infrastructure capacity planner
**Goal:** Provide an administrative sizing calculator that estimates hardware and worker node requirements based on profile volume and broker distribution.

**Architecture:**
- **Input Parameters:** Available vCPU/RAM, active profiles, and broker selection breakdown (email vs. headless form vs. CAPTCHA-gated).
- **Cost Weighting:** Differentiates lightweight email transmissions from memory-intensive Playwright browser sessions.
- **Telemetry Integration:** Calibrates planning coefficients using empirical execution metrics from real worker runs.

**Status:** Planned (pending empirical performance benchmarking under Item 7).

---

## Cross-Cutting Concerns

- **Security & Trust Boundaries:** Untrusted third-party code or community specifications must execute within strict sandbox boundaries (Bubblewrap, seccomp filters, restricted namespaces) and adhere to granular permission controls (`read_pii`, network egress).
- **Testing & Verification:** End-to-end integration tests must continuously validate sandboxed process execution, IPC socket connectivity, credential isolation, and memory caps across supported environments.
- **Single-Node vs. Distributed Scaling:** Core services are designed with clean execution boundaries (`produce_job` / `execute_job`) so single-container deployments can scale to multi-worker fleets backed by PostgreSQL without architectural refactoring.
- **Maintenance Model & Ecosystem Drift:** Decoupling broker logic into add-ons isolates site changes from core platform releases, supported by health tracking and auto-disable safety mechanisms.

---

## Suggested Implementation Sequence

1. **Broker health reporting & auto-disable (Item 6):** Complete.
2. **Sandbox runtime validation (Item 18, 21):** Complete.
3. **Declarative engine & broker specifications (Items 1, 2):** Core engine live; complete transition of legacy scripts in progress.
4. **Complex page interpreter & CAPTCHA framework (Items 3, 4):** Complete. Multi-form wizard support and solver seams verified.
5. **Distributed job execution boundary (Item 7):** Phased migration active (Phase 7.1 Data Boundary → Phase 7.2 Transport → Phase 7.3 Worker Daemon → Phase 7.4 Ingestion → Phase 7.5 Fleet Monitoring).
6. **Add-on distribution & package management (Item 8):** Phased rollout starting with Git repositories and advancing to signed catalog distribution.

---

### 10. Email-first opt-outs via parent companies
**Goal:** Prioritize high-efficiency email-based opt-outs to corporate entities controlling multiple broker storefronts, bypassing form friction and clearing multiple sites simultaneously.

**Architecture:**
- **Parent Company Data Model:** Child broker aggregation under `ParentCompany` and `Broker.parent_company_id`.
- **Automated Batching & Dispatch:** Scheduler fires consolidated opt-out emails for members with pending removal requests across child brokers, assigning a shared UUID tracking key and transitioning child requests to `sent`.
- **Template Tracking & URL Citations:** Standardized legal correspondence (`core/optout_email_template.py`) embeds the shared tracking key in subject and body (`Reference ID`), citing verified profile URLs across all subsidiary properties.
- **Multi-Request Reply Resolution:** IMAP monitor (`core/scheduler.py`) matches inbound confirmation replies using the shared tracking UUID, simultaneously confirming all child requests and updating the parent's `emails_confirmed` and `honor_status`.
- **Administrative UI & Manual Controls:** Dedicated parent company dashboard (`frontend/src/pages/ParentCompanies.jsx` and `routers/parent_companies.py`) providing manual dispatch triggers (`/dispatch` and `/dispatch-all`), child broker mapping, and reputation metrics.

**Status:** Complete.

---

### 11. First-run setup wizard
**Goal:** Provide a guided onboarding workflow for initial deployment configuration (database selection, email transports, institutional branding, and HTTPS provisioning).

**Architecture:**
- **Guided Setup Flow:** Implemented in `routers/wizard.py` covering database, email, branding, and deployment verification.
- **Transport Flexibility:**
  - **OAuth 2.0:** Recommended for Google Workspace and Microsoft 365. Utilizes scoped, expiring access tokens without storing mailbox passwords.
  - **IMAP / SMTP:** Supported for self-hosted mail servers, legacy providers, and app-specific password configurations (e.g., Apple iCloud Mail).
  - **Local Relays & Bridges:** Generic SMTP interface compatible with Proton Mail Bridge, Postfix, or enterprise outbound relays.
- **Email Mode Architecture:** Supports shared administrative inboxes and per-user mail authorization.
- **Mode Switching Grace Period:** Background monitoring (`core/email_grace.py`, `core/scheduler.py`, `routers/settings.py`) snapshots previous mailbox credentials during mode or account switches, maintaining automatic 60-day dual-inbox polling to capture delayed broker confirmations, with admin controls to extend or dismiss.

**Status:** Complete.

---

### 12. School district authentication (Parent Portal SSO)
**Goal:** Enable authentication for parents and district staff by federating with Student Information Systems (SIS) and district identity platforms when requested by an institutional partner.

**Scope & Governance:**
- **On-Demand Prioritization:** School district and parent portal integrations (ClassLink, Clever, PowerSchool, Infinite Campus) are maintained as an on-demand institutional feature, implemented only when formally requested by a district or school system. It is decoupled from the 1.0.0 core milestone.
- **Student Privacy & Regulatory Boundaries:** While K-12 students are protected by CIPA (Children's Internet Protection Act), COPPA, and FERPA against school data disclosure, older high school students (ages 16–18) frequently appear on commercial consumer data brokers once they obtain driver's licenses, register to vote, or register for standardized tests. Privacy Shield's standard individual/family member profiles protect these students immediately through regular opt-out flows without requiring deep SIS synchronization.

**Architecture (When Activated):**
- **Federated Protocols:** Leverages existing SAML 2.0 (`core/saml_sp.py`) and OIDC integrations (ClassLink, Clever, PowerSchool, Infinite Campus, Microsoft Entra, Google Workspace).
- **Role Mapping:** Maps portal accounts to the `parent` role and faculty accounts to appropriate administrative roles.
- **FERPA Compliance & Privacy Protection:** Strict adherence to minimal identity claims (name, email, unique identifier). System never queries or ingests student educational records; parents register family members independently.

**Status:** On-Demand (District Request Only).

---

### 13. SAML 2.0 SSO & identity hardening
**Goal:** Support SAML 2.0 identity federation for enterprise and academic deployments alongside OIDC, LDAP, and SIP2, reinforced with unified authentication hardening.

**Architecture:**
- **SAML 2.0 Service Provider:** Implemented via `pysaml2` and `xmlsec1` (`core/saml_sp.py`, `routers/saml.py`) supporting SP metadata, IdP configuration, signed assertions, and replay protection.
- **Unified Sign-In Policy:** Centralized in `core/sso_policy.py` across all external identity providers (OIDC, LDAP, SIP2, SAML) enforcing registration controls, domain allowlists, and privilege limits.
- **Directory Security (LDAP/LDAPS):** Strict certificate and hostname verification, StartTLS enforcement, unauthenticated bind protections, and custom CA trust anchors.
- **Library Protocol Security (SIP2):** Mandatory TLS verification, protection against delimiter and field injection in barcode/PIN fields, and robust response validation.
- **Certificate Lifecycle Monitoring:** Daily monitoring of SAML IdP signing certificates, LDAP/LDAPS certificates, and SIP2-over-TLS endpoints with staged expiration alerts.

**Status:** Complete. Documented in [`docs/SSO.md`](SSO.md).

---

### 14. Built-in HTTPS with automated certificates
**Goal:** Automate TLS certificate provisioning and renewal across containerized and bare-metal installations to secure patron data in transit.

**Architecture:**
- **Container Deployments (Docker):** Managed Caddy reverse proxy (`deploy/caddy/`) providing automated ACME issuance via Let's Encrypt, staging environments, internal CAs, or custom certificate mounts. Activated via compose profile (`COMPOSE_PROFILES=https`) and helper scripts (`scripts/enable-https.sh`, `scripts/enable-https.ps1`).
- **Bare-Metal Linux (Debian/Ubuntu):** Automated host installation script (`deploy/native/install.sh`) setting up systemd services, venv dependencies, and nginx reverse proxy with automated Certbot integration (`scripts/enable-https-native.sh`).
- **Windows Server Deployments:** Native service management via NSSM with IIS reverse proxy and win-acme integration. Documented in [`docs/NATIVE_INSTALL.md`](NATIVE_INSTALL.md).
- **Automated Health Probes:** `GET /api/cert-monitor/https-status` endpoint provides real-time verification of active TLS certificates without requiring host system privileges.

**Status:** Complete. Documented in [`docs/HTTPS.md`](HTTPS.md).

---

### 15. Process memory hygiene & credential lifecycle
**Goal:** Ensure decrypted credentials (database keys, OAuth tokens, passwords) and sensitive patron PII are retained in process memory for the minimum duration necessary.

**Technical Strategy:**
- **Language Scope:** Acknowledging Python string immutability and memory allocation behavior, memory hygiene represents disciplined risk reduction (limiting scope, minimizing retention windows, clearing references promptly) rather than a hardware-level zeroization guarantee.
- **Credential Scoping & Memory Zeroization:** `core/memory_hygiene.py` provides `SecureBuffer`, `ephemeral_secret`, and `scoped_credentials` context managers. Secrets are decrypted directly into mutable byte buffers, yielded strictly for the execution of connection blocks (SMTP, IMAP, tests), and overwritten with zeros on block exit or exception.
- **Log Sanitization:** Enforces strict review checklists and automated masking ensuring credentials and PII are never interpolated into log statements or exception tracebacks (Item 16).
- **Batch Processing Streaming:** Streams patron records (`stream_records` with `yield_per`) during bulk processing to ensure sensitive data goes out of scope promptly rather than accumulating in full-table in-memory collections.

**Status:** Complete.

---

### 16. Operational visibility & diagnostic logging
**Goal:** Provide administrators with centralized visibility into running application versions and diagnostic logs directly from the administrative interface.

**Technical Architecture:**
- **Part A — Version & Commit Reporting:** Canonical version (`backend/VERSION`) and short git commit hash (`GIT_COMMIT`) logged at API startup and exposed via `GET /api/health` for automated probes and bug reporting.
- **Part B — Persistent Rotating Logs & In-App Viewer:** Dual-layer logging architecture combining persistent disk rotation (`/data/logs/privacyshield.log`, 10MB rotations, 5 backups) with an in-memory ring buffer (2,000 records) for low-latency searching, filtering, and live UI streaming. Supported by automatic PII and credential sanitization (Bearer tokens, SIP2 credentials, query secrets, and JSON passwords) before emission. Full diagnostic log export available via `GET /api/logs/download`.
- **Part C — Dynamic Log Verbosity & Permissions:** Runtime configurable log levels (DEBUG, INFO, WARNING, ERROR) managed via `POST /api/logs/level` without requiring container restarts. Delegated access control with dedicated sensitive permissions (`logs.view` and `logs.manage`) allowing super admins to securely grant staff access to diagnostic tools.

**Status:** Complete. Documented in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).

---

### 17. Internationalization (i18n): language packs & RTL
**Goal:** Provide comprehensive localization support across the user interface, supporting community language packs, right-to-left (RTL) layout rendering, in-system translation management for administrators, and user onboarding guided tours.

**Architecture:**
- **Core Translation Architecture:** Master UI dictionary (`core/i18n.py`) with categorized translation keys, explicit screen locations ("where it appears"), and translator guidelines. Hierarchical resolution order: master English defaults → built-in translations (English, Spanish, Arabic, French) → installed language pack plugins (`<plugins_root>/languages/<id>/`) → administrator custom string replacements.
- **In-System Translation & Replacement Interface:** Administrative UI (`pages/Translations.jsx` gated with `settings.manage`) enabling super admins and managers to search and filter strings by UI location, view English source text, customize wording or replace terminology, toggle active languages, and register new custom locales.
- **Right-to-Left (RTL) Support:** Dynamic layout mirroring (`html[dir="rtl"]` in `index.css`) detecting RTL scripts (Arabic, Hebrew, Persian, Urdu), mirroring navigation sidebars, form layouts, and modals while preserving left-to-right (`ltr`) direction for email addresses, URLs, phone numbers, and code blocks.
- **Onboarding Tutorial & User Preferences:** Guided 4-step welcome walkthrough (`components/UserWelcomeModal.jsx`) allowing users to choose their language with instant UI preview, populate their Identity Vault PII for automated opt-outs, review email communications, and complete an orientation tour. User language preference and tutorial completion persist in user profile settings (`preferred_language`, `tutorial_completed`).
- **Data-Only Language Packs:** Scanned and loaded from `<plugins_root>/languages/` as data-only bundles (`manifest.json` + `messages.json`) requiring 0 permissions and zero subprocess overhead.

**Status:** Complete.

---

### 18. Typed plugin directories & runtime isolation
**Goal:** Organize extensions by functional category under a structured `plugins/` hierarchy, enforcing type-specific capabilities, permissions, and sandbox constraints.

**Directory Structure:**
```
plugins/
├── brokers/      # Broker opt-out specifications and optional code
├── captcha/      # CAPTCHA challenge solvers
├── forms/        # Custom multi-form page handlers
├── discovery/    # Patron listing discovery modules
├── email/        # Email transport and OAuth providers
├── themes/       # UI appearance configurations (data-only)
├── languages/    # Interface language packs (data-only)
└── general/      # Event listeners and notification hooks
```

**Security Controls:**
- **Type Enforced Boundaries:** Data-only plugins (`languages`, `themes`) cannot declare code entrypoints or execute background processes.
- **Static Code Inspection:** Automated validation (`plugins/code_inspector.py`) inspects code plugins at install time, prohibiting unauthorized file system access, dynamic code evaluation, native compilation, and unpermitted network egress.
- **Read-Only Sandbox:** Under Bubblewrap, the plugin code directory is mounted read-only with ephemeral private storage allocated in `/tmp`.
- **Runtime Integrity Verification:** SHA-256 integrity hashes are validated on launch; modified plugin files are flagged and blocked from execution.
- **Strict Path Containment:** Prevents directory traversal attacks during upload, extraction, and uninstallation.

**Status:** Complete. Documented in [`backend/plugins/docs/USING_PLUGINS.md`](../backend/plugins/docs/USING_PLUGINS.md).

---

### 19. Delegated managerial permissions
**Goal:** Provide a tiered `manager` role between super administrators and patrons, allowing granular delegation of administrative responsibilities.

**Architecture:**
- **Role Hierarchy:** `super_admin`, `manager`, `parent`, `member`.
- **Permission Matrix:** 17 discrete permissions spanning user management, member data access, broker configuration, system operations, and plugin management (`core/access.py`).
- **Least-Privilege Defaults:** Member PII access is disabled by default for managers. Super administrators retain exclusive authority over role assignments, system configuration, database migrations, and master reset operations.
- **Privilege Escalation Guards:** Managers cannot grant permissions beyond their own scope, modify super admin accounts, or generate administrative invitation tokens.

**Status:** Complete.

---

### 20. Multi-tier institutional hierarchy (Consortium)
**Goal:** Support statewide or consortium-level deployments by partitioning patron management and data visibility across independent library systems and branch locations.

**Technical Architecture:**
- **Organizational Hierarchy & Data Model:** Consortium (global instance) → Library Systems (`LibrarySystem`) → Branch Locations (`Branch`). Patrons (`User`) belong to a branch with attribution metadata (`branch_source`, `branch_override_by`, `branch_override_at`).
- **Dynamic SIP2 ILS Routing & Location Code Mapping:** Routes authentication requests across multiple `SIP2Connection`s prioritized by patron barcode prefix. Dynamically extracts home branch locations from patron responses using configurable ILS field codes (e.g., `AQ`, `AF`), matching against branch codes and aliases.
- **Strict Isolation & Delegated Scoping:** Centralized access queries in `backend/core/auth.py` strictly isolate non-super-admin managers to patrons within their explicitly assigned `ManagerScope`s (consortium, system, or branch level). Unscoped managers default to self and explicitly shared profile visibility. Cross-system visibility requires the sensitive `consortium.cross_system` permission.
- **Per-System Branding:** Library systems can customize portal branding (display name, logo, theme colors), governed by super-admin toggle controls.
- **Management API:** Comprehensive administration router (`backend/routers/consortium.py`) for managing systems, branches, multi-tenant SIP2 connections, manager scopes, unassigned patron queues, and staff branch overrides.

**Status:** Complete.

---

### 21. Plugin sandbox IPC & resource limits
**Goal:** Guarantee resilient, isolated inter-process communication between the host application and sandboxed plugins without resource starvation.

**Technical Architecture:**
- **Network Namespace IPC:** HostService and plugins communicate over dedicated Unix domain sockets (`host.sock` and `plugin.sock`) bind-mounted into isolated runtime directories, enabling reliable IPC even when network namespaces are disabled for the plugin.
- **Thread Stack Size Reduction:** Runner and SDK configure `threading.stack_size(512 * 1024)`, shrinking per-thread memory reservations to 512KB and preventing address space exhaustion under strict `RLIMIT_AS` memory ceilings.
- **Filesystem Containment:** Plugin working directories are pinned to their dedicated runtime directories, preventing arbitrary writes to the host filesystem.

**Status:** Complete.

---

### 22. Independent security audit & penetration testing
**Goal:** Engage a third-party security firm or independent security researchers to perform a comprehensive code audit and penetration test across PrivacyShield's security-critical subsystems.

**Audit Scope:**
- **OS-Level Sandboxing:** Bubblewrap containerization, seccomp-bpf syscall filters, private network namespaces, Unix domain socket bind-mounts, and capability dropping in `backend/plugins/sandbox.py`.
- **Inter-Process Communication & Broker:** gRPC HostService capability broker, runtime token validation, permission check enforcement, and unprivileged execution limits.
- **Cryptographic Protections:** SQLCipher AES-256-CBC full-database encryption, Fernet field-level PII encryption, key derivation, and ephemeral credential lifecycle.
- **Authentication & Federation:** SAML 2.0 assertion validation, SIP2-over-TLS parser resilience against malformed packets, LDAPS/StartTLS certificate validation, OAuth 2.0 token management, and FastAPI session cookie controls.
- **API & Web Vulnerabilities:** FastAPI input sanitization, CSRF protections, CORS configuration, role-based access control (Admin, Manager, Staff, Patron), and safe zip handling during plugin installation.

**Deliverables:**
- Publicly accessible security audit summary and threat model validation.
- Remediation of all critical and high-severity findings prior to v1.0 enterprise/consortium readiness.
- Clear disclosure and bug bounty / coordinated vulnerability reporting policy.

**Status:** Planned.

---

## Explicitly Deferred / Open Questions

- Formal declarative-vs-code boundary definition for edge-case broker add-ons (Item 1).
- Add-on cryptographic signing and provenance model for automated marketplace installations (Item 8).
- Selection of distributed queue architecture (Redis/RQ vs. Celery) and secure cross-worker PII serialization (Item 7).
- Operational scalability and ethical policies regarding third-party CAPTCHA-solving services (Item 4).
- Prioritization of Student Information System (SIS) vendor integrations for school district deployments (Item 12).
- Community review and governance model for community-contributed language packs (Item 17).
- Theme customization boundary: token-level styling vs. structural layout modifications (Item 18).
