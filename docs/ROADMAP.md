# OpenOptOut — Architectural Roadmap

Status: **Active development.** This document outlines the architectural roadmap for OpenOptOut. The platform centers on a modular **interpretation engine that executes broker add-ons**, decoupling the core orchestration from individual broker opt-out implementations.

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
| 2 | Declarative interpretation engine | Complete |
| 3 | Multi-form & complex page interpreter | Complete |
| 4 | Pluggable CAPTCHA resolution | Complete |
| 5 | Granular broker management | Complete |
| 6 | Automated broker health monitoring | Complete |
| 7 | Distributed execution: control plane & worker fleet | Complete |
| 8 | Add-on distribution: Git repo to marketplace | In Design / Active (Phase 8.1 In Design) |
| 9 | Infrastructure capacity planner | Planned — pending empirical performance benchmarking |
| 10 | Email-first opt-outs via parent companies | Complete |
| 11 | First-run setup wizard | Complete (Enhanced 7-step flow & bundle planned) |
| 12 | School district authentication (Parent Portal SSO) | On-Demand (District Request Only) |
| 13 | SAML 2.0 SSO & identity hardening | Complete |
| 14 | Built-in HTTPS with automated certificates | Complete |
| 15 | Process memory hygiene & ephemeral storage | In Testing (15.1 Complete, 15.2 In Testing) |
| 16 | Operational visibility & diagnostic logging | Complete |
| 17 | Internationalization (i18n): language packs & RTL | Complete (Plugin localization standard in design) |
| 18 | Typed plugin directories & runtime isolation | Complete |
| 19 | Delegated managerial permissions | Complete |
| 20 | Multi-tier institutional hierarchy (Consortium) | Complete |
| 21 | Plugin sandbox IPC & container privilege boundaries | In Testing (21.1 Complete, 21.2 In Testing) |
| 22 | Independent security audit & penetration testing | Planned |
| 23 | Unified interactive host & fleet installer (CLI/TUI) | Complete |
| 24 | Enterprise ingress, edge security & DDoS protection | Complete |
| 25 | Passwordless authentication & session lifespan governance | Complete |
| 26 | Automated ILS demographic ingestion & Identity Vault sync | Complete |
| 27 | Universal accessibility (a11y) & WCAG 2.2 AAA conformance | Complete |
| 28 | Multi-container test matrix, mock harness & diagnostic automation | Complete |
| 29 | Parent-company catalog & broker spec metadata | Complete (#67) |
| 30 | Family inboxes & one address per opt-out | Complete (#69) |
| 31 | Find your listings (listing finder) | Complete (#70) |
| 32 | State broker registries, dead-site detection & California DROP | Complete (#71) |
| 33 | General web search (SearXNG) | Complete (#72) |
| 34 | Checklist & per-variant removal report | Complete (#73, #75) |
| 35 | Broker confirmation links clicked automatically | Complete (#76) |
| 36 | Curated broker form plugins & honest form results | Complete (#77) — live verification pending |
| 37 | Long tail: privacy-request page finder & OneTrust/TrustArc forms | Complete (#79) — live verification pending |
| 38 | Built-in receive-only inbox | Not Planned (covered by + addressing & direct fallbacks) |
| 39 | Automated removal verification & re-listing monitor | Complete (#82) — live verification pending |
| 40 | Data-sharing detection & aggregator-first targeting | Complete (#83) |
| 41 | Encrypted backups to local, network, SFTP and cloud storage | Complete (#85, #91) |
| 42 | Automatic broker steps & AI helpers | Complete (#98) — live verification pending |
| 43 | Plain language for people and family pages | Complete (#86, #87) |
| 44 | Phone and email removal, birthday matching, and credit freeze letters | Complete (#88) |
| 45 | Removal timeline & round tracking | Complete (#89) |
| 46 | Plain language for admin pages & localized status badges | Complete (#90) |
| 47 | Cloud backups through rclone (Proton Drive, Box, pCloud, MEGA, Nextcloud) | Complete (#91) |
| 48 | Privacy record, access logging, and deadline reporting | Complete (#92) |
| 49 | Decoupled language packs, privacy score, PDF reports, and calendar scheduling | Complete (#93) |
| 50 | Live CAPTCHA hand-off & privacy-preserving solvers | Complete (#94) |
| 51 | Unclear match resolution & listing disambiguation | Complete (#95) |
| 52 | Full UI translation framework across 12 languages | Complete (#96) |
| 53 | Plugin localization standard & jurisdiction-based legal letters | Complete (#97) |
| 54 | Universal live hand-off for interactive steps ("Do it here") | Complete (#99) |
| 55 | Yahoo OAuth-only email integration | Complete (#100) |
| 56 | Comprehensive RTL mirroring & logical layout | Complete (#101) |
| 57 | Configurable regional date, time, and number formats | Complete (#103) |
| 58 | Modular opt-out letter plugins | Complete (#104) |
| 59 | Monitoring, Prometheus metrics, webhooks, and log forwarding | Complete (#105) |
| 60 | Broker pack 1 (50 independent plugins) & coverage calculation | Complete (#106) |
| 61 | Terms, operational limits, and transparency notices | Complete (#107) |
| 62 | Automated discovery response for inactive brokers | Complete (#108) |
| 63 | Usage statistics API for institutional data warehouses | Complete (#110) |
| 64 | Address-verified registration for housing communities | Complete (#116) |

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
- **Execution Pipeline:** `DryRunExecutor` for validation/simulation and `PlaywrightExecutor` for live interaction. `script_bridge` dynamically compiles existing `BrokerScript` definitions into executable `BrokerSpec` instances, with `heuristic_spec_for_broker` generating declarative fallback specs for unscripted brokers.
- **Legacy Engine Retirement:** The legacy combination-matrix engine (`_fill_one_combo`) has been completely retired. All brokers—whether backed by a formal Broker Add-on, an existing `BrokerScript`, or an unscripted broker—are compiled into standardized `BrokerSpec` structures via `script_bridge.get_or_build_broker_spec()`. Automated form submissions are executed exclusively through `PlaywrightExecutor`, standardizing CAPTCHA interception, screenshot logging, bot evasion, and multi-stage plugin hooks across the entire platform.

**Status:** Complete. Single declarative execution engine unified; legacy combo engine retired. See [`docs/INTERPRETER.md`](INTERPRETER.md).

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
**Goal:** Horizontally scale automated browser operations—including both opt-out removal executions and pre-removal discovery bots—by separating the administrative API/control plane from stateless headless browser execution workers.

**Target Architecture:**
- **Control Plane:** Web interface, REST API, database orchestration, scheduling producer, and health monitoring.
- **Worker Fleet:** Stateless worker nodes executing Playwright browser automations (both **Opt-Out Removals** and **Discovery Bots**) and SMTP transmissions from a centralized task queue.
- **Unified Browser Automation Stack:** Discovery bots and removal executors run inside the *exact same headless browser environment* (Playwright Firefox with identical anti-detection fingerprinting, user agent rotation, viewport emulation, and proxy routing). This eliminates browser environment drift, shares stealth configurations, and allows pooled browser instance reuse.
- **Distributed Discovery Bots & Pre-Removal Reconnaissance:**
  - *Web & Directory Search:* Querying search engines and public directories to uncover exposed patron records across the data broker landscape.
  - *Broker Site Search & URL Scraping:* Directly querying broker search endpoints, person-lookup pages, and directory structures to identify individual patron records.
  - *Pre-Removal Prerequisite Resolution:* Many data brokers strictly refuse removals unless provided with the exact profile/listing URL, or mandate that a removal request originate from clicking an on-page "Remove Data" / "Opt Out" button on the listing page itself. Discovery bots locate, verify, and persist these record URLs and entry-point buttons so downstream removal jobs can proceed without manual operator research.
  - *Pipeline Chaining:* Discovered listing URLs and record identifiers seamlessly populate `DiscoveryResult` records and feed directly into subsequent declarative `RemovalRequest` jobs.
- **Task Queue:** Distributed job queue (Redis-backed in production, zero-dependency in-process fallback for standalone installs) supporting prioritized channels (`removal_high`, `removal_normal`, `discovery`, `retry`).
- **Chunked Batching:** Workload chunking with per-broker rate limiting, concurrency caps, and fault isolation across both discovery crawls and removal submissions.

**Architectural Implications:**
- **Database:** Requires PostgreSQL for multi-node deployments (SQLite remains supported for single-node installations).
- **Security & Sandboxing:** Worker nodes host the Bubblewrap execution sandbox; credentials and PII transfers across worker boundaries must be strictly scoped, serialized into encrypted job envelopes, and never expose direct database ORM handles.
- **Proxy Management:** Coordinated proxy pools across distributed workers to prevent rate-limit collisions during concurrent discovery queries and opt-out submissions.
- **Browser Lifecycle:** Workers share a pooled browser runtime so discovery bots and removal tasks leverage identical stealth profiles and proxy contexts without cold-start browser spawning penalties.

**Capacity Planning Model:**
Worker capacity is determined by combined discovery-query and form-automation concurrency and browser memory overhead rather than simple patron counts:
```
operations_per_cycle = active_profiles × (avg_discovery_queries + avg_enabled_brokers)
worker_throughput    = concurrent_slots_per_worker × (3600 / avg_seconds_per_operation)
workers_needed       = operations_per_cycle ÷ (worker_throughput × hours_in_completion_window)
```

**Multi-Phase Migration Strategy (Sequential Sessions):**

To ensure operational stability and maintain continuous testability without disrupting standalone single-node installations, Item 7 is structured into five progressive, independently verifiable phases:

* **Phase 7.1 — Job Envelope & Secure Payload Serialization (Data Boundary) — Complete:**
  - Implemented `JobEnvelope` schema encapsulating action type (`removal` vs. `discovery`), compiled `Job` / query criteria, job ID, broker metadata, HMAC-SHA256 signature, and authenticated encrypted payload (`backend/core/distributed/envelope.py`).
  - Implemented `JobResultEnvelope` schema encapsulating `ExecResult`, discovered listing URLs / profile IDs, execution trace, screenshots, challenge metadata, and timing.
  - Decoupled execution from ORM entities: workers operate exclusively on serialized envelopes without direct database connection requirements.
  - Built-in memory zeroization (`zeroize()` and context manager) for scrubbing sensitive patron data and screenshot buffers from process memory (Roadmap Item 15).
  - *Verification:* Pure Python unit tests in `tests/run_tests.py` validating round-trip envelope serialization, tampering rejection, expiry enforcement, authenticated encryption, and cryptographic zeroization.

* **Phase 7.2 — Unified Queue Abstraction & Pluggable Backends (Transport Boundary) — Complete:**
  - Implemented abstract `JobQueue` ABC (`enqueue`, `dequeue`, `acknowledge`, `requeue`, `dead_letter`, `publish_result`, `get_result`, `queue_depth`, `in_flight_count`, `clear`) in `backend/core/distributed/queue.py`.
  - Implemented `InProcessJobQueue`: thread-safe in-memory priority queue supporting priority channels (`removal_high`, `removal_normal`, `discovery`, `retry`), dead-letter queue, in-flight lease tracking, and results queue preserving zero-dependency single-container operations (default).
  - Implemented `RedisJobQueue`: distributed queue backend supporting priority channels (`removal_high`, `removal_normal`, `discovery`, `retry`), dead-letter queue, atomic pop/push operations, in-flight lease hash, and results queue.
  - Implemented `get_queue(url, secret_key, reset)` global provider with automatic backend selection.
  - Extended `Job`, `JobStep`, `EmailJob`, and `ExecResult` with canonical `to_dict()` and `from_dict()` serialization.
  - *Verification:* Pure Python unit tests in `tests/run_tests.py` (`t_unified_job_queue`) verifying priority channel ordering, in-flight leases, ack/requeue/DLQ routing, results channel, mock Redis client operations, and global queue factory.

* **Phase 7.3 — Stateless Worker Node Daemon (Execution Boundary) — Complete:**
  - Implemented standalone worker daemon (`backend/worker.py` and `backend/core/distributed/worker.py`) running independently of the FastAPI web application.
  - Implemented `WorkerBrowserPool` providing Playwright browser lifecycle management, randomized user-agent rotation, proxy integration, and graceful dry-run / mock fallback.
  - Unified browser runner handling both removal jobs (via `PlaywrightExecutor`/`DryRunExecutor`) and discovery queries (`execute_discovery_query`) within the same browser runtime.
  - Implemented multi-slot concurrency (`WorkerConfig.concurrency` / `WORKER_CONCURRENCY=N`).
  - Implemented graceful shutdown and task draining via `request_stop()`, SIGTERM, and SIGINT.
  - Implemented retry counter tracking with automatic dead-letter queue (DLQ) routing for exhausted retries and tampered envelopes.
  - *Verification:* Pure Python unit tests in `tests/run_tests.py` (`t_worker_daemon_execution`) verifying removal dispatch, discovery bot execution, tampering rejection, retry/DLQ routing, and multi-slot concurrent execution with graceful draining.

* **Phase 7.4 — Control Plane Ingestion & Dynamic Scheduling (Orchestration Boundary) — Complete:**
  - Transitioned `core/scheduler.py` from direct in-process execution to an enqueuing producer (`enqueue_pending_optouts`, `enqueue_pending_discoveries`), compiling jobs into signed `JobEnvelope`s across priority queues.
  - Implemented asynchronous result ingestion service on the control plane (`backend/core/distributed/ingestion.py`): drains `JobResultEnvelope`s, updates `RemovalRequest` statuses (`submitted`, `needs_manual`, `failed`, `confirmed`), stores discovered profile URLs in `DiscoveryResult`, automatically chains discovered URLs into downstream removal requests, triggers parent company cascade confirmations, logs broker health metrics, and routes CAPTCHA challenges to the operator queue.
  - Implemented lease management & orphan reclamation (`reclaim_orphaned_leases`): automated detection and requeuing of jobs from crashed or unresponsive workers to `CHANNEL_RETRY` with retry counter tracking and automatic routing to `CHANNEL_DEAD_LETTER` once retries are exhausted.
  - *Verification:* Pure Python unit tests in `tests/run_tests.py` (`t_control_plane_ingestion_and_reclamation`) verifying lease expiration reclamation, DLQ routing on retry exhaustion, removal result ingestion, CAPTCHA queue routing, discovery listing persistence with automatic URL chaining into pending removal requests, and result draining.

* **Phase 7.5 — Fleet Monitoring, Admin Telemetry & Orchestration (Operations Boundary) — Complete:**
  - Implemented thread-safe and Redis-backed worker heartbeat registry (`backend/core/distributed/registry.py`) capturing node telemetry (`worker_id`, `hostname`, active slots, concurrency, CPU/RAM telemetry, uptime, and status transitions).
  - Wired live periodic heartbeat reporting and remote drain signal detection into `WorkerDaemon` (`backend/core/distributed/worker.py`).
  - Implemented control plane REST API router (`backend/routers/workers.py` gated by `settings.system`) providing endpoints for fleet listings, operational summaries, individual worker telemetry, remote node draining, and manual lease reclamation sweeps.
  - Built full-featured administrative worker fleet management dashboard in React (`frontend/src/pages/WorkerFleet.jsx`) with live auto-refresh, queue depth breakdown by priority channel, capacity utilization bars, node telemetry, and drain controls. Added navigation item in `Sidebar.jsx`.
  - Created distributed multi-container Docker Compose topology (`docker-compose.distributed.yml`) featuring standalone scaled worker services (`--scale worker=4`), Redis cluster transport, PostgreSQL, and FastAPI control plane.
  - *Verification:* Pure Python unit tests in `tests/run_tests.py` (`t_fleet_monitoring_and_telemetry`) verifying heartbeat registration, status transitions (online, busy, offline threshold), fleet capacity aggregation, drain signal propagation, and stale node pruning.

**Status:** Complete (Phases 7.1, 7.2, 7.3, 7.4 & 7.5 Complete).

---

### 8. Add-on distribution: Git repository to curated marketplace
**Goal:** Establish a modular distribution channel for community broker specs, solver plugins, and language packs through an integrated core catalog client and curated marketplace.

**Detailed Design:** See [`docs/CATALOG_AND_LOCALIZATION_DESIGN.md`](CATALOG_AND_LOCALIZATION_DESIGN.md).

**Phased Execution:**
- **Phase 8.1 — Core Catalog Client & Declarative Index (`index.json`) (In Design):**
  - **Catalog Client Daemon:** Implement `backend/plugins/catalog.py` on the control plane to fetch official `index.json`, maintain a local TTL-backed cache (`data/catalog_cache.json`, 4h refresh), and support conditional HTTP (`If-None-Match` / ETag).
  - **Catalog Schema & Tiering:** Declarative `index.json` defining metadata (`tier`: 1=recommended, 2=available, 3=experimental; `rank`: ordering integer within category; `recommended_bundle`: bool), checksums (SHA-256), and dependencies.
  - **Unified Install Pipeline:** Catalog installation downloads archives to ephemeral storage, verifies SHA-256 digests, and routes through the existing security boundary (`_extracted_bundle`, path traversal checks, static code inspection via `code_inspector.py`, and administrative permission grants).
  - **Air-Gapped & Resilient Fallback:** Provides graceful offline operation using cached indices or bundled fallback definitions if egress network is unavailable.
- **Phase 8.2 — Administrative Console "Browse" Tab & Update Detection (Planned):**
  - **Admin Catalog Browser:** Dedicated "Browse Catalog" tab in `frontend/src/pages/Plugins.jsx` filterable by category (`brokers`, `captcha`, `email`, `languages`, `themes`) with Tier 1 recommended items pinned to top.
  - **Update Notification Badges:** Automatic version comparison between installed plugins and catalog releases, displaying non-intrusive update badges.
  - **Admin Approval Gate:** Plugin updates require explicit super-admin review and approval before activation.
- **Phase 8.3 — Cryptographic Code Signing & Marketplace Registry (Planned):**
  - **Cryptographic Provenance:** Author signing keys, catalog root of trust, and signature validation before extraction.
  - **Public Web Directory:** Searchable registry with ratings, usage telemetry, and security audit badges.

**Status:** In Design / Active (Phase 8.1 In Design).

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
**Goal:** Provide a guided onboarding workflow for initial deployment configuration (database selection, email transports, institutional branding, HTTPS provisioning, localized experience, and recommended protections bundle).

**Detailed Design:** See [`docs/CATALOG_AND_LOCALIZATION_DESIGN.md`](CATALOG_AND_LOCALIZATION_DESIGN.md#section-5-setup-wizard-flow-enhancement).

**Architecture & Implementation:**
- **Current Guided Setup Flow (Complete):** Implemented in `routers/wizard.py` and `frontend/src/pages/SetupWizard.jsx` covering database, email, deployment/reverse-proxy, branding, and summary.
- **Transport Flexibility:**
  - **OAuth 2.0:** Recommended for Google Workspace and Microsoft 365. Utilizes scoped, expiring access tokens without storing mailbox passwords.
  - **IMAP / SMTP:** Supported for self-hosted mail servers, legacy providers, and app-specific password configurations (e.g., Apple iCloud Mail).
  - **Local Relays & Bridges:** Generic SMTP interface compatible with Proton Mail Bridge, Postfix, or enterprise outbound relays.
- **Email Mode Architecture:** Supports shared administrative inboxes and per-user mail authorization.
- **Mode Switching Grace Period:** Background monitoring (`core/email_grace.py`, `core/scheduler.py`, `routers/settings.py`) snapshots previous mailbox credentials during mode or account switches, maintaining automatic 60-day dual-inbox polling to capture delayed broker confirmations, with admin controls to extend or dismiss.
- **Planned 7-Step Enhanced Onboarding (Item 8 & 17 Synergy):**
  - **Step 1: Language Detection & RTL Preview:** Placed as the first step; detects browser language (`navigator.language`) and allows 1-click selection across Tier 1 languages (English, Spanish, French, Arabic), dynamically applying RTL layout before setup proceeds.
  - **Step 4: Recommended Protections Bundle:** Positioned immediately after email setup; queries catalog client for `tier 1` foundational brokers (StateRecords, CourtRecords, top email-first brokers), allowing the administrator to enable comprehensive protection with a single click.

**Status:** Complete (Enhanced 7-step flow & bundle planned).

---

### 12. School district authentication (Parent Portal SSO)
**Goal:** Enable authentication for parents and district staff by federating with Student Information Systems (SIS) and district identity platforms when requested by an institutional partner.

**Scope & Governance:**
- **On-Demand Prioritization:** School district and parent portal integrations (ClassLink, Clever, PowerSchool, Infinite Campus) are maintained as an on-demand institutional feature, implemented only when formally requested by a district or school system. It is decoupled from the 1.0.0 core milestone.
- **Student Privacy & Regulatory Boundaries:** While K-12 students are protected by CIPA (Children's Internet Protection Act), COPPA, and FERPA against school data disclosure, older high school students (ages 16–18) frequently appear on commercial consumer data brokers once they obtain driver's licenses, register to vote, or register for standardized tests. OpenOptOut's standard individual/family member profiles protect these students immediately through regular opt-out flows without requiring deep SIS synchronization.

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

### 15. Process memory hygiene & ephemeral storage
**Goal:** Ensure decrypted credentials (database keys, OAuth tokens, passwords) and sensitive patron PII are retained in process memory for the minimum duration necessary, and prevent memory remnants from being persisted unencrypted to physical storage.

**Phased Execution:**

- **Phase 15.1 — Ephemeral Credential Lifecycle & Process Zeroization (Complete):**
  - **Memory Zeroization:** `core/memory_hygiene.py` provides `SecureBuffer`, `ephemeral_secret`, and `scoped_credentials` context managers. Secrets are decrypted directly into mutable byte buffers, yielded strictly for the execution of connection blocks (SMTP, IMAP, tests), and overwritten with zeros on block exit or exception.
  - **Core Dump Suppression:** Process-level core dumps are disabled (`RLIMIT_CORE = 0` via `disable_core_dumps()`), container ulimits (`ulimits: core: 0`), and systemd units enforce `LimitCORE=0` to guarantee memory contents are never dumped to disk on crash.
  - **Log Sanitization:** Automated masking and strict review ensuring credentials and PII are never interpolated into log statements or exception tracebacks (Item 16).
  - **Batch Query Streaming:** Streams patron records (`stream_records` with `yield_per`) during bulk processing so sensitive records go out of scope promptly.

- **Phase 15.2 — Ephemeral RAM tmpfs (`/tmp`) Container Isolation (In Testing):**
  - **Problem Statement:** Playwright (Chromium/Firefox) headless browser automation and plugin sandboxes create temporary profile directories, caches, and screenshots under `/tmp`. Backing `/tmp` with an in-memory RAM `tmpfs` guarantees decrypted browser artifacts vanish upon reboot and never touch persistent disk blocks.
  - **Testing & Sizing Benchmarks:** Sizing benchmark suite (`deploy/tests/test_tmpfs_sizing.py` and `backend/tests/test_tmpfs_sizing.py`) monitors peak consumption across concurrent worker sessions to prevent `ENOSPC` (out of disk space) crashes during large multi-broker batches.
  - **Status:** In Testing. Empirical stress testing confirmed 100MB allocated across 4 concurrent browser workers completed in ~0.2s with zero leaks and complete cleanup. Standard recommendations: 512MB for standard instances, 1GB for high-throughput production worker fleets (`tmpfs: [ "/tmp:size=1G" ]`).

---

### 16. Operational visibility & diagnostic logging
**Goal:** Provide administrators with centralized visibility into running application versions and diagnostic logs directly from the administrative interface.

**Technical Architecture:**
- **Part A — Version & Commit Reporting:** Canonical version (`backend/VERSION`) and short git commit hash (`GIT_COMMIT`) logged at API startup and exposed via `GET /api/health` for automated probes and bug reporting.
- **Part B — Persistent Rotating Logs & In-App Viewer:** Dual-layer logging architecture combining persistent disk rotation (`/data/logs/openoptout.log`, 10MB rotations, 5 backups) with an in-memory ring buffer (2,000 records) for low-latency searching, filtering, and live UI streaming. Supported by automatic PII and credential sanitization (Bearer tokens, SIP2 credentials, query secrets, and JSON passwords) before emission. Full diagnostic log export available via `GET /api/logs/download`.
- **Part C — Dynamic Log Verbosity & Permissions:** Runtime configurable log levels (DEBUG, INFO, WARNING, ERROR) managed via `POST /api/logs/level` without requiring container restarts. Delegated access control with dedicated sensitive permissions (`logs.view` and `logs.manage`) allowing super admins to securely grant staff access to diagnostic tools.

**Status:** Complete. Documented in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).

---

### 17. Internationalization (i18n): language packs & RTL
**Goal:** Provide comprehensive localization support across the user interface, supporting community language packs, right-to-left (RTL) layout rendering, in-system translation management for administrators, universal plugin localization, and strict decoupling between patron interface language and broker legal correspondence language.

**Detailed Design:** See [`docs/CATALOG_AND_LOCALIZATION_DESIGN.md`](CATALOG_AND_LOCALIZATION_DESIGN.md#section-3-universal-plugin-localization-standard).

**Architecture & Implementation:**
- **Core Translation Architecture (Complete):** Master UI dictionary (`core/i18n.py`) with categorized translation keys, explicit screen locations ("where it appears"), and translator guidelines. Hierarchical resolution order: master English defaults → built-in translations (English, Spanish, Arabic, French, German, Portuguese, Chinese, Vietnamese, Korean, Tagalog, Hindi, Russian; the newer ones ship as JSON in `core/locales/`) → installed language pack plugins (`<plugins_root>/languages/<id>/`) → administrator custom string replacements.
- **In-System Translation & Replacement Interface (Complete):** Administrative UI (`pages/Translations.jsx` gated with `settings.manage`) enabling super admins and managers to search and filter strings by UI location, view English source text, customize wording or replace terminology, toggle active languages, and register new custom locales.
- **Right-to-Left (RTL) Support (Complete):** Dynamic layout mirroring (`html[dir="rtl"]` in `index.css`) detecting RTL scripts (Arabic, Hebrew, Persian, Urdu), mirroring navigation sidebars, form layouts, and modals while preserving left-to-right (`ltr`) direction for email addresses, URLs, phone numbers, and code blocks. Screens use logical (start/end) Tailwind classes throughout; arrows, chevrons, back/next, send, open-in-new, undo and switch icons are mirrored by one stylesheet rule (`rtl-keep` opts out); on/off switches, the mobile menu drawer and the privacy-score trend follow the reading direction. Tests `i18n.rtl_logical_classes` and `i18n.rtl_mirrored_icons` keep new screens in line.
- **Onboarding Tutorial & User Preferences (Complete):** Guided 4-step welcome walkthrough (`components/UserWelcomeModal.jsx`) allowing users to choose their language with instant UI preview, populate their Identity Vault PII for automated opt-outs, review email communications, and complete an orientation tour. User language preference and tutorial completion persist in user profile settings (`preferred_language`, `tutorial_completed`).
- **Data-Only Language Packs (Complete):** Scanned and loaded from `<plugins_root>/languages/` as data-only bundles (`manifest.json` + `messages.json`) requiring 0 permissions and zero subprocess overhead.
- **Universal Plugin Localization Standard (Complete):**
  - **Per-Plugin String Bundles:** Plugins may carry `locales/<code>.json` and declare `default_locale` and `locales` in `manifest.json`. Text is looked up by key (`description`, `instructions`, `steps.<i>.text`, or a spec's own `{"$t": key, "default": text}`). Installation checks every declared file exists, is flat key → text JSON and keeps the original `{placeholders}`.
  - **Five-Tier Resolution Chain:** Admin overrides → language pack → plugin's matching locale → plugin's default locale → the text as written (`plugins/plugin_i18n.py`). `pt-BR` falls back to `pt`.
  - **Cross-Plugin Translations via Language Packs:** `<pack>/plugins/<plugin_id>.json`. The 12 built-in packs translate all 47 built-in plugins (descriptions, checklist instructions, hand-off steps); `scripts/plugin_texts.py --check` lists gaps. Translations are machine quality.
  - **Where it shows:** Plugins page descriptions in the viewer's language; checklist instructions and "finish this yourself" steps in the member's language. Text a form step matches on the broker's page is never translated.
- **Legal Request Language vs. UI Interface Language Decoupling (Complete):**
  - **Jurisdictional Decoupling:** The letter a broker gets depends on the broker's jurisdiction and legal language, never the family's interface language. A US broker gets English; a French broker gets French under the GDPR. The "[Note: a localized template is not yet available]" prefix is gone.
  - **Broker Specification Alignment:** `BrokerSpec` declares `jurisdiction`, `legal_language` and `email_templates` per language, with defaults from `legal_basis` (`gdpr` → EU, `lgpd` → BR/pt-BR, ...). `lgpd` is a known law. Parent companies get a Country and Letter language on the Parent companies page. Letters are `letters` plugins (`plugins/bundled/letters/`); an admin can pick a different letter per broker or parent company (Admin → Opt-out letters), and an add-on can name one with `letter`.
  - **Letters (drafts, need lawyer review):** `core/legal_templates/` — CCPA (California residents), general US, GDPR (en, fr, de, es, it, nl, pt), UK GDPR, LGPD (pt-BR, en), PIPEDA (en, fr), and a law-neutral letter for other countries. Each is marked `review_status: "draft"` with a note on what to check.

**Still open:** a lawyer's review of every letter, and native-speaker review of the non-English letters and plugin translations; the Help and Plugin guide documents and text the server builds (checklist reasons, Privacy Record rows) are still English.

**Status:** Complete; reviews outstanding (above).

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

### 21. Plugin sandbox IPC & container privilege boundaries
**Goal:** Guarantee resilient, isolated inter-process communication between the host application and sandboxed plugins without resource starvation, and establish safe container privilege boundaries.

**Phased Execution:**

- **Phase 21.1 — Plugin Sandbox IPC & Resource Ceilings (Complete):**
  - **Network Namespace IPC:** HostService and plugins communicate over dedicated Unix domain sockets (`host.sock` and `plugin.sock`) bind-mounted into isolated runtime directories, enabling reliable IPC even when network namespaces are disabled for the plugin.
  - **Thread Stack Size Reduction:** Runner and SDK configure `threading.stack_size(512 * 1024)`, shrinking per-thread memory reservations to 512KB and preventing address space exhaustion under strict `RLIMIT_AS` memory ceilings.
  - **Filesystem Containment:** Plugin working directories are pinned to their dedicated runtime directories, preventing arbitrary writes to the host filesystem.

- **Phase 21.2 — Container `no-new-privileges` Sandbox Compatibility (In Testing):**
  - **Problem Statement:** Setting `no-new-privileges:true` (kernel flag `PR_SET_NO_NEW_PRIVS`) protects containers against setuid privilege escalation. On `api`, however, Bubblewrap (`bwrap`) relies on unprivileged user namespaces (`CLONE_NEWUSER`) or setuid root to construct mount and network namespaces.
  - **Testing Probe & Compatibility Matrix:** Compatibility probe (`deploy/tests/test_no_new_privs.py` and `backend/tests/test_no_new_privs.py`) audits host kernel posture, verifies unprivileged namespace creation, and checks nested seccomp transitions under `no-new-privileges:true`.
  - **Status:** In Testing. Empirical probing verified that `no-new-privileges: true` is safe and enforced on `web` and `caddy`. On `api`, kernels with AppArmor unprivileged user namespace restrictions (e.g. Ubuntu 24.04 / kernel 6.8+) block Bubblewrap UID mapping (`bwrap: setting up uid map: Permission denied`). In these environments, forcing `no-new-privileges: true` breaks Bubblewrap; the platform gracefully maintains isolation via POSIX `rlimits` and process containment while keeping container-level `no-new-privileges` on `api` opt-in.

---

### 22. Independent security audit & penetration testing
**Goal:** Engage a third-party security firm or independent security researchers to perform a comprehensive code audit and penetration test across OpenOptOut's security-critical subsystems.

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

### 23. Unified interactive host & fleet installer (CLI/TUI)
**Goal:** Deliver a guided, zero-friction terminal installation experience (`curl -fsSL ... | sudo bash`) that interactively provisions host dependencies, database engines, web servers, and tailors node installations according to their cluster role.

**Architecture & Capabilities:**
- **Interactive TUI & Scriptable Flags:** Runs an interactive terminal wizard (`whiptail`/`dialog` or formatted stdin prompts) for human operators, while supporting non-interactive flags (`--role`, `--db`, `--domain`, `--queue`, `--unattended`) for automated CI/CD and Ansible playbooks.
- **Cluster Role Specialization (Item 7 Synergy):**
  - **Standalone / All-in-One:** Installs web UI, API, database, and local browser automation on a single machine.
  - **Control Plane / UI Server:** Installs Web UI, API, Nginx, and Redis task dispatchers. *Excludes* Playwright, Firefox, Bubblewrap, and X11 graphics packages, reducing disk consumption by >1.5GB and memory overhead to sub-300MB.
  - **Worker Fleet Node:** Installs *only* the worker daemon, Bubblewrap sandbox, and Playwright Firefox + browser OS libraries. *Excludes* Nginx, Node.js, npm, frontend static builds, and public web endpoints, creating hardened headless compute instances.
- **Automated Database Provisioning:**
  - *PostgreSQL:* Prompts for credentials or runs an automated local PostgreSQL package setup, initializing database and user with random secure secrets, and writing `DATABASE_URL` to `.env`.
  - *SQLCipher:* Generates or prompts for master database encryption keys and configures Argon2/PBKDF2 key derivation.
  - *SQLite:* Initializes locked-down storage directories with restricted filesystem permissions.
- **Zero-Touch Nginx & Reverse Proxy Automation:**
  - Detects existing web servers, generates `/etc/nginx/sites-available/openoptout` with optimized reverse-proxy headers, WebSockets, SSE streaming, and client body limits.
  - Automatically symlinks to `sites-enabled` and validates syntax (`nginx -t && systemctl reload nginx`).
- **Automated TLS & Certbot Integration:**
  - Automated Let's Encrypt certificate acquisition via `certbot --nginx -d <domain>`.
  - Fallback mechanisms for internal consortium networks (custom certificate paste or internal CA configuration).
- **Pre-Flight Health Handoff:** Executes local loopback health checks before completing, outputting direct URLs and instructions for initial super-admin registration.
- **Verification:** Pure Python unit tests in `tests/run_tests.py` (`t_installer_role_specialization_and_configs`) validating role package specialization matrices, Nginx reverse proxy configuration generation, systemd unit definitions for API and worker services, and role-tailored environment configurations.

**Status:** Complete.

---

### 24. Enterprise ingress, edge security & DDoS protection
**Goal:** Harden institutional front-door routing with multi-provider reverse proxy support, Cloudflare Tunnel zero-trust ingress, edge rate limiting, and InCommon academic certificate automation.

**Architecture & Capabilities:**
- **Dual Reverse Proxy Architecture:** First-class support for both Caddy and Traefik front doors with automated configuration synthesis, container health routing, and WebSocket/SSE pass-through.
- **Cloudflare Integration & Zero-Trust Ingress:** Native support for Cloudflare Tunnel (`cloudflared`) allowing private network deployments without open inbound firewall ports. Cloudflare Proxy mode validates trusted edge IP ranges (`deploy/cloudflare/ip-ranges.txt`), restores true visitor IPs via `CF-Connecting-IP`, and safeguards against spoofed header injection.
- **Edge Flood & Brute-Force Rate Limiting:** Configurable per-visitor global request throttling (`RATE_LIMIT_PER_MINUTE`) alongside hardened thresholds for sensitive authentication endpoints (`AUTH_RATE_LIMIT_PER_MINUTE`), returning HTTP 429 with explicit `Retry-After` headers and 10-second slow-header timeouts.
- **InCommon Federation & ACME EAB Issuance:** Automated certificate issuance via CERTInext for higher-education and research institutions utilizing External Account Binding (EAB) with RSA-2048 key requirements and zero-disk ephemeral secret handling.
- **Verification:** Unit tests and end-to-end container test suites (`deploy/tests/protection_e2e.sh`, `deploy/tests/incommon_e2e.sh`) verifying rate limits, trusted proxy chains, and ACME issuance.

**Status:** Complete. Documented in [`docs/HTTPS.md`](HTTPS.md).

---

### 25. Passwordless authentication & session lifespan governance
**Goal:** Deliver modern, phishing-resistant passwordless sign-in options, eliminate password fatigue for patrons, and enforce role-tailored session duration policies.

**Architecture & Capabilities:**
- **FIDO2 / WebAuthn Passkeys:** Native passkey registration and assertion for local accounts, enabling biometric sign-in (Touch ID, Face ID, Windows Hello) and hardware security keys (YubiKey) with cryptographic challenge-response validation.
- **Email Magic Codes:** Ephemeral 6-digit one-time sign-in codes sent via institutional email with HMAC verification and 10-minute validity windows.
- **Local Account Policy Enforcement:** Optional administrative policy (`enforce_passwordless_local`) that disables password authentication for local accounts while strictly fencing external IdP accounts (SAML, LDAP, OIDC) to their respective identity providers.
- **Role-Based Session Lifespans:** Configurable token expiration windows tailored by user role (`super_admin`, `manager`, `parent`, `member`), paired with persistent "Remember Me" session tokens (up to 30 days) protected by sliding-window invalidation.
- **Brute-Force Account Throttling:** Multi-tier exponential backoff throttling sign-in attempts per account identifier and IP address, mitigating password spraying and credential stuffing without leaking account existence.
- **Verification:** Pure Python unit tests in `tests/run_tests.py` validating WebAuthn credential parsing, magic code generation/verification, session policy durations, and throttling lockouts.

**Status:** Complete.

---

### 26. Automated ILS demographic ingestion & Identity Vault synchronization
**Goal:** Streamline onboarding for library patrons by automatically pulling verified demographic attributes from Integrated Library Systems (ILS) into the encrypted Identity Vault.

**Architecture & Capabilities:**
- **SIP2 Demographic Field Mapping:** Configurable extraction of patron address lines, city, state, postal code, telephone numbers, and date of birth from SIP2 patron information responses (`64`).
- **Flexible Synchronization Modes:** Supports patron-driven import (prompted upon first login or in vault settings) as well as policy-enforced automatic provisioning (`ils_sync_demographics: "always"`).
- **Data Sanitization & Vault Encryption:** Ingested demographic fields undergo phone normalization (E.164), ZIP validation, and deduplication before being committed into AES-256 encrypted `FamilyMember` records.
- **Mock ILS Testbed Daemon:** Dedicated mock SIP2 test server (`backend/tests/mock_sip2_server.py`) bound to loopback `127.0.0.1` providing barcode validation, configurable patron responses, and demographic verification without external ILS dependencies.
- **Verification:** Test runner suite validating SIP2 parsing, field mapping transformation, and encrypted vault synchronization.

**Status:** Complete.

---

### 27. Universal accessibility (a11y) & WCAG 2.2 AAA conformance
**Goal:** Ensure the platform is universally usable by all patrons, staff, and administrators regardless of visual, motor, or cognitive abilities, adhering to WCAG 2.2 AAA standards.

**Architecture & Capabilities:**
- **In-App Accessibility Preferences:** Dedicated user preferences modal enabling High Contrast mode (enhanced borders and WCAG AAA color ratios), OpenDyslexic typeface, font scaling, and animations toggle.
- **Reduced Motion Support:** Automatic synchronization with operating system preferences (`prefers-reduced-motion: reduce`) disabling animations, transitions, and auto-scrolling behaviors.
- **Screen Reader & Keyboard Navigation:** Global skip-to-content anchor link (`#main-content`), distinct high-visibility focus rings (`focus-visible`), and accessible form controls designed to avoid nested label announcements.
- **Hierarchical Breadcrumbs:** Accessible breadcrumb navigation (`BreadcrumbNav.jsx`) across administrative and patron workflows with structured ARIA landmarks (`aria-label="Breadcrumb"`).
- **Verification:** Validated via automated browser checks, keyboard navigation flows, and screen-reader testing across dark, light, and high-contrast themes.

**Status:** Complete. Documented in [`ACCESSIBILITY.md`](../ACCESSIBILITY.md).

---

### 28. Multi-container test matrix, integration mockbed & diagnostic telemetry
**Goal:** Guarantee system reliability across deployment permutations through automated container matrix testing, live email/ILS test harnesses, and automated log diagnostic triage.

**Architecture & Capabilities:**
- **Docker Profile Matrix Runner:** Automated test script (`scripts/test-docker-matrix.sh`) executing end-to-end verification across core profiles (`base`, `https-caddy`, `https-traefik`, `distributed`), verifying container startup, health probes, UI rendering, and security posture.
- **Automated Failure Diagnostics:** Log triage scanner (`.github/release-test/scan_logs.py`) analyzing multi-container log streams, filtering benign warnings, and outputting aggregated markdown diagnostic reports (`error-report.md`) with actionable failure traces.
- **Live Email Verification Probe:** Test harness (`scripts/test-email-account.py`) supporting Google/Microsoft OAuth 2.0 as well as IMAP/SMTP app passwords to verify mailbox connectivity, send/receive loops, and folder permissions.
- **Verification:** Continuously executed via local development scripts and automated CI workflows.

**Status:** Complete.

---

### 29. Parent-company catalog & broker spec metadata
**Goal:** One opt-out per company instead of one per front-site, and specs that say what each opt-out legally owes and what it will ask of a person.

- **Parent catalog** (`core/catalog/parent_companies.json`, `core/parent_catalog.py`): StateRecords, CourtRecords, PeopleConnect/Intelius, BeenVerified, Whitepages and Spokeo with their child sites, plus "opting out here also removes you there" cascades. Applied from Parent companies; never overrides an admin's data.
- **Spec metadata:** `legal_basis`, `statutory_response_days` (gives every request a due date), `search_url` / `listing_pattern`, `one_optout_per_email`, `requires`, `source`, `last_verified`; the `pause_for_human` step; `contact_email` and `listing_url` fields.
- **Per-broker email opt-outs** send again (fixed send path); no guessed `privacy@` addresses.
- **Credits:** [`CREDITS.md`](../CREDITS.md), linked from the README.

**Status:** Complete (#67).

---

### 30. Family inboxes & one address per opt-out
**Goal:** Opt-outs are sent from, and answered at, each person's own inbox; the system inbox only sends notifications.

- Each user connects an inbox (OAuth or app password); a parent can connect several and assign one to each family member.
- Every opt-out gets its own `+address` (`you+oo<random>@domain`) where the inbox allows it, so replies are matched exactly and addresses that later receive mail from someone else reveal who shared them.
- Replies are matched by tag, then by tracking key, then (for plain addresses) by the broker's sending domain. Family inboxes are polled with the system inbox.
- See [`docs/EMAIL_SETUP.md`](EMAIL_SETUP.md).

**Status:** Complete (#69).

---

### 31. Find your listings
**Goal:** Help people find where they're listed and put each listing into the removal cycle.

- Search links built from every name, phone, address and email in the identity vault (adapted from Opt-Out Desk, MIT); one search per known broker.
- Paste a listing's address: the broker is worked out from the domain (or its parent or network) and a removal request is created with the listing attached. Unknown sites become checklist items.

**Status:** Complete (#70).

---

### 32. State broker registries, dead-site detection & California DROP
- California, Vermont, Texas and Oregon registries can be imported. Imported brokers are **off by default**; an admin turns them on after a warning that it can do more harm than good.
- Brokers whose sites stop answering for 30 days are marked defunct.
- California's DROP deletion service appears as a checklist item for California residents.
- See [`docs/STATE_REGISTRIES.md`](STATE_REGISTRIES.md).

**Status:** Complete (#71).

---

### 33. General web search
- Server-side searches through a self-hosted SearXNG (the only provider). Strong matches on known brokers are added to removals automatically; everything else waits for "That's me" / "Not me". Weekly re-runs.
- See [`docs/WEB_SEARCH.md`](WEB_SEARCH.md).

**Status:** Complete (#72).

---

### 34. Checklist & per-variant removal report
- **Checklist page:** everything that needs a person (connect an inbox, finish by hand, confirm a link, CAPTCHAs, "is this you?", overdue brokers, re-checks) with progress per family member.
- **Per-variant report:** Dashboard card comparing removal of the main details (full name, current address, phone) with every other saved variant.

**Status:** Complete (#73, #75).

---

### 35. Broker confirmation links
- A reply asking for a click no longer counts as a removal. The link is saved encrypted and clicked after each email check: https only, on the broker's or parent's domain (or a click-tracker that lands there), public addresses only, re-checked at every redirect. A hidden browser presses "Confirm" buttons when needed.
- Links that can't be clicked go on the checklist. Email plugins return links so message bodies stay in the sandbox.

**Status:** Complete (#76).

---

### 36. Curated broker form plugins & honest form results
**Goal:** Finish automated form filling: real steps for the big people-search sites, and results that never claim more than happened.

- **Built-in broker plugins** in `backend/plugins/bundled/brokers/`, installed at startup: automated Spokeo, MyLife, BeenVerified and Radaris (selectors from Blake104/OptOut, verified upstream 2026-05); guided Whitepages, FastPeopleSearch, TruePeopleSearch, Nuwber, That's Them, USPhoneBook, SmartBackgroundChecks, SearchPeopleFree, FamilyTreeNow, Cyber Background Checks, Clustal and Social Catfish (steps from BADBOOL), which hand the person a one-time address so replies and confirmation links are still automatic.
- **Engine:** `type` step for React/MUI inputs, actions inside iframes, `{field}` page addresses, derived fields (`street`, `state_name`, `birth_year`, `phone_digits`), whole-name option matching, invisible reCAPTCHA ignored, Turnstile waited out.
- **"+" addresses:** a form that calls the email invalid is retried once with the plain address and the broker is remembered.
- **Honest results:** brokers without steps go on the checklist instead of a best-guess fill (guessing is an admin opt-in and must show a success page); manual brokers are no longer marked "sent"; a submitted form stays "sent" until the broker replies, its link is clicked, or someone checks the listing is gone; missing details become a checklist item naming the field.
- **Tooling:** `broker-plugins/tools/validate.py` dry-runs every plugin. See [`broker-plugins/README.md`](../broker-plugins/README.md) and [`docs/INTERPRETER.md`](INTERPRETER.md).
- **Open:** live verification of every plugin; handing a live browser to a person at a pause so they can finish in place instead of starting over.

**Status:** Complete (#77) — live verification pending.

---

### 37. Long tail: privacy-request page finder & hosted privacy forms
**Goal:** Cover brokers no one has written steps for. Find a site's privacy-request page, and fill the hosted forms many companies use (OneTrust, TrustArc) with one shared handler.

- **Privacy-page finder** (`core/privacy_finder.py`): reads a broker's own website (no personal data sent, at most 8 public pages) for hosted OneTrust/TrustArc forms, in-house request forms, opt-out pages, policies and privacy email addresses. Daily for 20 brokers without steps (30-day recheck), immediately for sites from pasted listings, or on demand from the Brokers page.
- **Label-driven form filler** (`autofill` step, `interpreter/hosted_forms.py`): picks delete / do-not-sell and "myself", fills name, one-time email and address, ticks certifications, never marketing boxes; refuses ID/SSN/DOB fields, forms without a name and email box, and request types without deletion — those go on the checklist with the page.
- Found forms become the broker's opt-out steps after plugins and admin scripts; their verification emails are clicked via item 35. Found email addresses are used only after an admin approves them.
- See [`docs/PRIVACY_PAGES.md`](PRIVACY_PAGES.md).

**Status:** Complete (#79) — live verification pending.

---

### 38. Built-in receive-only inbox
**Goal:** Unique addresses on a family-owned domain for inboxes without `+` addressing. Design: [`docs/BUILTIN_INBOX.md`](BUILTIN_INBOX.md).

**Status:** Not Planned (2026-10-12): Gmail and Microsoft "+" addresses cover it; Yahoo/AOL and brokers that refuse "+" already fall back to the plain address.

---

### 39. Automated removal verification & re-listing monitor
**Goal:** Know that removals stuck, and catch listings that come back.

- `core/verification.py` checks each removal through the listing page, the broker's own search (`search_url` / `listing_pattern`) or a site-restricted web search confirmed by visiting the page.
- Verdicts: gone, still up, not found, couldn't check. Sent + gone → removed; removed + still up → sent again ("came back").
- Runs daily within a budget, before every scheduled re-send, and whenever the weekly web search finds a page on a broker someone was removed from.
- Dashboard *Removal checks* card. See [`docs/VERIFICATION.md`](VERIFICATION.md).

**Status:** Complete (#82) — live verification pending.

---

### 40. Data-sharing detection & aggregator-first targeting
- **Sharing:** opt-out addresses that receive mail from a company they were never given to become "given to → came from" edges (possible / likely / strong by how many distinct addresses), excluding the broker's own family. Admin → Data sharing.
- **Targeting:** brokers weighted by known wholesalers (`catalog/aggregators.json`), cascades, family size and observed sharing; new default dispatch order "aggregators first".
- See [`docs/DATA_SHARING.md`](DATA_SHARING.md).

**Status:** Complete (#83).

---

### 41. Encrypted backups
- Database (consistent SQLite copy or `pg_dump`), settings, installed plugins and the keys, in one file encrypted with AES-256-GCM under a scrypt-derived passphrase key; authenticated frames refuse truncated or altered files.
- Destinations: local folder / mounted network drive, SFTP (host key pinned), S3-compatible (Amazon S3, Google Cloud Storage, Backblaze, Wasabi, MinIO), Google Drive, OneDrive, Dropbox; retention per destination; daily or weekly schedule; restore and verify commands.
- See [`docs/BACKUPS.md`](BACKUPS.md).

**Status:** Complete (#85, #91).

---

### 42. Automatic broker steps & AI helpers
- **Repairs:** a failure classified as "form not found" queues a repair (once a day per broker). The current steps are rehearsed with made-up details; the step that broke is pointed at the field or button with the same meaning on the new page (built-in rules, no AI); an AI helper is asked only if the rules can't fix it.
- **New brokers:** an AI helper drafts steps from the broker's public opt-out page; drafts always wait for an admin.
- **Guardrails:** every draft is rehearsed and stops before the final click; only a passing, selector-only repair applies itself (with a notice and Undo); requests to helpers are refused if they contain any saved personal detail; drafts are checked to stay on the broker's site and never type fixed values; a plugin update sets older repairs aside.
- **Helpers (bring your own key):** Claude (Anthropic API), ChatGPT/Codex models (OpenAI Responses API), Google's Antigravity agent (Gemini Interactions API, preview; read-only page access), and your own model on your network through any OpenAI-compatible server (LM Studio, Ollama, llama.cpp, vLLM…). Order, monthly limit for online helpers, and on/off switches on **Admin → Automatic broker steps**.
- **Coding agents:** `AGENTS.md`, `CLAUDE.md` and a shared `broker-plugin` skill so Claude Code, Codex and Antigravity write and fix broker plugins to the project's rules.
- See [`docs/AUTOMATIC_STEPS.md`](AUTOMATIC_STEPS.md).

**Status:** Complete (#98) — not yet run against live providers or live broker sites.

---

### 43. Plain language for people and family pages
**Goal:** Eliminate confusing technical jargon across all public and family-facing workflows.

- Renamed and simplified screens: status labels, Dashboard, Email monitor, Find listings, Check again, CAPTCHAs, Family, Your details, Broker sites, Login, Settings, and Help.
- Automated testing (`jargon` test) protects family screens against re-introducing engineering jargon.

**Status:** Complete (#86, #87).

---

### 44. Phone and email removal, birthday matching, and credit freeze letters
**Goal:** Expand removal coverage to phone- and email-keyed directory sites, optional encrypted birth dates, and credit freezes.

- Sites marked `lookup_by` phone or email dispatch one opt-out per saved number or address across 14 specialized directory plugins (Truecaller, Sync.ME, CallApp, Hiya, CallerSmart, NumLookup, Spy Dialer, ReversePhoneLookup, NumberGuru, RocketReach, Apollo, Hunter, ZoomInfo, Lusha).
- Optional encrypted birthday with age-aware matching rules to disambiguate namesakes without exposing exact birth dates.
- Dedicated Freeze credit page providing standardized freeze request letters for Equifax, Experian, and TransUnion (adult and child under 16); SSNs are never stored or handled by OpenOptOut.

**Status:** Complete (#88).

---

### 45. Removal timeline & round tracking
**Goal:** Transparently record every removal status transition and visualize longitudinal progress.

- Removal timeline logs every status change in sequential rounds (sent → reply → removed → staying gone; found again → next round).
- Per-site progress bar visualizes lifecycle progress and recurring verification sweeps.

**Status:** Complete (#89).

---

### 46. Plain language for admin pages & localized status badges
**Goal:** Apply plain-language standards to administration screens and localize operational badges.

- Standardized admin navigation, management views, and system error notices.
- Menu items and status badges fully localized across all 12 supported languages.

**Status:** Complete (#90).

---

### 47. Cloud backups through rclone
**Goal:** Support arbitrary cloud storage providers without bloating core platform dependencies.

- Added "Other cloud storage" provider powered by pinned, checksum-verified `rclone` binary in the image.
- Supports Proton Drive, Box, pCloud, MEGA, Nextcloud, and other standard remote protocols with private temporary configuration files and input validation.

**Status:** Complete (#91).

---

### 48. Privacy record, access logging, and deadline reporting
**Goal:** Provide full compliance reporting, staff audit visibility, and data subject rights management under GDPR and CCPA.

- Privacy Record: Complete inventory of stored personal data (GDPR Art. 30), staff access log for cross-account viewing, per-person JSON data export, configurable retention policies, and self-service account deletion.
- Fix family member addition and deletion to cascade cleanly across all related database records.
- Re-landed statutory deadline reporting and opt-in alert notices for delinquent brokers.

**Status:** Complete (#92).

---

### 49. Decoupled language packs, privacy score, PDF reports, and calendar scheduling
**Goal:** Modularize language distribution, track privacy posture quantitatively, and offer privacy-respecting scheduling.

- Decoupled language system: English core with 12 built-in language pack plugins (`lang-*`) that administrators can enable, disable, or replace.
- Privacy Score: 0–100 composite index tracking removal progress and exposure reduction over time with historical snapshots.
- PDF Removal Reports: Clean, printable PDF summaries of removal status and scores without printing sensitive personal details.
- Calendar scheduling: Configurable opt-out execution weekdays, holidays, calendar page, and private authenticated `.ics` subscription feed.

**Status:** Complete (#93).

---

### 50. Live CAPTCHA hand-off & privacy-preserving solvers
**Goal:** Allow users to solve complex CAPTCHAs interactively while keeping automated third-party solving privacy-safe.

- Interactive "Solve it here": Browser session is mirrored to a secure user-facing page where the user completes the CAPTCHA inside the live broker page, and automation resumes automatically.
- Privacy-safe automated solvers: Challenge redaction (`core/captcha_privacy.py`) crops the puzzle and blacks out personal details before dispatching to external solving services (2Captcha, Anti-Captcha, CapSolver, CapMonster) using encrypted credentials.

**Status:** Complete (#94).

---

### 51. Unclear match resolution & listing disambiguation
**Goal:** Safely handle ambiguous search results that return only names without location, age, or phone identifiers.

- Policy-driven disambiguation: Admin-configurable default behavior (ask on Checklist, skip, or remove all up to 10 listings) with individual user override.
- Automated negative filtering: Drops candidate profiles that explicitly contradict known attributes (e.g. mismatched age or middle initial).
- Added `pick_listing` step and Skipped status to the declarative interpreter.

**Status:** Complete (#95).

---

### 52. Full UI translation framework across 12 languages
**Goal:** Localize every user interface phrase into all 12 supported languages.

- Complete internationalization pass: All interface phrases routed through `tx()`, `txn()` (plurals), and `txr()` (rich text).
- 2,450 phrases translated into Spanish, French, Arabic, German, Portuguese, Chinese, Vietnamese, Korean, Tagalog, Hindi, and Russian.
- CI extractor and synchronization tests ensure zero untranslated screen phrases.

**Status:** Complete (#96).

---

### 53. Plugin localization standard & jurisdiction-based legal letters
**Goal:** Enable plugins to provide their own localized strings and decouple opt-out legal language from UI display language.

- Plugin localization: Plugins declare `locales/` directories or reference language pack dictionaries; checklist steps display in the user's preferred language while form selectors remain exact.
- Decoupled legal letters: Broker opt-out communications select legal templates by broker/parent `jurisdiction` and `legal_language` (CCPA, GDPR, UK GDPR, LGPD, PIPEDA, US general, law-neutral) rather than the account's UI language.

**Status:** Complete (#97).

---

### 54. Universal live hand-off for interactive steps ("Do it here")
**Goal:** Extend live interactive browser hand-off to all manual confirmation and verification steps.

- Generalizes the live session hand-off beyond CAPTCHAs to any `pause_for_human` step (e.g., SMS verification codes, security questions, email confirmation PINs).
- Reruns automation up to the interactive step, hands control to the user in a safe sandboxed frame, and seamlessly continues automation once complete.

**Status:** Complete (#99).

---

### 55. Yahoo OAuth-only email integration
**Goal:** Modernize Yahoo Mail integration with secure OAuth sign-in and token-based IMAP/SMTP access.

- Removed legacy insecure app-password authentication in favor of standard Yahoo OAuth flow (`mail-r`, `mail-w`).
- Reads confirmation emails over IMAP with `BODY.PEEK` using OAuthBearer / XOAUTH2 tokens without marking emails as read.

**Status:** Complete (#100).

---

### 56. Comprehensive RTL mirroring & logical layout
**Goal:** Deliver first-class right-to-left layout support for Arabic and RTL languages.

- Converted all layout rules to directional Tailwind utilities (`ms-`, `pe-`, `start-`, `text-end`, `border-s`).
- Global stylesheet rule mirrors navigational and directional icons automatically.
- Enforced by `i18n.rtl_logical_classes` and `i18n.rtl_mirrored_icons` automated tests.

**Status:** Complete (#101).

---

### 57. Configurable regional date, time, and number formats
**Goal:** Respect administrative and cultural formatting conventions across all numeric and temporal displays.

- Admin setting for system regional formats (locale, 12h/24h clock, first day of week, digit sets, time zone).
- Client formatting pipeline (`i18n/format.js`) standardizes dates and numbers across screens while leaving legal broker communications in the broker's statutory format.

**Status:** Complete (#103).

---

### 58. Modular opt-out letter plugins
**Goal:** Convert legal opt-out text templates into modular, installable plugins.

- Built-in letters decoupled into `letters` plugin type (`backend/plugins/bundled/letters/`).
- Admins can assign custom letters per broker or parent organization with live preview using sanitized mock details.

**Status:** Complete (#104).

---

### 59. Monitoring, Prometheus metrics, webhooks, and log forwarding
**Goal:** Production-grade observability, health probing, and alerting for homelab and enterprise clusters.

- Endpoints: Unauthenticated `/api/health/ready` liveness probe and token-authenticated Prometheus `/api/metrics`.
- Outbound webhooks: Real-time event notifications to ntfy, Gotify, Slack, Teams, Discord, Home Assistant, or signed JSON payloads with zero PII egress.
- Scrubbed log forwarding: Streams sanitized logs to syslog (UDP/TCP/TLS), OTLP, Loki, or Splunk HEC.

**Status:** Complete (#105).

---

### 60. Broker pack 1 (50 independent plugins) & coverage calculation
**Goal:** Significantly expand out-of-the-box opt-out coverage across independent data brokers.

- Pack 1 adds 50 curated broker plugins targeting high-impact upstream data wholesalers, directory networks, and public records platforms.
- Calculates and displays cumulative site coverage (direct broker + parent networks + confirmed downstream cascades).
- Unchecked plugins start disabled until verified or approved by an administrator.

**Status:** Complete (#106).

---

### 61. Terms, operational limits, and transparency notices
**Goal:** Transparent communication of platform capabilities, legal constraints, and operator responsibilities.

- Plain-language disclosure accepted during setup explaining what automated opt-outs can and cannot guarantee.
- Per-member transparency notice presented prior to storing personal identifiers.
- Editable terms template for institutional and multi-family deployments.

**Status:** Complete (#107).

---

### 62. Automated discovery response for inactive brokers
**Goal:** Handle listings found on disabled brokers according to administrative policy.

- Policy rules: Automatically enable the broker once listings reach N members, request admin review, or notify the affected person with manual instructions.

**Status:** Complete (#108).

---

### 63. Usage statistics API for institutional data warehouses
**Goal:** Replace academic journal metrics (COUNTER/SUSHI) with a streamlined analytics API for libraries and universities.

- Lightweight authenticated endpoint (`/api/stats/v1`) providing aggregated daily, weekly, and monthly counts.
- Designed for ETL ingestion into library analytics platforms (e.g. Springshare LibInsight) or corporate data warehouses without exposing individual patron records.

**Status:** Complete (#110).

---

### 64. Address-verified registration for housing communities
**Goal:** Enable self-service onboarding restricted to verified residents of housing districts and apartment complexes.

- Management uploads an authorized address CSV list (with unit/apartment normalization).
- Sign-up flow validates resident address eligibility prior to account creation, rate-limits lookups, and auto-populates verified address into the member's profile.
- Provides secure fallback contact details for unlisted units.

**Status:** Complete (#116).

---

## Explicitly Deferred / Open Questions

- Formal declarative-vs-code boundary definition for edge-case broker add-ons (Item 1).
- Add-on cryptographic signing and provenance model for automated marketplace installations (Item 8).
- Selection of distributed queue architecture (Redis/RQ vs. Celery) and secure cross-worker PII serialization (Item 7).
- Operational scalability and ethical policies regarding third-party CAPTCHA-solving services (Item 4).
- Prioritization of Student Information System (SIS) vendor integrations for school district deployments (Item 12).
- Community review and governance model for community-contributed language packs (Item 17).
- Theme customization boundary: token-level styling vs. structural layout modifications (Item 18).
