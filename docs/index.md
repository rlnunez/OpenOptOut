# OpenOptOut Documentation

Welcome to the documentation for **OpenOptOut**, the self-hosted, AGPL-3.0 privacy tool that removes families and community members from commercial data broker directories.

---

## Documentation by Reader

```
┌───────────────────────────┬───────────────────────────┬───────────────────────────┐
│     User & Family         │   Administrator & Ops     │   Developer & Security    │
├───────────────────────────┼───────────────────────────┼───────────────────────────┤
│ • Finding your listings   │ • Docker & Native Install │ • Core Architecture       │
│ • Setting up family email │ • Built-in HTTPS & Edge   │ • Writing Broker Add-ons  │
│ • Verification monitoring │ • SSO, SAML & OIDC        │ • Interpreter Runtime     │
│ • Privacy rights & law    │ • Encrypted Backups       │ • Security Sandboxing     │
│                           │ • System Updates & Health │ • Test Suites & Scanners  │
│ [Explore User Guide →]    │ [Explore Admin Guide →]   │ [Explore Dev Guide →]     │
└───────────────────────────┴───────────────────────────┴───────────────────────────┘
```

### [User & Family Guide](user/index.md)
Everything you need to know about protecting yourself and your family:
- [Email setup](user/email-setup.md) — Plus addressing, family inboxes, and email tracking.
- [Verification checks](user/verification.md) — How OpenOptOut monitors whether removals stick.
- [Web search integration](user/web-search.md) — Finding exposed profiles via private SearXNG search.
- [Privacy page discovery](user/privacy-pages.md) — OneTrust, TrustArc, and custom forms.
- [State registries](user/state-registries.md) — California DROP, Texas, and Vermont registry workflows.
- [Data sharing & aggregators](user/data-sharing.md) — Removing from upstream aggregators first.
- [Privacy legislation](about/legislation.md) — CCPA, GDPR, LGPD, and statutory rights.

### [Administrator & Operations Guide](admin/index.md)
Technical guides for self-hosters, library IT, and community operators:
- [Automated HTTPS & Reverse Proxies](admin/https.md) — Caddy, Traefik, Cloudflare Tunnel, and AOP.
- [Native Bare-Metal Installation](admin/native-install.md) — Systemd services, Nginx, and Windows Server IIS.
- [Database Administration](admin/database.md) — SQLite (SQLCipher encryption) and enterprise PostgreSQL.
- [Encrypted Backups](admin/backups.md) — Local, network, SFTP, S3, and cloud storage (Proton, Box, pCloud).
- [Single Sign-On (SSO)](admin/sso.md) — OIDC (Google/Microsoft), SAML 2.0, and LDAP integration.
- [System Roles & Permissions](admin/roles.md) — Super admins, managers, and delegated controls.
- [Housing Community Onboarding](admin/communities.md) — Address-verified resident sign-ups.
- [System Updates & Maintenance](admin/updater.md) — Automated releases, workload draining, and instant rollback.
- [Monitoring & Prometheus](admin/monitoring.md) — Metrics endpoints, alerts, and health probes.

### [Developer & Architecture Guide](dev/index.md)
Resources for contributing to OpenOptOut and understanding system internals:
- [System Architecture](dev/architecture.md) — Modular design, boundaries, and thread models.
- [Privacy Architecture Framework](architecture/privacy-framework-29100.md) — ISO/IEC 29100 role definitions, trust boundaries, and 11 privacy principles.
- [NIST Privacy Framework Profile](architecture/nist-privacy-profile.md) — NIST Privacy Framework Version 1.0 and CSF Privacy Profile.
- [CISA Secure by Design](architecture/cisa-secure-by-design.md) — CISA / NSA / FBI Secure by Design principles, safe harbor, and vulnerability class elimination.
- [Media Sanitization & Cryptographic Erase](architecture/media-sanitization-800-88.md) — NIST SP 800-88 Rev. 1 media sanitization, WAL purge, and signed destruction certificates.
- [Key Management & Epoch Versioning](architecture/nist-key-management-800-57.md) — NIST SP 800-57 key management, epoch derivation, and re-encryption pipelines.
- [Privacy Information Management (ROPA & DPIA)](architecture/pims-iso-27701-ropa.md) — ISO/IEC 27701 & GDPR Article 30/35 compliance reports.
- [DPoP Sender-Constrained Tokens](architecture/dpop-rfc-9449.md) — RFC 9449 proof-of-possession token replay defense.
- [SCIM 2.0 Enterprise Identity](architecture/scim-enterprise-identity.md) — RFC 7643 & RFC 7644 automated user provisioning, session revocation, and deprovisioning.
- [Digital Identity Guidelines (NIST SP 800-63A/B/C)](architecture/digital-identity-800-63.md) — IAL, AAL, FAL assurance levels, and identity re-anchoring architecture for Item #72.
- [SLSA Level 3 & Supply Chain Security](architecture/slsa-supply-chain.md) — OpenSSF SLSA Level 3 build provenance, Sigstore attestations, and Cosign image signing.
- [Development Workflow](dev/development.md) — Local environment setup and running test matrices.
- [Interpreter Runtime](dev/interpreter.md) — Declarative broker specifications and Playwright execution.
- [Writing Broker Plugins](dev/plugins.md) — Step-by-step authoring guide for data broker add-ons.
- [Automatic Steps & AI Drafter](dev/automatic-steps.md) — Spec rehearsal, auto-repair, and AI helpers.
- [AI Governance (NIST AI RMF 1.0 & ISO/IEC 42001)](architecture/ai-governance-nist-iso.md) — AI risk management, prompt injection boundaries, synthetic rehearsal, and local model governance.
- [FERPA Architecture Alignment](architecture/ferpa-alignment.md) — 34 CFR Part 99, School Official exception, student data minimization, and campus IdP/SCIM integration.
- [Security Policy](../SECURITY.md) & [Accessibility & VPAT Conformance](../ACCESSIBILITY.md) — NIST SP 800-38D, NIST SP 800-132, ISO/IEC 27701, COPPA, OWASP ASVS L2, OWASP LLM Top 10, WCAG 2.2 (Level AA/AAA), Revised Section 508, and EN 301 549.
- [Security Scanning & Hardening](dev/security-scanning.md) — CodeQL, Semgrep, bandit, and audit posture.
- [Proposals & Design RFCs](dev/proposals/catalog-design.md) — Upcoming designs and request-for-comments.

---

## Roadmap & Release History

- **[Active & Planned Roadmap](ROADMAP.md):** Focuses strictly on in-progress, planned, and under-consideration initiatives.
- **[Completed Milestones Archive](archive/COMPLETED_ROADMAP.md):** Architectural specifications and test notes for historical milestones up through v0.11.0 (frozen archive).
- **[Changelog](../CHANGELOG.md):** Version-by-version release notes and change summaries tracking all ongoing updates.

