# ISO/IEC 27001:2022 ISMS Architecture & Statement of Applicability (SoA)
## Information Security Management System (ISMS) Implementation

Status: **Architecturally Aligned & Verified (v0.11.3)**  
Scope: **Core Application, Multi-Tenant Workloads, Cryptographic Keyring, Release Pipeline, and Add-on Marketplace**

> [!IMPORTANT]
> **Procurement & Governance Benchmark:**  
> This document articulates OpenOptOut's alignment with **ISO/IEC 27001:2022 (Information Security, Cybersecurity and Privacy Protection — Information Security Management Systems)**. It provides enterprise security officers, higher-education CISOs, and institutional IT auditors with a formal **Statement of Applicability (SoA)** evaluating all **93 Annex A controls** across the four modernized ISO 27001:2022 domains: **Organizational (37)**, **People (8)**, **Physical (14)**, and **Technological (34)**.

---

## 1. Information Security Management System (ISMS) Scope & Boundary

OpenOptOut is engineered under a strict **Zero-Trust, Zero-Vendor-Exfiltration** security architecture. The ISMS scope encompasses:
1. **The Application Control Plane**: FastAPI routers, authentication providers (SAML, OIDC, SCIM, SIP2), rate limiting, and RBAC authorization policies.
2. **The Worker Execution Fleet**: Headless Playwright browser runtimes, bubblewrap/seccomp execution sandboxes, and Redis queue job dispatchers.
3. **The Cryptographic Storage Boundary**: Encrypted Identity Vault (AES-256-GCM epoch keyrings), SQLite (SQLCipher)/PostgreSQL encrypted storage, and NIST SP 800-88 media sanitization.
4. **The Add-on Marketplace & Supply Chain**: Remote catalog distribution, Ed25519/Cosign package signatures, provenance attestations, and emergency spec revocation pipelines.

---

## 2. ISO/IEC 27001:2022 Statement of Applicability (SoA)

### Legend:
- **Applicable (A)**: Control is active and enforced in OpenOptOut architecture.
- **Implemented (I)**: Full technical or procedural implementation in code.
- **Not Applicable (NA)**: Control applies to physical hosting facilities rather than the open-source software appliance itself (institutionally inherited).

---

### Clause 5: Organizational Controls (37 Controls)

| Control | Control Name | Status | Technical Implementation in OpenOptOut |
|---|---|---|---|
| **5.1** | Policies for information security | A / I | Comprehensive policies documented in `SECURITY.md`, `AGENTS.md`, and `docs/architecture/`. |
| **5.2** | Information security roles and responsibilities | A / I | Role-Based Access Control (`core/access.py`): `super_admin`, `admin`, `manager`, `parent`, `member`. |
| **5.3** | Segregation of duties | A / I | Separation between system administration (`routers/admin.py`) and member identity vaults (`routers/vault.py`); super admin cannot be auto-granted via SSO (`core/sso_policy.py`). |
| **5.4** | Management responsibilities | A / I | Administrative dashboard alert feeds, audit logs, and certificate expiration monitoring (`core/cert_monitor.py`). |
| **5.5** | Contact with authorities | A / I | RFC 9116 `security.txt` and CSAF 2.0 provider metadata for rapid security coordination. |
| **5.6** | Contact with special interest groups | A / I | Open-source bug bounty and private vulnerability reporting program via GitHub Security Advisories. |
| **5.7** | Threat intelligence | A / I | Curated data broker health monitoring (`core/broker_health.py`) and automated broker drift detection. |
| **5.8** | Information security in project management | A / I | Mandatory security verification suites and pre-push hooks (`scripts/security_check.py`). |
| **5.9** | Inventory of information and other associated assets | A / I | Machine-readable ROPA (`GET /api/privacy/ropa`) and dynamic SBOM endpoints (`GET /api/admin/sbom`). |
| **5.10** | Acceptable use of information and assets | A / I | Legal terms recording and acting-for authority confirmations (`core/terms.py`). |
| **5.11** | Return of assets | A / I | Automated data export (`GET /api/privacy/export`) allowing complete patron data repatriation. |
| **5.12** | Classification of information | A / I | Strict data classification: PII (encrypted), System Config (encrypted/hashed), Public Specs (plaintext). |
| **5.13** | Labelling of information | A / I | Machine-readable cryptographic headers (`gcm:v{epoch}:`) identifying ciphertexts and key epochs. |
| **5.14** | Information transfer | A / I | Mandatory TLS/STARTTLS enforcement for SMTP, HTTPS API enforcement, and encrypted migration envelopes. |
| **5.15** | Access control | A / I | Principle of least privilege enforced across API endpoints via dependency injection (`Depends(require_role)`). |
| **5.16** | Identity management | A / I | NIST SP 800-63A/C Identity Assurance Engine (`core/identity_assurance.py`) governing IAL and FAL. |
| **5.17** | Authentication information | A / I | PBKDF2-SHA512 password hashing (100k iterations) and RFC 9449 DPoP sender-constrained tokens. |
| **5.18** | Access rights | A / I | Granular permission checks (`can(user, 'permission')`) restricting multi-tenant visibility. |
| **5.19** | Information security in supplier relationships | A / I | Strict boundary enforcement for third-party solver plugins and data broker target gateways. |
| **5.20** | Addressing security within supplier agreements | A / I | Privacy terms enforcement across plugin manifests (`outbound_domains` whitelisting). |
| **5.21** | Managing security in the ICT supply chain | A / I | OpenSSF SLSA Level 3 build provenance attestations and pinned base container dependencies. |
| **5.22** | Monitoring, review and change management of supplier services | A / I | Automated broker health monitoring auto-disabling broken or unresponsive third-party brokers. |
| **5.23** | Information security for cloud services | A / I | Zero-Cloud Invariant: 100% self-hosted; cloud model APIs completely replaceable with local Ollama inference. |
| **5.24** | Information security incident management planning | A / I | Documented incident response protocols and security audit scope (`docs/dev/audit-scope.md`). |
| **5.25** | Assessment and decision on information security events | A / I | Ring-buffer diagnostic log handler with dynamic log verbosity and automated error classification. |
| **5.26** | Response to information security incidents | A / I | Immediate session revocation (`/api/auth/signout-everywhere`) and token family revocation. |
| **5.27** | Learning from information security incidents | A / I | Automated post-mortem regression testing integrated into CI/CD release tests. |
| **5.28** | Collection of evidence | A / I | Tamper-evident HMAC-signed Certificates of Sanitization under NIST SP 800-88 Rev. 1. |
| **5.29** | Information security during disruption | A / I | High-availability distributed worker fleets (`docker-compose.distributed.yml`) with failover queues. |
| **5.30** | ICT readiness for business continuity | A / I | Automated encrypted backup pipelines (`core/backup.py`) supporting local, S3, SFTP, and WebDAV targets. |
| **5.31** | Legal, statutory, regulatory and contractual requirements | A / I | Full statutory mapping across CCPA/CPRA, GDPR, LGPD, COPPA, and FERPA. |
| **5.32** | Intellectual property rights | A / I | Licensed under AGPL-3.0 with complete SPDX 2.3 licensing metadata generation. |
| **5.33** | Protection of records | A / I | Write-Ahead Log truncation, cryptographic erasure, and tamper-resistant audit logging. |
| **5.34** | Privacy and protection of PII | A / I | ISO/IEC 27701 (PIMS) and ISO/IEC 29100 Privacy Architecture Framework conformance. |
| **5.35** | Independent review of information security | A / I | Formal audit boundaries published in `docs/dev/audit-scope.md` for external penetration testing. |
| **5.36** | Compliance with policies and standards | A / I | Continuous automated CI test suites (`run_tests.py`) asserting compliance on every commit. |
| **5.37** | Documented operating procedures | A / I | Complete Administrator & Operations Guide (`docs/admin/index.md`). |

---

### Clause 6: People Controls (8 Controls)

| Control | Control Name | Status | Technical Implementation in OpenOptOut |
|---|---|---|---|
| **6.1** | Screening | NA | Responsibility of the self-hosting institution/operator. |
| **6.2** | Terms and conditions of employment | NA | Responsibility of the self-hosting institution/operator. |
| **6.3** | Information security awareness, education and training | A / I | Educational in-app walkthroughs, setup wizard guidance, and plain-language COPPA advisories. |
| **6.4** | Disciplinary process | NA | Responsibility of the self-hosting institution/operator. |
| **6.5** | Responsibilities after termination or change of employment | A / I | SCIM 2.0 automated deprovisioning (`DELETE /Users/{id}`) immediately cascading to data zeroization. |
| **6.6** | Confidentiality or non-disclosure agreements | NA | Responsibility of the self-hosting institution/operator. |
| **6.7** | Remote working | A / I | Cross-origin isolation (COOP/CORP), strict CSP, and DPoP sender-constrained token protections for remote web access. |
| **6.8** | Information security event reporting | A / I | Direct in-app error reporting and CSP violation reporting endpoint (`POST /api/csp-report`). |

---

### Clause 7: Physical Controls (14 Controls)

| Control | Control Name | Status | Technical Implementation in OpenOptOut |
|---|---|---|---|
| **7.1 - 7.14** | Physical security perimeters, entry, equipment, media, utilities | NA | Inherited from the deploying institution's data center, on-premises server room, or cloud infrastructure. OpenOptOut ensures software-level defense-in-depth via full-disk encryption support and encrypted database files (SQLCipher). |

---

### Clause 8: Technological Controls (34 Controls)

| Control | Control Name | Status | Technical Implementation in OpenOptOut |
|---|---|---|---|
| **8.1** | User endpoint devices | A / I | Responsive, accessible web client adhering to browser security sandbox constraints; no native agent binaries required on patron devices. |
| **8.2** | Privileged access rights | A / I | Super-admin MFA mandate within 3 days of installation; privilege step-up verification for security changes. |
| **8.3** | Information access restriction | A / I | Patron profile isolation: family members cannot view other families' vaults; consortium isolation across tenants. |
| **8.4** | Access to source code | A / I | Fully open-source AGPL-3.0 on GitHub with branch protection rules and signed commits. |
| **8.5** | Secure authentication | A / I | WebAuthn/FIDO2 Level 3 hardware passkeys, TOTP, and 10k SecLists common password dictionary blocklist. |
| **8.6** | Capacity management | A / I | Memory hygiene monitors (`core/memory_hygiene.py`) and job concurrency rate limiters. |
| **8.7** | Protection against malware | A / I | Decompression bomb pre-scan on XLSX imports, safe filename sanitization, and strict sandbox isolation. |
| **8.8** | Management of technical vulnerabilities | A / I | Automated multi-scanner pre-push verification (Semgrep, Bandit, Trivy, OSV-Scanner, Actionlint). |
| **8.9** | Configuration management | A / I | Immutable Docker container architecture with declarative settings schemas (`settings_store.py`). |
| **8.10** | Information deletion | A / I | NIST SP 800-88 Cryptographic Erase cascading through member deletion and SQLite WAL truncation. |
| **8.11** | Data masking | A / I | Automatic redaction of sensitive credentials, PII masking on solver egress (`core/captcha_privacy.py`), and log sanitization. |
| **8.12** | Data leakage prevention | A / I | Zero outbound telemetry; explicit `outbound_domains` firewall whitelisting in broker execution engine. |
| **8.13** | Information backup | A / I | Encrypted, scheduled database and configuration backup engine supporting remote off-site replication. |
| **8.14** | Redundancy of information processing facilities | A / I | Distributed worker daemon fleets communicating over authenticated Redis queues (`WorkerDaemon`). |
| **8.15** | Logging | A / I | Structured security audit event logging (`core/logging_config.py`) with PII redaction filters. |
| **8.16** | Monitoring activities | A / I | Real-time Prometheus metrics endpoint (`/metrics`), live health probes (`/api/health`), and certificate monitors. |
| **8.17** | Clock synchronization | A / I | NTP synchronization asserted in federated token validation (60-second clock skew tolerance). |
| **8.18** | Use of privileged utility programs | A / I | Banned dangerous execution wrappers (`eval`, `system`); sandboxed subprocess execution via Bubblewrap. |
| **8.19** | Installation of software on operational systems | A / I | Curated add-on marketplace requiring signed manifests, integrity checksums, and declarative JSON specs. |
| **8.20** | Network security | A / I | Automated reverse proxy integration (Caddy/Nginx) enforcing HTTPS, HSTS, and mTLS client-certificate validation. |
| **8.21** | Security of network services | A / I | Dedicated DNS rebinding and SSRF protection (`dns_guard.assert_safe_url()`) blocking private IP ranges. |
| **8.22** | Segregation of networks | A / I | Docker Compose internal network bridge isolating database and Redis from external exposure. |
| **8.23** | Web filtering | A / I | Safe anchor URL wrapping (`isSafeHref()`) preventing `javascript:` pseudo-protocol execution. |
| **8.24** | Use of cryptography | A / I | AES-256-GCM, HKDF-SHA256 key derivation, NIST SP 800-57 epoch key versioning, and Ed25519 signatures. |
| **8.25** | Secure development life cycle | A / I | Automated pre-push security hooks, PR linting, and continuous release testing in GitHub Actions. |
| **8.26** | Application security requirements | A / I | Comprehensive alignment with OWASP ASVS 5.0.0 Level 2 and OWASP Top 10 for LLMs. |
| **8.27** | Secure system architecture and engineering principles | A / I | CISA Secure by Design: structural vulnerability class elimination across SQLi, XSS, SSRF, and path traversal. |
| **8.28** | Secure coding | A / I | Parameterized SQLAlchemy ORM queries, React auto-escaping, and strict JSON schema bounding. |
| **8.29** | Security testing in development and acceptance | A / I | Multi-tier test harness (`backend.tests.run_tests`), static JSX a11y linter, and Playwright UI tests. |
| **8.30** | Outsourced development | A / I | Strict coding agent instructions (`AGENTS.md`) and broker add-on packaging rules. |
| **8.31** | Separation of development, test and production environments | A / I | Dry-run mock executors (`DryRunExecutor`) ensuring tests never fire real live broker requests. |
| **8.32** | Change management | A / I | SemVer release management, database migrations (`core/migrations.py`), and 90-second rollback daemon. |
| **8.33** | Test information | A / I | Synthetic personas ("Jordan Example", `@example.invalid`) used exclusively in test fixtures; zero real PII. |
| **8.34** | Protection of information systems during audit testing | A / I | Rehearsal-mode execution boundaries (`spec_drafter.rehearse()`) halting prior to final submission clicks. |

---

## 3. Marketplace Security Invariants (Roadmap Item #8 Pre-Requisites)

To satisfy ISO/IEC 27001:2022 **Controls 5.19–5.23 (Supply Chain Security)** and **Controls 8.19–8.30 (Secure Software Lifecycle)**, the upcoming Add-on Marketplace (Roadmap Item #8) is bound by six non-negotiable security invariants:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      MARKETPLACE SUPPLY-CHAIN SECURITY INVARIANTS                      │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Declarative Pure Data Invariant: Broker add-ons are strictly declarative JSON data  │
│    (`manifest.json` + `spec.json`). Zero arbitrary executable code or Python scripts.  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 2. Cryptographic Code Signing & SLSA L3: Every add-on bundle is signed via Cosign      │
│    or Ed25519 with transparency log inclusion (Sigstore Rekor).                        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 3. Tiered Publisher Governance: Strict separation between Core Bundled (Tier 1),      │
│    Verified Partner (Tier 2), and Community Experimental (Tier 3) add-ons.            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 4. Syscall & Network Sandbox: Non-declarative solver plugins execute strictly within   │
│    Bubblewrap Linux user namespaces with Seccomp syscall filtering and domain blocking.│
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 5. Automated Emergency Revocation: Out-of-band Signed Certificate Revocation List     │
│    (CRL) enabling instant, global quarantine of compromised specs across all nodes.    │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 6. Air-Gapped Registry Mirroring: Complete support for offline enterprise catalog mirrors│
│    allowing institutional deployments to operate with zero external internet access.  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Institutional Certification & Audit Readiness

OpenOptOut provides institutions with an audit-ready compliance posture that dramatically streamlines vendor risk assessments (e.g., HECVAT, CAIQ, SOC 2 Type II mapping).

For technical audit artifacts and automated verification suites:
- **Statement of Applicability Verification**: Tested via `backend/tests/run_tests.py` (`security.standards_iso_27001_isms`).
- **Cryptographic Specifications**: See [`nist-key-management-800-57.md`](nist-key-management-800-57.md) and [`media-sanitization-800-88.md`](media-sanitization-800-88.md).
- **Privacy Controls**: See [`privacy-framework-29100.md`](privacy-framework-29100.md) and [`pims-iso-27701-ropa.md`](pims-iso-27701-ropa.md).

