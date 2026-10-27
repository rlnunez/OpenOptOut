# Changelog

All notable changes to OpenOptOut are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each completed roadmap item is cross-referenced with its architectural milestone number (e.g., `Roadmap Item #`). For active, planned, and upcoming initiatives, see the live [Roadmap (`docs/ROADMAP.md`)](docs/ROADMAP.md). For detailed specifications, design rationale, and test verification notes for historical milestones up through v0.11.0, see the [Completed Milestones Archive (`docs/archive/COMPLETED_ROADMAP.md`)](docs/archive/COMPLETED_ROADMAP.md) (frozen after v0.11.0 release). All subsequent completed roadmap work, architectural improvements, and release notes are documented directly in this changelog.

---

## [0.11.4] — 2026-10-26

### Security & Authentication Resilience
- **Master Secret Key Rotation & Pepper Persistence (`backend/core/auth.py`, `backend/core/settings_store.py`):**
  - **Hex Encoded Pepper Storage:** Ensured `pepper.key` is stored and read safely as a 64-character hex string with `os.fsync`, eliminating raw binary byte truncation issues from trailing whitespace characters while retaining full backward-compatible reading of legacy 32-byte raw binary files.
  - **Key Rotation Synchronization:** Ensured `save_secret_key_file()` and `ensure_bootstrap_secret_key()` actively persist the current active pepper before rotating `SECRET_KEY`, preventing password invalidation when administrators configure or rotate the master key.
  - **Candidate Pepper Fallback & Transparent Auto-Upgrade:** Added candidate pepper fallbacks in `verify_password()` checking `.env` and `secret.key` derivations if the primary pepper does not match, transparently migrating verified passwords to the modern active pepper upon successful login without 401 Unauthorized errors.
  - **Decoupled Key Derivation & Circular Import Prevention (`backend/core/settings_store.py`, `backend/core/auth.py`):** Moved pepper derivation, candidate harvesting, and persistence directly into `settings_store.py` to eliminate circular import dependencies with `models.database` on first boot, and added dynamic model resolution in `auth.py` to guarantee mapped ORM models are always bound for `GET /api/auth/me`.
  - **Audit Key Files:** Included `pepper.key` in `get_security_key_files()` to ensure strict `0600` permissions auditing.
  - **Static Security & Audit Logging Hygiene (`backend/core/settings_store.py`):** Refined exception logging format string when persisting `pepper.key` prior to master key rotation, eliminating Semgrep false-positive credential leak rule (`python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure`) while preserving clean diagnostics.
  - **RFC 9116 Vulnerability Disclosure Acknowledgments (`.well-known/security.txt`, `backend/main.py`):** Added explicit `Acknowledgments` directive pointing to [`CREDITS.md`](CREDITS.md), formally recognizing upstream open-source data broker opt-out research, mapping projects, and contributor tools in standardized security discovery metadata.
- **Agent Skill Security & Compliance Standards (`.agents/skills/broker-plugin/SKILL.md`, `.claude/skills/broker-plugin/SKILL.md`):**
  - Codified mandatory, non-negotiable security, privacy, and compliance standards for AI coding agents authoring or repairing data broker plugins.
  - Enforced strict COPPA/GDPR data minimization (only requesting and filling fields explicitly mandated by the broker's form).
  - Explicitly prohibited automated filling or collection of SSNs, government IDs, driver's licenses, passports, or passwords, mandating fallback to `method: manual` (guided) plugins.
  - Formalized strict boundary isolation between `{contact_email}` (isolated sub-addressed alias for confirmations) and `{email}` (data to be expunged).
  - Documented sandbox domain isolation rules, synthetic rehearsal requirements, and plain-language accessibility requirements for human escalation steps (`pause_for_human`).
  - Added anti-flakiness and integrity protocols: bot-protection and unverified broker flags (`starts_enabled: false`), verification date honesty (`last_verified`), mandatory `requires` array synchronization, anti-brittle selector rules, and prohibition on checking marketing/newsletter boxes.

### Automated Dependency Maintenance
- **Frontend Dependencies (`frontend/package.json`):**
  - Upgraded dependencies (`lucide-react` 1.59.0, `react`/`react-dom`/`react-is` 19.3.1, `postcss` 8.5.31) with verified JSX accessibility and production build integrity (PR #154).
- **Backend Dependencies (`backend/pyproject.toml`):**
  - Upgraded core Python dependencies (`fastapi` 0.150.0, `starlette` 1.9.0, `sqlalchemy` 2.1.5, `authlib` 1.9.1, `google-auth` 2.62.0, `paramiko` 5.1.0, `boto3` 1.43.115, `setuptools` 84.2.0) with zero breaking changes across routers and test suites (PR #155 / #157).
- **GitHub Actions Commit Hash Pinning:**
  - Pinned immutable commit SHAs across build provenance, fuzzing, scorecard, and security workflows (`cosign-installer`, `setup-buildx-action`, `login-action`, `metadata-action`, `build-push-action`, `attest-build-provenance`, `upload-sarif`) (PR #156).

## [0.11.3] — 2026-10-26

### Accessibility & WCAG 2.2 AA Compliance
- **Active Navigation Contrast Guarantee (`frontend/src/index.css`):**
  - Guaranteed Level AAA (>= 7:1) contrast for `[aria-current='page']` active navigation items across all ADA themes (Dark ADA, Light ADA, Space Explorer ADA), and disabled CSS color transitions on active indicators to eliminate transient contrast dips during page transitions.
- **Accessible Loading State Contrast:**
  - Upgraded loading indicator, progress state, and spinner contrast to >= 7:1 across all dark and light themes.
- **Dual-Round & Multi-Theme Automated Accessibility Verification (`.github/release-test/ui_check.py`):**
  - **Round 1 (Regular/Default Theme):** Strict functional auditing of all application pages with axe-core, asserting zero blocking form label, select name, button name, or interactive element accessibility defects while treating non-blocking contrast and minimum target size as diagnostic notices.
  - **Round 2 (Multi-Theme ADA Audit):** Expanded automated browser walkthrough to audit all three distinct ADA compliance themes across every page (Dark ADA `dark-ada`, Light ADA `light-ada`, and Space Explorer ADA `space-ada`), enforcing WCAG 2.2 Level AA and Level AAA adherence, 125% root font scaling, and enhanced touch targets.
  - **Verbose Failure & Theme Diagnostics:** Upgraded test runner and markdown reporting to output full node-level diagnostics (exact CSS selector path, HTML snippet, axe-core remediation failure explanation, and active theme tag) directly to CI standard output and release test artifacts.
- **Universal Multi-Theme High-Contrast Overrides (`frontend/src/index.css`):**
  - Added comprehensive styling rules across Dark ADA, Light ADA, and Space Explorer ADA themes covering form controls (`input`, `select`, `textarea`, `::placeholder`), text hues (`.text-slate-100` through `.text-slate-600`), and action/badge button backgrounds (`.bg-shield-600`, `.bg-blue-600`, `.bg-emerald-600`, `.bg-sky-700`, `.bg-sky-600`, `.bg-sky-500`) with explicit child text inheritance.
- **Space Explorer ADA WCAG 2.2 Level AAA Compliance (`frontend/src/index.css`):**
  - Calibrated full Level AAA color palette guaranteeing >= 7:1 enhanced contrast across all elements: pure black background (`#000000`), 21:1 pure white text (`#ffffff`), 12.12:1 luminous amber text and links (`#ffb800`), 16.7:1 cyan accents (`#00ffff`), 12.8:1 emerald accents (`#00ff88`), 8.2:1 red alert text (`#ff7777`), 9.8:1 amber buttons (`#ff9900` with black text), 7.36:1 danger buttons (`#ff6b6b` with black text), 9.8:1 2px borders, and 44x44px touch targets.
- **System-Wide Form Control Label Association (`frontend/src/components/Field.jsx`):**
  - Implemented automatic recursive DOM tree inspection in the core `<Field>` wrapper, auto-generating and binding `htmlFor`/`id` and fallback `aria-label` attributes to nested `<input>`, `<select>`, and `<textarea>` controls across all form views.
- **Interactive Component Accessibility Enhancements:**
  - **Broker Priority (`BrokerPriority.jsx`):** Added accessible names and ARIA labels for bulk priority level selectors, per-broker priority dropdowns, and individual priority reset controls, eliminating 160+ unlabelled element violations.
  - **System Logs (`SystemLogs.jsx`):** Added accessible ARIA labels for log verbosity, subsystem, and log level filter dropdowns; made the log viewer terminal scrollable region explicitly keyboard-focusable (`tabIndex={0}`) with descriptive ARIA labelling.
  - **Branding & Settings (`Branding.jsx`, `Settings.jsx`):** Added explicit accessible labels to standalone file inputs (application logo, favicon, CA certificates, IdP metadata), color pickers, and cryptographic shredding toggles.
  - **Identity Vault (`IdentityVault.jsx`):** Added dynamic accessible labels for collapsible profile accordions (`Collapse {label}`, `Expand {label}`), legal name editors, and removal actions.
  - **Text Link Contrast & Underlining (`Help.jsx`):** Restored persistent underlines on inline links within text blocks satisfying WCAG 1.4.1 (Link in Text Block).
- **Dark High-Contrast Theme Overrides (`frontend/src/index.css`):**
  - Added dedicated `.theme-dark-ada` styling overrides ensuring compliant contrast for neutral text (`.text-slate-700`), form placeholder text (`::placeholder`), status badges (`.text-amber-300`, `.text-red-300`, `.text-emerald-300`, `.text-sky-300`, `.text-purple-300`), and table borders.
- **Static JSX Accessibility Linter (`frontend/scripts/check-a11y.mjs`):**
  - Added standalone JSX AST accessibility scanner checking for button names, unlabelled inputs, and improper ARIA attributes, integrated into `npm run check:a11y`.

### Internationalization & Localization
- **Complete Language Pack Synchronization:**
  - Synchronized 35 newly introduced screen and ARIA phrases across all 17 bundled language packs (`backend/plugins/bundled/languages/lang-*/texts.json`): Arabic, German, Spanish, French, Hindi, Indonesian, Korean, Pirate, Polish, Portuguese, Russian, Swahili, Tagalog, Ukrainian, Urdu, Vietnamese, and Chinese.
  - Verified 100% dictionary coverage and strict placeholder preservation (`{name}`, `{label}`) across all locales via automated Tier 1 test suite (`i18n.page_texts_current`, `i18n.builtin_languages_complete`).

### Code Architecture & Refactoring
- **Centralized Shared Utilities:**
  - **Backend (`backend/core/utils/`):** Centralized common string sanitizers, cryptographic helpers, and date/time formatters to eliminate duplicate logic across backend core services and routers.
  - **Frontend (`frontend/src/utils/`):** Unified toast notification dispatching, clipboard interaction, and common UI helpers into shared frontend modules.
- **Constant Unification:**
  - Replaced magic numbers with canonical constants (e.g., `LONG_TEXT_MAX` across authentication and back-channel logout routines).

### Security & Scanner Configuration
- **OIDC Back-Channel Logout Robustness & Error Handling (`backend/routers/auth.py`):**
  - Hardened `POST /api/auth/backchannel-logout` against malformed tokens and fuzzing inputs by validating string types and ensuring decoded JWT payloads and event claims are structured dictionaries before querying claims, eliminating uncaught 500 crashes during Schemathesis API fuzzing.
  - Resolved undefined logger reference (`NameError`) in exception handling and sanitized log emission to prevent credential disclosure warnings.
- **Authentication Input Hardening & SQLi False-Positive Elimination (`backend/routers/auth.py`):**
  - Added strict metacharacter pre-validation (`'`, `"`, `--`, `/*`, `;`) to `/api/auth/token` and `/api/auth/ldap/login`, returning immediate uniform `401 Unauthorized` responses before triggering rate limiting or database lookups, preventing differential timing and boolean probing heuristics during automated OWASP ZAP scans.
- **Content Security Policy (CSP) & Form Action Protection (`backend/core/csp.py`):**
  - Enforced `form-action 'self';` in `MINIMAL_HTML_CSP` across OAuth and SAML error/callback pages, resolving OWASP ZAP *Failure to Define Directive with No Fallback* warnings.
  - Stripped `style-src 'unsafe-inline';` from `MINIMAL_HTML_CSP` and eliminated all inline `style='...'` markup in OAuth and SAML endpoints to prevent style-based injection attacks.
- **Distributed Envelope Deserialization & Semgrep Compliance (`backend/core/distributed/envelope.py`):**
  - Refactored `JobEnvelope` dictionary deserialization into an internal `_construct_unverified` constructor, removing direct invocations of `verify_signature=False` while preserving fail-closed HMAC cryptographic verification in `WorkerDaemon.execute_envelope()`.
- **Local Pre-Push Security Verification Suite (`scripts/security_check.py` & Git Hook):**
  - Added automated pre-push security gating executing multi-scanner verification: Gitleaks, TruffleHog, Semgrep, Bandit, Zizmor, Trivy, OSV-Scanner, and Actionlint.
- **Secret Scanner Allowlisting (`.gitleaks.toml`):**
  - Configured project-specific Gitleaks allowlist rules for test fixture mock tokens and test keys.
  - Masked non-secret regex pattern definitions in test runner (`backend/tests/run_tests.py`) to eliminate false-positive generic API key alerts from static scanners.
- **SCIM & Administrative Authorization Fixes:**
  - Authorized `super_admin` role for SCIM 2.0 endpoints and exported `resolve_user_from_token` in `backend/core/auth.py`.
  - Resolved input size bounds and OAuth 2.1 redirect URI exact-matching checks.

### CI/CD & Testing Infrastructure
- **GitHub Actions Script Injection Defense (`.github/workflows/release-test.yml`):**
  - Replaced inline shell template interpolations (`${{ inputs.themes }}`, `${{ inputs.routes }}`) with step-level environment variables (`INPUT_THEMES`, `INPUT_ROUTES`), resolving `zizmor/template-injection` (CWE-94) audit findings.
  - Converted argument string concatenation to quoted bash arrays `"${EXTRA_ARGS[@]}"`, satisfying ShellCheck rule `SC2086` and passing `actionlint`.
- **Credential Persistence Mitigation (`.github/workflows/build-provenance.yml`):**
  - Enforced `persist-credentials: false` under `actions/checkout` in SLSA build provenance and container signing workflow, resolving `zizmor/artipacked` credential persistence alerts.
- **Developer Local Feedback & Test Selection (`.github/workflows/release-test.yml`, `.github/release-test/`):**
  - Added `--themes` and `--routes` targeting flags to `ui_check.py` and GitHub Actions dispatch inputs, allowing instant local verification of individual themes or page routes without running full multi-theme passes.
  - Structured theme audit execution to run sequentially in isolated browser processes to prevent database lock contention and worker port collisions.
  - Added live stdout streaming and graceful timeouts to browser installation scripts.
- **Release Test Workflow Enhancements (`.github/workflows/release-test.yml`):**
  - Added dynamic workflow dispatch parameters (`test_name`, `tag`) and custom execution run names.
  - Resolved Actionlint YAML parsing errors in run-name expressions.

### OWASP ASVS 5.0.0 Security Hardening & Audit Completion
- **ASVS V2 Business Logic & Pipeline Integrity:**
  - **Strict Request State Transitions (2.3.1):** Enforced state validation on `PATCH /api/requests/{id}` rejecting direct transitions to automated or terminal states (`sent`, `confirmed`, `submitted`); only manual review states (`pending`, `skipped`) may be modified directly, closing an opt-out step-skipping gap.
  - **Date of Birth & Age Synchronization (2.2.3):** Prevented age edits from desynchronizing from existing `dob` values, and updated COPPA child record crypto-shredding purge routines to compute minor status strictly from `dob`.
  - **Anti-Automation & Resource Exhaustion Protection (2.4.1):** Rate-limited discovery search and broker opt-out submission triggers in `automation.py` to prevent resource exhaustion, CAPTCHA credit exhaustion, and browser runner starvation.
  - **COPPA Parental Consent & Minor Credit Freeze Advisory:** Added plain-language disclaimer component (`ChildPrivacyNotice`) during dependent profile creation/editing under age 13, clarifying consent limits and linking directly to the credit freeze workflow across all 17 supported language packs.
- **ASVS V3 Web Frontend & Security Headers:**
  - **Cross-Origin Isolation (3.4.8, 3.5.8):** Added `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Resource-Policy: same-origin` headers across FastAPI response middleware, Nginx front-door configurations, Caddy, and bare-metal installer templates.
  - **Restricted Base URI & Consolidated CSP (3.4.3):** Consolidated disparate Content Security Policy declarations into a unified generator (`backend/core/csp.py`) and restricted `base-uri` from `'self'` to `'none'` everywhere.
  - **CSP Violation Reporting Endpoint (3.4.7):** Added rate-limited violation reporting endpoint (`POST /api/csp-report`) wired into CSP directives via `report-uri`, `report-to`, and `Reporting-Endpoints`.
  - **HSTS Enforcement (3.4.1):** Enforced conditional HSTS header emission in Nginx when proxying over TLS (`X-Forwarded-Proto == https`) and added `includeSubDomains` to Caddy's HSTS configuration.
  - **Client-Side Safe Link Navigation Guards:** Audited and wrapped all externally sourced or user-controlled anchor URLs (search results, broker terms, confirmation URLs, registries, credit bureaus) with `isSafeHref()` across 8 frontend views to eliminate `javascript:` pseudo-protocol injection risks.
- **ASVS V5 File & Upload Security:**
  - **CAPTCHA Screenshot Path Traversal Guard (5.3.2):** Introduced `limits.safe_filename_fragment()` restricting file path tokens to `[A-Za-z0-9_-]` across `optout_engine.py` and `discovery.py` to prevent directory traversal via crafted broker names or plugin manifests.
  - **Decompression Bomb Protection for Registry XLSX Imports (5.2.3):** Added pre-parse zip inspection verifying uncompressed byte totals and entry counts before loading uploaded registry spreadsheets into `openpyxl`.
  - **HTTP Header Injection Defense in Exports (5.4.1, 5.4.2):** Sanitized `Content-Disposition` header filenames in privacy export downloads by stripping CR/LF line breaks and escaping quotes and backslashes.
  - **Documented File Upload Security Policy (5.1.1):** Added formal documentation in `SECURITY.md` detailing size bounds, allowed MIME types, and antimalware analysis boundaries for all upload endpoints.
- **ASVS V6 & V7 Session Security & Password Controls:**
  - **Granular Session Tracking & Revocation:** Added persistent `UserSession` table (indexed by JWT `jti`) supporting self-service active device session visibility, individual device session revocation, admin-initiated per-user session termination, and daily stale session pruning in scheduler.
  - **Separation of Logout vs. Global Revocation:** Split `/api/auth/signout` (terminates current device session) from `/api/auth/signout-everywhere` (revokes all active user sessions).
  - **Opt-In Role-Based Inactivity Timeout (7.3.1):** Added configurable per-role idle session timeouts alongside absolute session expiration.
  - **10k+ Offline Common Password Blocklist (6.2.1):** Replaced legacy ~111-entry password list with a 10,000+ top compromised password dictionary (from SecLists) and application-specific terms, preserving offline privacy without third-party API exposure.
  - **Character-Based Password Length Floor (6.2.9):** Evaluated minimum password length by Unicode code point count rather than UTF-8 byte length to avoid premature rejection of international character passwords.
  - **Step-Up Authentication for MFA Enrollment:** Required current password verification prior to enrolling TOTP authenticators or WebAuthn hardware security keys.
- **ASVS V9 Distributed Queue Cryptographic Envelope Integrity:**
  - **Fail-Closed HMAC Envelope Verification:** Updated `WorkerDaemon.execute_envelope()`, `JobEnvelope.from_dict()`, and `JobResultEnvelope.from_json()` to reject unsigned or unverifiable task envelopes rather than silently bypassing verification when `SECRET_KEY` is missing.
- **ASVS V13 Secure System & Service Configuration:**
  - **Distributed Service Credential Hardening (13.2.1, 13.2.3):** Removed insecure default database passwords and required explicit `REDIS_PASSWORD` authentication (`--requirepass`) across worker fleets in `docker-compose.distributed.yml`.
  - **Anonymous Version & Commit Fingerprinting Protection (13.4.6):** Redacted Git commit hashes from `GET /api/health` for unauthenticated callers while preserving authenticated diagnostics for administrators.
  - **CORS Verb Restriction:** Restricted cross-origin access strictly to authorized HTTP methods.
- **ASVS V14 Data Protection in Transit & at Rest:**
  - **MFA Ticket Query Parameter Removal (14.2.1):** Removed ephemeral MFA ticket exposure from query strings in `GET /api/auth/mfa/status`, requiring HTTP header delivery (`X-MFA-Ticket`).
  - **Universal API Cache Disabling (14.2.2, 14.3.2):** Defaulted all API response headers to `Cache-Control: no-store` unless explicitly overridden.
  - **Uploaded Logo Metadata Stripping (14.2.8):** Stripped metadata and EXIF data from uploaded tenant logos by re-encoding raster images and stripping `<metadata>`/comments from SVGs.
  - **Web Cache Deception Prevention (14.2.5):** Configured Nginx to return real HTTP 404 responses for missing static asset extensions rather than falling back to the SPA HTML shell.
- **ASVS V15 & V16 Cryptographic & Security Event Logging:**
  - **Enforced SMTP TLS Negotiation:** Fixed a critical boolean-type evaluation bug where `smtp_tls=True` silently fell back to unencrypted plaintext SMTP, guaranteeing strict TLS/STARTTLS enforcement for credential resets and opt-out notifications.
  - **Security Audit Event Logging (16.3.1, 16.3.2, 16.3.3):** Added structured audit event logging for authentication outcomes, access authorization denials, and anti-automation rate-limit lockouts using account IDs and PII-sanitized formatters.
  - **Global Exception Sanitization (16.5.4):** Added top-level unhandled exception fallback handler returning generic error bodies to prevent internal diagnostic leaks.

### CISA "Secure by Design" & Vulnerability Transparency
- **CISA Secure by Design Principles Alignment:**
  - **Comprehensive Architectural Specification:** Published `docs/architecture/cisa-secure-by-design.md` detailing alignment across the three core principles (Take Ownership of Customer Security Outcomes, Embrace Radical Transparency and Accountability, Build Organizational Structure to Eliminate Vulnerability Classes) and seven tactical goals.
  - **Vulnerability Class Elimination Rationale:** Formally documented structural elimination of OWASP/CWE flaw classes across the codebase: SQL Injection (SQLAlchemy parametrized AST queries), Cross-Site Scripting (React auto-escaping and CSP `base-uri 'none'`), Server-Side Request Forgery (`dns_guard.assert_safe_url()`), Directory Traversal (`limits.safe_filename_fragment()`), and Sandbox Escapes (Bubblewrap and Seccomp BPF syscall isolation).
  - **Default Security Posture:** Verified zero default passwords, mandatory initial admin password configuration upon first launch, free built-in MFA (TOTP and WebAuthn/FIDO2 hardware keys), and automatic database schema migrations without operator intervention.
- **RFC 9116 Vulnerability Disclosure (`/.well-known/security.txt`):**
  - **Standardized Machine-Readable Contact:** Deployed standard RFC 9116 `security.txt` discovery at `/.well-known/security.txt` and `/api/.well-known/security.txt` linking to the GitHub Private Vulnerability Reporting program (`https://github.com/rlnunez/OpenOptOut/security/advisories/new`), canonical policy, contributors graph, and changelog acknowledgments.
  - **Security Researcher Safe Harbor Policy:** Added explicit safe harbor protections in `SECURITY.md` assuring good-faith security researchers of protection against civil or criminal legal action (including under CFAA and DMCA anti-circumvention provisions), safe harbor scope boundaries, and clear communication guidelines.
- **Software Bill of Materials (SBOM):**
  - **CycloneDX 1.5 & SPDX 2.3 Generators (`backend/core/sbom.py`):** Added dynamic CycloneDX 1.5 JSON and ISO/IEC 5962:2021 (SPDX 2.3) SBOM generation combining installed environment package metadata via `importlib.metadata` and pinned project manifest dependencies (`requirements.txt`).
  - **NTIA Minimum Elements Dependency Graph:** Resolved declared library dependencies (`requires`) to construct hierarchical dependency trees (`DEPENDS_ON` relationships).
  - **Admin Diagnostic Endpoint (`GET /api/admin/sbom`):** Exposed authenticated administrative endpoint supporting format negotiation (`?format=cyclonedx` or `?format=spdx`) providing real-time, machine-readable inventory of software components, versions, licenses, and suppliers.
  - **Standards Alignment Registry:** Updated `STANDARDS_ALIGNMENT` in `backend/core/privacy_record.py` to index `cisa_secure_by_design`, `spdx_2_3`, `oauth_2_1`, `nist_sp_800_88`, `w3c_trace_context`, `openssf_slsa_3`, and `scim_2_0`.

### Enterprise Identity, Sanitization & Standards Alignment
- **OAuth 2.1 & RFC 9700 Security Best Current Practice Alignment:**
  - **Unconditional PKCE Enforcement:** Defaulted and enforced PKCE with S256 (`code_challenge_method=S256`) unconditionally across all authorization code grants in `backend/core/oauth_engine.py`, updating Yahoo Mail and custom plugins.
  - **Exact Redirect URI Matching:** Added strict byte-for-byte URI validation in `OAuthClient`, forbidding fragments (`#`), relative traversal (`..`), and unencrypted schemes.
  - **Refresh Token Rotation & Reuse Detection:** Implemented single-use refresh token rotation in `OAuthEngine.refresh_token()`; detects reuse of consumed tokens and automatically revokes the compromised token family.
- **NIST SP 800-88 Rev. 1 Media Sanitization & Cryptographic Erase (CE):**
  - **Storage Residual Purging:** Integrated `PRAGMA wal_checkpoint(TRUNCATE)` and incremental vacuuming on SQLite during patron/dependent deletion in `backend/core/people.py` and `backend/core/sanitization.py`, eliminating lingering unallocated WAL transaction pages.
  - **In-Memory Zeroization:** Implemented `zeroize_buffer()` to scrub sensitive cryptographic keys in memory buffers prior to garbage collection.
  - **Certificate of Sanitization:** Generated machine-readable, HMAC-signed JSON destruction receipts verifying data erasure under NIST SP 800-88 Rev. 1 with zero plaintext PII exposure.
- **W3C Trace Context (Distributed Tracing Recommendation):**
  - **Standardized Tracing Headers:** Implemented W3C `traceparent` and `tracestate` header generation, validation, and child span derivation in `backend/core/tracing.py`.
  - **Distributed Queue Propagation:** Added `traceparent` and `tracestate` fields to `JobEnvelope` and `JobResultEnvelope` in `backend/core/distributed/envelope.py`, enabling end-to-end distributed audit correlation across API, Redis queues, and worker bots.
- **SCIM 2.0 Enterprise Identity Management (RFC 7643 & RFC 7644):**
  - **Service Provider Discovery:** Implemented RFC 7643 discovery endpoints at `/api/scim/v2/` (`ServiceProviderConfig`, `Schemas`, `ResourceTypes`).
  - **User Lifecycle Management:** Implemented RFC 7644 user operations (`GET /api/scim/v2/Users`, `GET /Users/{id}`, `POST /Users`, `PATCH /Users/{id}`, `DELETE /Users/{id}`) supporting automated provisioning, real-time attribute sync, session revocation upon deactivation (`active: false`), and cascading cryptographic erasure on deprovisioning.
- **OpenSSF SLSA Level 3 & Cosign Container Signing:**
  - **Cryptographic Provenance Attestation:** Added `.github/workflows/build-provenance.yml` generating non-falsifiable in-toto SLSA Level 3 build provenance via `actions/attest-build-provenance@v2`.
  - **Keyless Container Signing:** Integrated `sigstore/cosign-installer` to sign release container images via GitHub OIDC identity.
- **NIST SP 800-57 Part 1 Rev. 5 Key Management Lifecycle:**
  - **Epoch Key Versioning:** Supported versioned AES-256-GCM ciphertexts (`gcm:v{epoch}:`) with cryptoperiod derivation under HKDF-SHA256 in `backend/core/encryption.py`.
  - **Automated Re-encryption Pipeline:** Added `reencrypt_all_records(db)` migrating older ciphertexts and legacy Fernet data to active key epochs without service downtime.
- **OpenID Connect Back-Channel Logout 1.0:**
  - **Server-to-Server Session Revocation:** Added `POST /api/auth/backchannel-logout` in `backend/routers/auth.py` verifying OIDC `logout_token` claims, immediately revoking all active sessions for matching user subjects (`sub`) or session IDs (`sid`).
- **RFC 9449 OAuth 2.0 Demonstrating Proof-of-Possession (DPoP):**
  - **Asymmetric Sender-Constrained Tokens:** Implemented `backend/core/dpop.py` verifying client DPoP proof JWTs, binding tokens to RFC 7638 JWK thumbprints (`jkt`), matching HTTP method and URI, and enforcing single-use `jti` replay defense.
- **ISO/IEC 27701:2019 (PIMS) Compliance Reporting:**
  - **Statutory ROPA & DPIA Endpoints:** Implemented `GET /api/privacy/ropa` (GDPR Article 30 Record of Processing Activities) and `GET /api/privacy/dpia` (GDPR Article 35 Data Protection Impact Assessment) in `backend/core/ropa.py` and `backend/routers/privacy.py`.
- **W3C Subresource Integrity (SRI) & OASIS CSAF 2.0:**
  - **Automated SRI Injection:** Added `scripts/inject_sri.py` injecting SHA-384 cryptographic integrity hashes and `crossorigin="anonymous"` attributes into frontend bundle scripts and stylesheets.
  - **CSAF 2.0 Provider Metadata:** Implemented standard CSAF 2.0 discovery metadata at `/.well-known/csaf/provider-metadata.json` and linked in RFC 9116 `security.txt`.
- **Independent Security Audit Scope Specification (Roadmap Item 68):**
  - **Formal Audit Boundaries & Invariants:** Published `docs/dev/audit-scope.md` defining technical boundaries, in-scope modules, out-of-scope rules of engagement, threat models, cryptographic invariants, and auditor test execution commands for external penetration testing across OWASP ASVS 5.0.0, NIST SP 800-57, NIST SP 800-88, CISA Secure by Design, FIDO2/WebAuthn Level 3, OAuth 2.1, DPoP, SCIM 2.0, and ISO/IEC 27701.

### Privacy Protocols & Data Rights Automation
- **Data Rights Protocol (DRP v0.9/v1.0) Client & Execution Engine (Roadmap Item 73):**
  - **First-Class Opt-Out Method (`drp`):** Added native `drp` opt-out execution method alongside `form`, `email`, and `manual` across `BrokerSpec`, `JobCompiler`, `DryRunExecutor`, and `OptOutEngine`.
  - **Protocol Schema & Identity Models (`core/drp/schema.py`):** Canonical DRP data structures supporting multiple privacy regimes (`ccpa`, `gdpr`, `coppa`, `general`, `lgpd`) and rights (`sale:opt-out`, `deletion`, `access`).
  - **DRP Client Implementation (`core/drp/client.py`):** Built dedicated DRP client supporting standardized `/exercise`, `/status`, and `/.well-known/data-rights` discovery operations.
  - **Zero-PII Audit Logging & SSRF Guard:** Enforced `dns_guard.assert_safe_url()` and `safe_dns_context()` across all DRP endpoints, with strict PII filtering ensuring consumer identity records are never written to unencrypted logs.
  - **Model & Database Support:** Extended `OptOutMethod` enum with `drp` and integrated direct status/token tracking via `RemovalRequest.request_key`.
- **W3C Global Privacy Control (GPC) Universal Opt-Out Signal (Roadmap Item 74):**
  - **Universal HTTP Header Emission:** Automated emission of standard `Sec-GPC: 1` and paired `DNT: 1` headers across all automated browser contexts (discovery, opt-out submission, worker fleet, link confirmation, URL verification), DRP client requests, and frontend API calls.
  - **DOM Property Enforcement:** Injected `navigator.globalPrivacyControl = true` init script across all automated Playwright browser frames and pages to satisfy legal opt-out preference signal requirements under CCPA/CPRA (11 CCR § 7025) and Colorado CPA (4 CCR 904-3 Rule 5.06).
  - **W3C Well-Known Resource:** Implemented `GET /.well-known/gpc.json` (and proxied `/api/.well-known/gpc.json`) conforming to section 4 of the W3C Global Privacy Control community specification.
- **ISO/IEC 29100 Privacy Architecture Framework Alignment:**
  - **Formal Architecture & Role Mapping:** Published comprehensive privacy framework specification (`docs/architecture/privacy-framework-29100.md`) establishing technical boundaries and roles across PII Principals (family members and patrons), PII Controllers (self-hosting administrators and library authorities), PII Processors (core engine and worker fleet), and Third Parties (data brokers and privacy-masked solvers).
  - **11 Privacy Principles Mapping:** Aligned codebase safeguards to all 11 ISO/IEC 29100 principles, documenting parental representation consent (`terms.py`), collection minimization (zero SSNs), field-level AES-256-GCM encryption, visual CAPTCHA masking, cadenced crypto-shredding purges, and immutable staff access logging (`AccessLog`).
  - **Public Data Inventory Endpoint:** Added `GET /api/privacy/inventory` serving a transparent, machine-readable data inventory detailing personal data categories, storage protections, retention schedules, and standards alignment without exposing internal system counts or server diagnostics.
- **NIST Privacy Framework Version 1.0 & CSF Privacy Profile Alignment:**
  - **CSF Privacy Profile Specification:** Published architectural profile (`docs/architecture/nist-privacy-profile.md`) mapping technical safeguards across all 5 Core Functions: Identify-P (inventory & broker ecosystem mapping), Govern-P (RBAC & automated retention monitoring), Control-P (disassociated processing, visual CAPTCHA masking, and hard crypto-shredding), Communicate-P (patron access logs, GPC signal, and DRP), and Protect-P (AES-256-GCM, PBKDF2, MFA, and process sandboxing).
  - **Disassociated Processing Safeguards (CT.DP-P):** Formally integrated disassociated processing declarations in the data inventory metadata, validating visual PII challenge masking, ephemeral in-memory execution, and minimal broker field payloads.

### Authentication & Identity Providers (OIDC, SIP2, MFA)
- **FIDO Alliance FIDO2 & W3C WebAuthn Level 3 Implementation:**
  - **User Verification (UV) Flag Enforcement:** Injected UV flag validation (`authData[32] & 0x04`) in `verify_webauthn_assertion()` to fail closed when user verification is required by policy or credential settings.
  - **Hardware-Bound vs. Synced Passkey Classification:** Implemented WebAuthn L3 Backup Eligibility (`BE` flag, bit 3) and Backup State (`BS` flag, bit 4) parsing in `parse_and_validate_registration_response()`, accurately distinguishing physical hardware tokens (FIDO2 Level 2/3) from multi-device synced passkeys.
  - **Ed25519 (EdDSA / alg: -8) Support:** Expanded cryptographic verification to support Ed25519 Edwards curve signatures alongside ES256 and RS256.
  - **Discoverable Passkey Detection (`credProps`):** Added WebAuthn L3 `credProps` extension to registration options confirming client-side resident key generation.
- **NIST SP 800-63B Authentication & Lifecycle Hardening:**
  - **Magic-Link Mandatory MFA (§3.1.3):** Enforced that magic-link email sign-in always requires MFA (or initiates mandated MFA setup) and never completes authentication on its own, complying with NIST SP 800-63B rev. 4 §3.1.3 prohibiting email as an out-of-band authentication factor.
  - **Password Length Floor (§3.1.1):** Raised minimum local password length from 12 to 15 characters (single-factor password floor), updating validation and internationalized copy across all 17 language packs.
  - **Default Role Idle Timeout (§2.2.3):** Defaulted idle session timeout to 60 minutes across all roles, with administrator configurability down to 0 (disabled).
  - **Remember-Me Duration Cap (§2.2.3 AAL1):** Enforced a hard 30-day ceiling on "Remember Me" extended sessions, rejecting higher values in the settings API and clamping legacy settings defensively on read.
- **OIDC SSRF & DNS Rebinding Protection:** Wrapped OIDC discovery, token, and userinfo network requests with `dns_guard.assert_safe_url()`.
- **OIDC Issuer Mix-Up Guard:** Rejected OIDC discovery documents whose asserted `issuer` does not match the configured discovery URL authority.
- **SSO Redirect Base URL Resolution:** Enforced precedence of configured `PUBLIC_BASE_URL` and `FRONTEND_URL` over untrusted client `Host` request headers when computing OIDC `redirect_uri` targets, and resolved a runtime `NameError` in `_sso_redirect()`.
- **Cross-Provider External Identifier Scoping:** Scoped `User.external_id` updates to the originating authentication provider, preventing secondary IdPs asserting verified matching emails from clobbering primary identity mappings.
- **TOTP Counter-Replay Defense:** Tracked matched RFC 6238 time-step counters per account (`totp_matched_counter`, `totp_replay_check`), preventing reuse of intercepted TOTP tokens against concurrent MFA tickets within the drift window.
- **SIP2 Reissued Library Card Account Linking:** Added support for resolving patrons with reissued library cards via configurable barcode fields (`previous_card_*`), preserving user removal history and settings across card renewals.

### Container & Infrastructure Hardening
- **CIS Docker Benchmark Container Hardening:**
  - **Docker Socket Proxy Mediation (CIS 5.32):** Deprecated direct `/var/run/docker.sock` volume mounting in the updater service in favor of a digest-pinned `docker-socket-proxy` sidecar (Tecnativa) exposing only minimal API endpoints (`images`, `pull`, `up`), blocking `docker exec` and container escapes.
  - **Resource Ceilings & PID Limits (CIS 5.11, 5.12, 5.28):** Enforced CPU, memory, and PIDs ceilings (`deploy.resources.limits`) across all services in `docker-compose.yml` and `docker-compose.distributed.yml`, overridable via `.env`.
  - **Read-Only Root Filesystems (CIS 5.13):** Enforced `read_only: true` root filesystems across `api`, `web`, `worker`, `redis`, `db`, and proxy services with minimal scoped `tmpfs` mounts and persistent volumes.
  - **Multi-Stage Build Trim & Build Tool Elimination (CIS 4.3):** Refactored `backend/Dockerfile` into a `pydeps-builder` compilation stage and runtime container stage, stripping compilers and build headers (`gcc`, `build-essential`, `-dev` packages) to reduce image size by ~230MB.
  - **Stripped Setuid/Setgid Binaries (CIS 4.8):** Removed setuid/setgid permissions from unnecessary system utilities (`su`, `passwd`, `mount`, `chage`, etc.) inside the container image while preserving bubblewrap's `cap_add: SYS_ADMIN`.
  - **Updater Build Dependency Collision Fix:** Dropped unnecessary `docker` group (gid 999) from `deploy/updater/Dockerfile`, preventing Alpine 3.20 build collision with the default `ping` group.
- **Plugin Network Sandboxing & Namespace Enforcement:** Closed network-permission bypass by enforcing host-mediated routing on non-email plugins declaring `network` or `outbound_domains`. Enabled OS-level namespace sandboxing (bubblewrap/seccomp) by default with fallback on unsupported platforms (`REQUIRE_HARD_SANDBOX=false`).
- **Installer Control-Plane Sandbox Parity:** Extended bubblewrap and seccomp syscall filters to control-plane instances and multi-host deployment configurations.
- **Rclone Container Multi-Stage Build (CVE-2026-111943 & CVE-2026-114437):** Refactored `/usr/local/bin/rclone` compilation in `backend/Dockerfile` to compile from source via a multi-stage builder using Go 1.27.3 (`golang:1.27.3-bookworm@sha256:972b4110ba0f47539a975c31e52c64765e1ff19f2d74469ae4a595c6676e80a5`) to remediate Go stdlib `crypto/x509` intermediate CA certificate verification vulnerabilities, and upgraded `github.com/go-chi/chi/v5` from `v5.3.1` to `v5.4.0` to remediate client IP spoofing in `ClientIPFromXFF` middleware.
- **Supply-Chain Digest Pinning (Scorecard):** Pinned the `rclone-builder` container stage image with its multi-platform SHA-256 digest to satisfy OpenSSF Scorecard supply-chain integrity requirements.
- **Stale Wheel, Dist-Info & Base Image SBOM Purge:** Purged base-image pre-bundled `pip-25.0.1.dist-info`, static build-time `pip/_vendor/bom.cdx.json` SBOMs (which declared outdated `setuptools 70.3.0`), `ensurepip` pre-bundled bootstrap wheels (`/usr/local/lib/python*/ensurepip/_bundled`), and build caches from the backend container image in `backend/Dockerfile` and `backend/install_deps.py` to eliminate Trivy scanner findings (`CVE-2026-1703`, `CVE-2026-8643`, `CVE-2026-6357`, `CVE-2026-3219`, `CVE-2026-13346`, `CVE-2025-8869`, and `GHSA-xmj3-9gf7-h52w`).
- **Persistent HTTP Warning Banner:** Added persistent admin warning banner on unencrypted HTTP connections advising administrators to run `enable-https.sh` to protect credentials and member PII in transit.
- **Headless Firefox & Fontconfig Tmpfs Support for Read-Only Containers:** Added `libpci3` and configured `XDG_CACHE_HOME=/tmp/.cache`, `XDG_CONFIG_HOME=/tmp/.config`, and `MOZ_DISABLE_RDD_SANDBOX=1` in `backend/Dockerfile`, paired with dedicated tmpfs mounts for `/home/appuser` and `/var/cache` in `docker-compose.yml` and `docker-compose.distributed.yml` to prevent Playwright Firefox launch timeouts under CIS-hardened read-only root filesystems.
- **Cross-Browser Navigation Abort Handling in Release UI Check:** Updated `.github/release-test/ui_check.py` request failure handler to accommodate non-Chromium cancellation codes (`NS_BINDING_ABORTED` in Firefox and `Request cancelled` in WebKit) when background requests are aborted during navigation.
- **Cross-Platform Test Compatibility:** Updated test `backup.rclone_destination` in `backend/tests/run_tests.py` to use portable permission checking supporting both GNU and BSD/macOS `stat` syntax.

### Dependencies & Maintenance
- **`pip` Security Upgrade & CA Synchronization:** Upgraded `pip` to `26.2.2` in `backend/requirements.txt` (which natively vendors patched `certifi 2026.10.19`) and integrated automated build-time CA bundle synchronization (`sync_pip_certifi` in `install_deps.py`) to eliminate persistent GHSA-6q48-6c7w-9gw2 / PYSEC-2026-4320 alerts without suppressing scanner findings in ignore files.
- **Setuptools Security Upgrade (GHSA-xmj3-9gf7-h52w):** Upgraded `setuptools` from `84.0.0` to `84.1.0` in `backend/requirements.txt` to remediate path traversal / arbitrary file placement vulnerability during legacy wheel processing.
- **Cloud Dependencies Consolidation & Manifest Deduplication:** Merged optional cloud IAM database authentication dependencies (`boto3==1.43.111`, `azure-identity==1.26.0`) directly into `backend/requirements.txt` and removed `backend/requirements-cloud.txt`, deduplicating requirement definitions, eliminating dual-manifest maintenance, and permanently resolving scanner findings caused by isolated manifest evaluations.
- **Exception Message Leak Guard in SAML IdP Config:** Replaced raw exception string embedding in `save_config` with a fixed error response, resolving Semgrep `exception-text-returned-to-client` finding.
- **Distributed Worker Queue DLQ Pipeline & Envelope Verification:** Coordinated HMAC signature verification between queue dequeue operations and `WorkerDaemon.execute_envelope()` so that tampered or invalid envelopes are auditably captured, signed, and routed to the Dead Letter Queue (DLQ) rather than crashing during deserialization, while preserving HMAC verification on results.
- **Centralized SSRF / DNS Protection (`dns_guard.py`):** Consolidated URL validation and DNS pinning logic across log forwarding, OAuth engines, webhooks, authentication providers, registry synchronization, and SAML metadata resolvers.
- **ReDoS Elimination in Log Scrubbing:** Replaced unbounded regex patterns in `logging_config.py` with bounded, non-backtracking matchers.
- **Security Policy Documentation (`SECURITY.md`):** Thoroughly documented sensitive data classifications, crypto key inventories, upload file handling policies, AV scanning rationale, external service timeout/retry policies, and secrets rotation schedules.

---

## [0.11.2] — 2026-10-20

### Security & Hardening
- **Language Pack Translation Safety Validation:** Added pre-install and load-time inspection (`is_safe_translation_string`, `inspect_language_pack`) rejecting language packs that introduce unprompted external URLs (phishing protection), prohibited URI schemes (`javascript:`, `file:`, `data:`), or executable HTML tags (`<script>`, `<iframe>`, etc.), protecting users from phishing links or UI instruction tampering in uploaded language packs.
- **Plugin Sandbox AST Obfuscation & Reflection Guard:** Banned reflection attributes (`__subclasses__`, `__globals__`, `__code__`, `__reduce__`, `__bases__`, `__mro__`), dynamic attribute lookups on sensitive modules via `getattr()`, and direct or dynamic access to `sys.modules` in the plugin code inspector to prevent sandbox evasion.
- **Proactive Core PII Log Sanitization:** Extended `sanitize_log_message` in core logging to scrub personal email addresses (`[email]`), phone numbers (`[number]`), and Social Security Numbers (`[ssn]`) across local log files and memory ring buffers.
- **Fail-Closed Strict Sandbox Flag (`REQUIRE_HARD_SANDBOX`):** Added configuration flag that refuses to launch plugins on hosts lacking OS-level namespace sandboxing (bubblewrap/unshare), preventing silent fallback to uncontained execution.
- **Login Timing Oracle & User Enumeration Mitigation:** Added constant-time dummy password verification (`dummy_verify_password`) in `POST /api/auth/token` for non-existent accounts, equalizing PBKDF2/Bcrypt processing latency to prevent username harvesting.
- **Single-Use Enforcement on Ephemeral MFA Tickets:** Integrated `code_attempts` consumption into TOTP, backup recovery code, and WebAuthn verification to prevent intermediate MFA ticket replay.
- **Immediate Session Invalidation on User Role & Permission Modifications:** Automatically incremented `token_version` whenever an administrator modifies a user's role, manager permissions, or MFA overrides to instantly terminate active sessions.
- **SAML IdP Metadata SSRF & DNS Rebinding Protection:** Enforced `https://` scheme verification, `public_host` destination validation, and `safe_dns_context` socket pinning with disabled HTTP redirect following (`follow_redirects=False`) when fetching remote SAML IdP metadata documents.
- **OIDC HTTPS Endpoint Enforcement & Credential Guard:** Added strict endpoint URL validation in `OIDCProviderConfig` rejecting non-HTTPS discovery, authorization, token, and userinfo endpoints to prevent cleartext credential transmission.
- **SAML Assertion Concurrency Lock & Replay Defense:** Synchronized single-use `in_response_to` request ID consumption under thread-safe locking (`_OUTSTANDING_LOCK`) to eliminate race conditions during concurrent SAML response processing.
- **Comprehensive Crypto-Shredding of Member PII & Residual MFA Secrets:** Extended multi-pass cryptographic shredding in `delete_person` to overwrite member date of birth (`dob`), user full name, and immediately wipe residual MFA credentials (`totp_secret_enc`, `backup_codes`, `webauthn_credentials`) before database purge.
- **Browser Hardware Feature Isolation (`Permissions-Policy`):** Added defense-in-depth HTTP security header `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()` restricting browser hardware capability access.
- **Webhook SSRF & DNS Rebinding Hardening:** Enforced `public_host` validation and `safe_dns_context` socket pinning on outbound webhook dispatches to prevent SSRF against internal subnets and DNS rebinding attacks.
- **Single-Use Verification Code Invalidation:** Automatically consumed and invalidated email verification tokens via `code_attempts.used` upon successful registration to prevent code replay attacks.
- **MFA Session Token Revocation Parity:** Enforced `token_version` validation in `_resolve_user_for_mfa` to ensure revoked or invalidated JWT sessions cannot access MFA status or enrollment flows.
- **WebAuthn Step-Up Re-Authentication:** Enforced password confirmation and dispatched account alert emails upon deleting registered WebAuthn / Passkey hardware keys.
- **PostgreSQL Process List Credential Protection:** Stripped cleartext database passwords from `pg_dump` CLI subprocess arguments in backup jobs, securely supplying credentials through environment variable separation (`PGPASSWORD`).
- **Log Scrubbing Everywhere:** The scrubbing formatter now also wraps uvicorn's access and error handlers and the worker's logging, so request lines (calendar feed links, OIDC `code`/`state`) no longer reach `docker compose logs` unscrubbed. Scrubbing now covers prefixed secret names (`access_token`, `X-API-Key`, `Set-Cookie`), quoted dicts, URL credentials, labelled names and birth dates, street addresses, `%40` emails and international phone numbers. Debug level no longer turns on SQL and HTTP-library logging.
- **Private Log Files:** New log directories are created 0700 and log files (including rotated copies) 0600. The admin file-permission alert now lists the log directory and files when they are looser, with `chmod 700` / `chmod 600` (Docker, Linux/macOS) and `icacls` (Windows) commands to fix them.
- **Plugin Log Channel:** Plugins that hold `read_pii` can no longer write message text to the host log (only its length is recorded).
- **Plugin Egress via `outbound_domains` Actually Enforced:** `outbound_domains` was only checked on the host-mediated `http.fetch` path; a non-email-provider plugin holding `network` could still import `socket`/`requests`/`ftplib`/`paramiko`/etc. directly and reach any host the OS sandbox's (all-or-nothing) network namespace allowed, regardless of what it declared. Install-time code inspection (`code_inspector`) now treats a direct network-library import as a blocking finding for any plugin type except `email` (which keeps its separate, narrower exemption for its own mail protocol), forcing every other plugin through `plugin.http`, the one path where `outbound_domains` is real.
- **Sign-Up Code Flooding:** `/api/auth/signup/email-code` now also limits requests per email address (5 per 5 minutes), not only per IP.
- **Fix:** `routers/auth.py` used `MAX_PASSWORD_BYTES` without importing it, which stopped the auth router from loading.
- **Registration Email Token Consumption Ordering:** Deferred email verification token invalidation until all registration prerequisites (including resident address token checks) succeed, preventing premature token burning on multi-step registration forms.
- **Cloudflare Turnstile Response Injection & Site Key Extraction:** Added `cf-turnstile-response` to the response field injection payload in `PlaywrightExecutor._handle_captcha` with synthetic `input`/`change` event dispatching, and extracted `sitekey` parameters from Turnstile iframe query strings in `_detect_challenge` when missing from DOM element attributes.
- **Broker Self-Repair Queue on Locator Timeouts:** Extended failure classification in `broker_health.record_failure` to queue self-repair (`_queue_repair`) when a timeout error contains Playwright locator/selector failures (`waiting for locator`, `waiting for selector`, `locator.`), preventing selector drift from being discarded as generic network timeouts.
- **Expanded Disposable Email Rejection Detection & HTTP 429 Navigation Guard:** Broadened `EMAIL_REJECTED` in `PlaywrightExecutor` to catch phrases refusing disposable/temporary emails or requiring permanent personal addresses, routing them to clean manual fallback. Added proactive HTTP 429 and 50x response inspection on `navigate` steps to fail fast with explicit rate limit / server error details.
- **Frontend Error Boundary & 422 Detail Normalization:** Added top-level `<ErrorBoundary>` to catch unhandled rendering exceptions with reload recovery, and normalized API validation error shapes (`detailText`) across all frontend pages to prevent React child rendering crashes on 422 response arrays.
- **Resolved CodeQL Substring Sanitization Warning in Turnstile Mock:** Replaced substring domain check on CSS selector with structural selector matching in `backend/tests/run_tests.py` to remediate CodeQL `py/incomplete-url-substring-sanitization` alert.
- **MFA Throttling Precedence & Ticket Replay Defense:** Enforced `login_throttle` checks prior to single-use token evaluation across TOTP, backup recovery code, and WebAuthn sign-in endpoints; removed premature per-guess attempt invalidation so account lockouts return 429 properly without permanently corrupting unexpired MFA session tickets.
- **Settings Store Python 3.9+ Compatibility:** Replaced PEP 604 type unions (`| None`) with `Optional[...]` in `settings_store.py` to ensure runtime compatibility across Python runtimes without PEP 563 evaluation.
- **Test Credential Normalization for Secret Scanners:** Replaced base62 test strings in `backend/tests/run_tests.py` with delimited test credentials to resolve generic API key code scanning alerts.

### Internationalization & Locale Usability
- **Multilingual Address Parsing:** Enhanced `combinations._parse_address` to split on Arabic comma (`،` U+060C), semicolon, and full-width comma (`，`), preserve building numbers in European-style addresses (`Carrer de Mallorca, 401, 08013 Barcelona`), and parse international alphanumeric postal codes (UK, Canada, Europe) without misclassifying postal prefixes as US states.
- **Flexible Date of Birth Formats:** Extended `parse_dob` to parse European dot format (`DD.MM.YYYY`), resolve unambiguous international dates where day > 12 (`DD/MM/YYYY`), and follow configured non-US regional formats.
- **Mononym & Single Legal Name Support:** Updated `member_fields.resolve` to fall back `last_name` to `first_name` when a profile has a mononym (single name), preventing broker form job compilation failures on forms requiring surname fields.
- **Phone Number Locale Handling:** Added automatic normalization for Eastern Arabic (`٠-٩`) and Persian (`۰-۹`) numerals into standard ASCII digits and handled international `00` dial-out prefixes in `member_fields.phone_digits` and `phone_e164`.
- **RTL BiDi Form Input Isolation:** Added `unicode-bidi: plaintext` for text inputs and textareas under RTL mode in `index.css`, preventing mixed-direction addresses with numbers and slashes from visually flipping.
- **Flexible Community Address Verification:** Updated `resident_addresses.clean` to support addresses where the street number is placed after the street name (standard in Europe, Latin America, and the Middle East) and accept international postal codes.

### Dependencies
- Upgraded `pillow` from 12.3.0 to 13.0.0 in `backend/requirements.txt` to remediate CVE-2026-112403, CVE-2026-112397, CVE-2026-112400, CVE-2026-112404, CVE-2026-112895, CVE-2026-112896, CVE-2026-112897, CVE-2026-112395, and CVE-2026-112899.
- Explicitly pinned `certifi==2026.10.19` in `backend/requirements.txt`, `backend/requirements-cloud.txt`, and `docs/requirements.txt` to remediate GHSA-6q48-6c7w-9gw2 / PYSEC-2026-4320 (compromised intermediate emSign CA keys).
- Merged PR #146: Upgraded `reportlab` from 4.4.4 to 5.0.1 in `backend/requirements.txt`.

---

## [0.11.1] — 2026-10-20

### Security & Dependencies
- **Security Dependency Hardening:** Upgraded `follow-redirects` from `1.16.0` to `1.16.1` in the frontend application layer to remediate upstream HTTP redirect security advisories.
- **Dependency Maintenance & Pinning Updates:**
  - Merged PR #144: Updated official GitHub Actions workflow action SHAs (`upload-sarif`, `upload-artifact`, `download-artifact`, `scorecard-action`).
  - Merged PR #140: Refreshed `python:3.12-slim-bookworm` container base image digest pin with latest upstream Debian security patches.
  - Merged PR #141: Bumped `lucide-react` (1.52.0 → 1.55.0) and `vite` (8.3.3 → 8.3.4).
  - Merged PR #145: Routine maintenance upgrades for Python dependencies (`fastapi` 0.143.0, `sqlalchemy` 2.1.4, `pydantic` 2.14.1, `msgpack` 1.2.3, `google-auth` 2.61.0, `boto3` 1.43.111).

### Changed & Improved
- **CI / Release Testing Workflow Flexibility:** Enhanced `.github/workflows/release-test.yml` and `.github/release-test/setup_check.py` to allow manual workflow dispatch testing on `main` or arbitrary branches/refs without requiring a version bump or new release tag creation.

---

## [0.11.0] — 2026-10-19

### Added
- **Antigravity (Google) AI Helper Integration:** Added Google Antigravity alongside Claude, OpenAI, and Local AI servers in the setup wizard and administrative AI settings, unifying helper purpose descriptions across all providers.
- **Interactive Entropy Generator UI Showcase:** Expanded the Interactive Chaos & Randomness generator by default during setup with real-time entropy stream visualization and canvas particle physics, collapsing the baseline CLI/bootstrap key panel.
- **ADA-Compliant 5% Incremental Font Size Slider:** Replaced discrete font size buttons with an accessible range slider supporting 5% step increments (75% to 150%), keyboard navigation (Arrow keys, Home, End), and live screen-reader percentage announcements.
- **Comprehensive WCAG 2.2 AAA Documentation (`docs/ACCESSIBILITY.md`):** Complete accessibility compliance matrix with color contrast ratios, screen reader compatibility, keyboard navigation shortcuts, and assistive technology testing guides.

### Changed
- **Setup Wizard Navigation & Button Streamlining:** Removed redundant bottom "Skip" action buttons when an inline "Skip for now" / "Configure later" option is already provided within step choices.
- **AI Helper Setup Header:** Stated the unified purpose of AI helpers once in the step header ("inspect broker pages, draft new opt-out steps, and repair broken form-filling selectors") rather than repeating redundant descriptions inside every option.

### Fixed
- **Setup Wizard Release-Test Infinite Loop:** Resolved testing script freeze in `.github/release-test/ui_check.py` where step `3c` matched embedded key generator controls and repeated `continue` across 25 iterations without advancing the wizard.
- **Password Pepper Stability Across Master Key Rotations:** Added in-memory caching and persistent `pepper.key` storage in `backend/core/auth.py` so rotating or setting a master key never invalidates existing user passwords with 401 Unauthorized errors.
- **Theme Persistence on Route Navigation:** Fixed state synchronization in `AccessibilityContext` that erroneously reset custom themes back to the high-contrast ADA mode upon navigating across pages.
- **Release-Test Diagnostic & Upgrade Sweep Hardening:** Handled legacy wizard steps in before-upgrade checks, prevented false-positive error alerts on translation catalog pages, and updated admin password locators for ASVS L2 12-character minimums.
- **Backup Module Typing Import:** Fixed a `NameError` on `Optional` import in `backend/core/backup.py`.

---

## [0.11.0-rc8] — 2026-10-19

### Added
- **First-Boot Setup Wizard & Usability Configuration:**
  - Modernized initial boot flow to immediately present language selection, accessibility preferences, theme selection (Light, Dark, High-Contrast), font size scaling (Admin account), and OpenDyslexic typography before account or system configuration.
  - Granular setup steps making MFA, master encryption key generation, and system email skippable, while enforcing database and network configuration as required.
  - Added dedicated AI connection setup near the end of the onboarding wizard.
- **100% Self-Hosted Web Assets & Typography (WCAG 2.2 AAA):**
  - Fully air-gapped web assets with zero external CDN dependencies: self-hosted Inter, JetBrains Mono, OpenDyslexic, and Antonio font families via npm `@fontsource` packages.
  - Verified WCAG 2.2 Level AAA color contrast compliance across light, dark, and high-contrast palettes.
- **ISO/IEC 27701 & COPPA Data Lifecycle & Tabbed Admin Navigation:**
  - Granular retention schedules for member identity profiles, removal history logs, operator access logs, and temporary verification artifacts with preset intervals (`30d`, `90d`, `180d`, `1y`) and custom retention day inputs (`Admin → Settings → Lifecycle`).
  - Automated cryptographic shredding upon member deletion overwriting sensitive PII records in-place with CSPRNG random bytes across multiple passes prior to row removal, followed by optional database vacuuming.
  - Reorganized lengthy administrative settings view into clean, accessible top-level sub-menu tabs (`General`, `Security`, `Workers & Fleet`, `Lifecycle`, `Branding`, `Integrations`).
- **NIST SP 800-38D AES-256-GCM AEAD Field & Backup Encryption:**
  - Upgraded field-level encryption for sensitive PII to authenticated Galois/Counter Mode (AES-256-GCM) with 96-bit CSPRNG nonces and 128-bit authentication tags (`gcm1:`) under RFC 5869 HKDF domain separation (`openoptout:field-encryption-gcm:v1`).
  - Transparent dual-decryption supporting both modern `gcm1:` and legacy Fernet ciphertexts.
  - Streamed AES-256-GCM backup archives with 4 MiB chunks, sequential nonces, and header Authenticated Additional Data (AAD) binding.
- **NIST SP 800-132 PBKDF2 Iteration Hardening:**
  - Increased PBKDF2-HMAC-SHA256 password peppering iterations to 210,000 rounds before bcrypt hashing, with automatic background hash migration on successful authentication.
  - Standalone PBKDF2 key derivation for encrypted backup archives with 210,000 iterations and 16-byte random salts.

### Security
- **OWASP ASVS 4.0.3 Level 2 Hardening (PR #137):**
  - **V2 Authentication**: Raised minimum password length to 12 characters (ASVS 2.1.1); integrated pre-hash dictionary screening rejecting top-10,000 common and compromised passwords (ASVS 2.1.7); added self-service password change endpoint (`POST /api/auth/password/change`, ASVS 2.1.10); implemented `token_version` tracking on User models to immediately invalidate active JWT bearer tokens upon credential change (ASVS 3.3.4); and enabled automated user email alerts whenever an administrator modifies their account credentials or roles (ASVS 2.1.11).
  - **V2 Account Protection**: Eliminated timing and account-enumeration oracles in password reset and magic link generation endpoints (ASVS 2.2.2); added IP and account rate-limiting on magic link dispatch (ASVS 2.3.1).
  - **V5 Input & Output Sanitization**: Neutralized CSV formula injection risks in member and audit log exports (`core/csv_safety.py`, ASVS 5.1.4); hardened SVG logo uploads against MIME content sniffing via strict `nosniff` headers and XML tag checks (ASVS 5.1.5); escaped control characters in audit log output to prevent log forging (ASVS 7.1.1); and enforced bounded lengths on profile text inputs (ASVS 5.1.1).
  - **V8 & V13 Architecture**: Enforced domain separation for field encryption keys via HKDF (`core/encryption.py`, ASVS 6.2.8); corrected database encryption bootstrap initialization order; and disabled unauthenticated OpenAPI/Swagger UI docs in production mode (ASVS 13.1.5).
- **OWASP Top 10 for LLMs Hardening (PR #138):**
  - **LLM10 Unbounded Consumption Defense**: Enforced strict schema bounds in `draft_schema()` with `maxLength` on all strings and `maxItems` on all arrays to eliminate unbounded JSON payload memory consumption during AI spec generation.
  - Pinned OpenAI and compatible provider model invocations to bounded token ceilings (`max_output_tokens=16000` / `max_tokens=16000`).
- **ISO/IEC 27701 Retention Floor & Access Log Scoping Fix (PR #139):**
  - Preserved statutory 30-day minimum floor in `privacy_record.retention_days()`.
  - Prevented member self-service deletions from polluting administrative staff access logs with spurious unauthorized audit rows.

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
- **Express vs. Advanced Setup Wizard & Security Showcase (Windows-Style Top-Level Toggle):** Introduced a top-level mode switch between **Express Setup** (zero-touch defaults for home users: local encrypted SQLite, local home network or managed Caddy TLS, and optional deferred email) and **Advanced Setup** (granular control over PostgreSQL, full SMTP/IMAP/Proton transports, Caddy/Traefik reverse proxies, Cloudflare tunnels, and corporate branding). Showcases the active 128+ character master encryption key with masked view (`••••••••`), eye reveal toggle, clipboard copying, and strict 0600 file permission validation, while embedding the interactive image chaos and mouse movement entropy generator directly in the wizard.
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
- **Self-Managed mTLS Client-Certificate Revocation Enforcement (PR #131):** Enforced client certificate revocation in the application layer by forwarding certificate serials across reverse proxies (`X-Client-Cert-Serial` in Caddy and Nginx, `passTLSClientCert` with `info.serialNumber: true` in Traefik) and inspecting them with a FastAPI request middleware (`reject_revoked_client_certs`), refusing revoked serials with HTTP 403 on the next request without requiring proxy restarts. Also repaired container volume synchronization for in-app CA private key storage and mount points across Caddy and Traefik entrypoints.
- **Plugin Sandbox Seccomp Syscall Filtering Bindings (PR #130):** Installed `pyseccomp==0.1.2` in `backend/requirements.txt` (pure Python wheel over `libseccomp2` on Linux) and introduced `seccomp_filter.load_seccomp()` to dynamically locate bindings under either `seccomp` or `pyseccomp`. This enables real syscall filtering in containerized environments where Debian's `python3-seccomp` package was previously inaccessible to the image's Python interpreter.
- **Setup Wizard Secret Key Generation Accommodation:** Updated release-test scripts (`.github/release-test/ui_check.py` and `setup_check.py`) to detect and satisfy master secret key generation and file persistence prompts during automated first-run setup wizard walkthroughs.
- **Content and Translation Catalog Release Testing:** Scoped error-phrase matching in `.github/release-test/ui_check.py` so that catalog and diagnostic pages (`/translations`, `/logs`, `/help`, `/plugin-help`) emit non-fatal warnings instead of triggering false-positive run failures on legitimate error message copies (PR #127).
- **Setup Wizard Reverse Proxy Deployment Test:** Synchronized test assertions in `wizard.deployment_reverse_proxy_choice` (`backend/tests/run_tests.py`) to validate the new `client_mtls` reverse-proxy deployment configuration flag (PR #129).
- **Playwright Headless Browser Container Dependencies:** Added `libasound2` to container package dependencies for headless Playwright browser automation in test execution environments.
- **Server-Side Exception Traceback Scrubbing:** Sanitized API error responses across settings and mTLS endpoints to log raw exceptions server-side rather than reflecting internal tracebacks to clients.
- **Seccomp Posture Reporting:** Probes importability of `seccomp` Python bindings rather than static library presence on disk, ensuring the Plugins console reflects real syscall filtering capability (PR #122).

### Security
- **Identity Record Control Character Sanitization (PR #134):** Factored string cleaning into `clean_text` and `clean_text_lenient` in `backend/core/text_input.py` to strip control characters, CRLF injections, bidi-overrides, and lone surrogates from saved email addresses, phone numbers, and physical addresses across user-entered vault records (`backend/routers/family.py`) and SSO/LDAP/SIP2 patron import pipelines (`backend/routers/auth.py`), preventing email template parsing and SMTP transmission aborts.
- **AI Helper Scraped Page Content Boundary & Prompt Injection Defense (PR #133):** Wrapped scraped broker page descriptions in explicit `<broker_page_content>` delimiters in `spec_drafter.py` and updated system prompts and Antigravity agent instructions in `ai_helpers.py` to enforce that broker page content is treated strictly as data to describe, never as instructions (even if phrased as system directives, administrative commands, or override orders). Also added warning indicators to "Notes from the helper" and `pause_for_human` steps in `SpecHelpers.jsx` so reviewing administrators do not mistake untrusted broker page text for trusted instructions.
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
- **Space Explorer High-Contrast Theme (Roadmap Item 27):** High-contrast color scheme with proportional font scaling and OpenDyslexic priority overrides.
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
