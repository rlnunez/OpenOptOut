# OpenOptOut — Architectural Roadmap

Status: **Active Development.** This document tracks in-progress, planned, and under-consideration architectural work for OpenOptOut.

> [!NOTE]
> **Completed Milestones Archive:** Historical specifications, design rationale, and verification notes for completed milestones up through v0.11.0 are documented in the [Completed Milestones Archive (`docs/archive/COMPLETED_ROADMAP.md`)](archive/COMPLETED_ROADMAP.md) (frozen after v0.11.0 release). Subsequent completed roadmap items, enhancements, and release notes are documented directly in [`CHANGELOG.md`](../CHANGELOG.md).

The guiding architectural principle: **the core does not contain broker-specific logic.** The core engine interprets declarative specifications detailing how a broker's opt-out functions (web forms, emails, required language/templates, multi-step flows) and executes them. Brokers are packaged as declarative specifications and optional isolated code extensions maintained independently.

---

## Active & Planned Items at a Glance

| # | Item | Status | Priority / Target |
|---|------|--------|-------------------|
| [8](#item-8) | [Add-on distribution: Git repo to curated marketplace](#item-8) | Active / In Design | High (Phase 8.1 Active) |
| [11](#item-11) | [Setup wizard: Catalog step & recommended protections bundle](#item-11) | Planned | Medium (Follows Item 8) |
| [12](#item-12) | [School district authentication (Parent Portal SSO)](#item-12) | On-Demand | District Request Only |
| [14](#item-14) | [Extended DNS-01 ACME challenge providers (AWS, DigitalOcean, deSEC)](#item-14) | Planned | Medium |
| [22](#item-22) | [Independent security audit & penetration testing](#item-22) | Planned | High (Pre-1.0) |
| [38](#item-38) | [Built-in receive-only inbox](#item-38) | Considering | Low / Backup Seam |
| [64](#item-64) | [Community onboarding: mailed postcard tokens & manager review](#item-64) | Planned | Low / Enhancements |
| [67](#item-67) | [High-risk mode for domestic violence survivors & election workers](#item-67) | Planned | High |
| [69](#item-69) | [Removal-service ownership & broker-family conflict flags](#item-69) | Planned | Medium |
| [70](#item-70) | [Native-speaker review for 5 newest languages](#item-70) | Planned | Medium |
| [72](#item-72) | [Instance migration, tenant merging & identity re-anchoring](#item-72) | Planned | Medium (Institutional & Consortium) |

---

## Active & Upcoming Work Items

<a id="item-8"></a>
### 8. Add-on distribution: Git repository to curated marketplace
**Goal:** Establish a modular distribution channel for community broker specs, solver plugins, and language packs through an integrated core catalog client and curated marketplace.

**Detailed Design:** See [`docs/dev/proposals/catalog-design.md`](dev/proposals/catalog-design.md).

**Phased Execution:**
- **Phase 8.1 — Core Catalog Client & Declarative Index (`index.json`) (Active / In Design):**
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

---

<a id="item-11"></a>
### 11. Setup wizard: Catalog step & recommended protections bundle
**Goal:** Streamline initial installation onboarding by selecting pre-curated protection bundles (e.g., "US High Priority", "EU GDPR Focus", "Stalker & Harassment Protection").

- Wizard Step 4 ("Recommended Protections") pulls the Tier 1 bundle from the catalog index.
- 1-click batch installation and automated dependency resolution during first-run setup.

---

<a id="item-12"></a>
### 12. School district authentication (Parent Portal SSO)
**Goal:** Enable K-12 school districts to offer OpenOptOut to parent communities via district student information systems (PowerSchool, Infinite Campus, Skyward).

- Implemented on-demand for partnering public school districts.
- Read-only parent portal roster ingestion mapping parents to enrolled students for automated family group provisioning.

---

<a id="item-14"></a>
### 14. Extended DNS-01 ACME challenge providers
**Goal:** Broaden zero-port-forwarding HTTPS certificate automation for private, internal, and dynamic-DNS deployments.

- **Current Status:** Cloudflare DNS-01 is complete via Caddy (`tls.dns.cloudflare`) and Traefik (`CLOUDFLARE_DNS_API_TOKEN`).
- **Planned Providers:** Add native DNS-01 challenge support for AWS Route 53, DigitalOcean, deSEC, and DuckDNS in front-door proxy configurations.

---

<a id="item-22"></a>
### 22. Independent security audit & penetration testing
**Goal:** Commission an independent, third-party source code and cryptographic audit by a reputable firm (e.g., OSTIF, Radically Open Security) prior to the 1.0 GA release.

- Audit scope document defined in [`docs/dev/audit-scope.md`](dev/audit-scope.md).
- Focus areas: PII zeroization in memory, sandbox escape resistance (bubblewrap/seccomp), authenticated encryption bounds, OAuth token handling, and SQLCipher key derivation.
- **Internal Compliance Baselines Completed (v0.11.0-rc8):**
  - **OWASP ASVS 4.0.3 Level 2**: 12-char minimum password policy, breached-password rejection, self-service password rotation, session token versioning, admin change notifications, CSV formula injection defense, and SVG content-sniffing protection (PR #137).
  - **OWASP Top 10 for LLMs**: Hardened schema output bounds (`maxLength`/`maxItems`) and provider token limits (`max_tokens=16000`) for unbounded consumption defense (LLM10, PR #138).
  - **NIST SP 800-38D & SP 800-132**: AES-256-GCM AEAD field and backup encryption, 210,000-iteration PBKDF2 password peppering, and RFC 5869 HKDF domain separation.
  - **ISO/IEC 27701 & COPPA**: Granular data retention schedules, automated multi-pass crypto-shredding upon member deletion with SQLite vacuuming, and 30-day floor preservation (PR #139).

---

<a id="item-38"></a>
### 38. Built-in receive-only inbox
**Goal:** Provide unique disposable email addresses on a family-owned domain for data brokers that do not support or reject standard `+` alias addressing.

- **Detailed Design:** See [`docs/dev/proposals/builtin-inbox.md`](dev/proposals/builtin-inbox.md).
- **Status:** Under consideration as an alternative when upstream brokers strip or refuse plus addresses.

---

<a id="item-64"></a>
### 64. Community onboarding: mailed postcard tokens & manager review
**Goal:** Extend address-verified housing community registration with physical address proof mechanisms.

- **Current Status:** Address matching against authorized CSV lists with unit normalization is complete.
- **Planned Enhancements:** Physical mailed postcard tokens with one-time verification codes, and an optional manual application workflow for unlisted or newly annexed addresses.

---

<a id="item-67"></a>
### 67. High-risk mode for survivors, doxxing targets & election workers
**Goal:** Provide elevated protective posture for users facing acute physical safety threats, domestic violence, doxxing campaigns, or judicial/election work.

- Daily accelerated verification cycles (bypassing normal 30-day delays).
- Priority task queue channel (`removal_high`).
- Aggressive listing search intervals across high-risk broker subsets.
- Immediate webhook/SMS notification when an expunged listing reappears.

---

<a id="item-69"></a>
### 69. Removal-service ownership & broker-family conflict flags
**Goal:** Detect and flag conflicts when commercial removal services (DeleteMe, Incogni, Kanary) or overlapping family accounts submit conflicting requests to the same broker.

---

<a id="item-70"></a>
### 70. Native-speaker review for 5 newest languages
**Goal:** Conduct native-speaker linguistic reviews of the 5 newest language packs (Polish, Ukrainian, Urdu, Swahili, Indonesian) to ensure cultural and legal terminology accuracy.

---

<a id="item-72"></a>
### 72. Instance migration, tenant merging & identity re-anchoring
**Goal:** Enable seamless data migration, tenant consolidation, and identity re-anchoring when grassroots community instances merge into broader institutional deployments (e.g., when a public library district, municipal authority, or regional consortium assumes hosting for an area).

- **Encrypted Migration Envelopes:**
  - Export end-to-end encrypted tenant bundles containing family profiles, encrypted identity vaults, custom removal policies, and historical verification records.
  - PII remains strictly encrypted at rest and in transit (using target-instance public key or ephemeral transfer passphrases).
- **Deduplication & Merge Reconciliation:**
  - Merges removal histories and in-flight broker requests without duplicating outreach or resetting verified suppression timelines.
  - Automatically reconciles overlapping listings, member aliases, and broker response logs.
- **Identity Re-Anchoring & Auth Provider Migration:**
  - Facilitates transitioning users from legacy authentication (local password, magic link, community OIDC) to institutional authentication methods chosen by the host (e.g., public library card SIP2 barcode/PIN, university/municipal SAML 2.0, or LDAP).
  - Self-service claiming flow allows patrons to verify legacy credentials once and bind their existing family vault to their library or enterprise credentials with zero data loss.
  - Enforces deterministic assurance validation under the [NIST SP 800-63A/C Digital Identity Architecture](architecture/digital-identity-800-63.md) (`validate_identity_rebinding`), preventing unverified account claiming or IAL downgrades.
- **Operator Decommission & Cutover Tooling:**
  - Administrative handoff wizard with pre-flight schema compatibility verification, cutover redirect notices on the departing instance, and cryptographic zeroization of decommissioned host storage.
