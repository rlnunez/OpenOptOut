# Security policy

OpenOptOut handles sensitive patron and family data. Security reports are welcome.

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

Report privately via **[Report a vulnerability](https://github.com/rlnunez/OpenOptOut/security/advisories/new)** (Security tab → Report a vulnerability).

Include:
- Vulnerability description and potential security impact
- Reproduction steps (requests, scripts, or screenshots)
- Affected version or commit hash (available via `/api/health`)

You should receive an initial response within 7 days. Valid reports will be credited in published advisories unless anonymity is requested.

## Scope

- **In scope:** Backend API, web UI, plugin sandbox (bubblewrap, seccomp, gRPC broker), data encryption at rest, authentication mechanisms (local, OIDC, SAML, LDAP, SIP2), distributed workers, installers, and official Docker images.
- **Out of scope:** Third-party data broker sites, and issues requiring prior root or host compromise (unless enabling container escapes or cross-tenant privilege escalation).

## Core Data Protection & Privacy Controls

- **No Personal Data Outside Encrypted Storage:** Patron and family member identifiers (names, addresses, phones, emails) are encrypted at rest using AES-256-GCM (NIST SP 800-38D) with HKDF domain separation.
- **Never Store SSNs or Government IDs:** Hard architectural boundary. SSNs, government IDs, and third-party passwords are never collected, filled, or stored.
- **Children's Data Protection (COPPA):** Dependent profiles are managed exclusively through authenticated parent/guardian accounts. Aux data (confirmation links, email logs) for minors is automatically crypto-shredded after the retention window (`coppa_children_retention_days`).
- **Zero Third-Party Telemetry:** Zero analytics SDKs, tracking pixels, or outbound telemetry. Outbound network requests are limited to admin-configured integrations and broker automation.
- **Memory Hygiene & Crash Protection:** Core dumps are suppressed at the process (`RLIMIT_CORE = 0`), container (`ulimits: core: 0`), and service levels to prevent cleartext memory dumps to disk. Ephemeral decrypted buffers are zeroized upon completion.
- **Plugin Sandboxing:** Broker plugins execute within OS-level namespaces (bubblewrap), seccomp syscall filters, and declared network boundaries.

## Data Classification

| Data Category | Classification | Encryption & Protection | Retention & Access |
|---|---|---|---|
| **Family Member PII** | Restricted (COPPA) | AES-256-GCM at rest; access logged; scrubbed from all logs | Self-service deletion; minors' aux data auto-purged |
| **SSNs & Government IDs** | Prohibited | Never collected, filled, or stored | N/A |
| **Credentials & Secrets** | Restricted | AES-256-GCM / Fernet; masked in UI; never logged | Kept until replaced/removed; admin only |
| **Session Tokens (JWT)** | Restricted | Signed (HMAC-SHA256); ephemeral browser storage | Revocable per-session or account-wide; expires per policy |
| **Security Audit Logs** | Internal | Structured text (`0600` permissions); PII scrubbed | Configurable retention (default 30+ days); admin only |
| **Interaction Artifacts** | Restricted | PII encrypted; CAPTCHAs blacked out before transmission | Purged per retention schedule |
| **Uploaded Branding** | Low | Validated, stripped of metadata, re-encoded from pixels | Replaced on upload; public login asset |

## Web Frontend & Browser Security

- **Token Authentication:** Authentication uses Bearer tokens passed in the `Authorization` header rather than ambient cookies, eliminating cross-site request forgery (CSRF) exposure.
- **Security Headers & CSP:** Enforces `nosniff`, `strict-origin-when-cross-origin`, frame restrictions, and an explicit `Content-Security-Policy` (`object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`) with reporting to `/api/csp-report`.
- **Self-Hosted Assets:** All JavaScript, stylesheets, and fonts are bundled locally with no external CDN runtime dependencies.
- **Input Neutralization:** External links and broker text are validated and sanitized (`isSafeHref`, control character filtering) to prevent injection and malicious scheme execution.

## Authentication & Session Controls

- **Progressive Throttling:** Exponential backoff and independent account/IP locking on repeated failed attempts without account enumeration.
- **Multi-Factor Authentication:** TOTP (RFC 6238) and FIDO2/WebAuthn with counter-replay protection and password re-verification.
- **Session Tracking & Revocation:** Each sign-in issues a discrete session ID (`UserSession`). Users can view and revoke individual sessions or sign out everywhere; admins can force-revoke sessions globally.
- **Audit Logging:** Structured audit lines (`auth_event`, `authz_denied`, `lockout_triggered`) record security events in UTC with numeric IDs and scrubbed PII.

## Cryptographic Inventory & Key Management

All cryptographic keys are operator-supplied via environment variables or owner-only files (`0600`), or derived using RFC 5869 HKDF for purpose-specific domain separation.

| Key / Material | Purpose | Algorithm / Standard | Rotation Guidance |
|---|---|---|---|
| `SECRET_KEY` | Root secret, JWT signing, HKDF root | HMAC-SHA256 (128+ chars) | Annually, or immediately on suspected compromise |
| `FIELD_ENCRYPTION_KEY` | Patron PII encryption at rest | AES-256-GCM (NIST SP 800-38D) | On compromise (with data re-encryption) |
| `DB_ENCRYPTION_KEY` | Database file encryption | SQLCipher AES-256 | On compromise |
| Password Pepper | Pre-hash passwords before bcrypt | PBKDF2-HMAC-SHA256 (210k rounds) | On compromise (independent of `SECRET_KEY`) |
| `SEARXNG_SECRET` | Search instance session signing | HMAC-SHA256 | Annually |
| Queue HMAC Key | Distributed worker envelope integrity | HMAC-SHA256 (HKDF-derived) | Derived from `SECRET_KEY` |
| Backup Key | Backup archive confidentiality | AES-256-GCM (scrypt/PBKDF2) | Per organizational backup policy |
| DB / Redis Passwords | Service-to-service authentication | High-entropy string | Annually or on staff turnover |

## External Services & File Uploads

- **External Integrations:** Outbound connections (SMTP/IMAP, SearXNG, SSO IdPs, webhooks, brokers) are strictly administrator-configured, enforce short bounded timeouts (10–25s), and do not silently cascade retries.
- **File Upload Boundaries:** All upload endpoints are restricted to authenticated administrators and enforce size caps:
  - Branding logos: 2 MB limit; magic-byte verified; raster images re-encoded from raw pixels; SVGs sanitized.
  - Broker plugins: 50 MB zip limit; manifest verified; inspected for path traversal and disallowed syscalls before installation.
  - CSV/JSON/Registry imports: 10–30 MB limits; strict schema validation; uncompressed size and entry limits enforced on zip/xlsx archives.

## Compliance & Security Standards

OpenOptOut is engineered to follow recognized industry standards for application security, cryptography, and privacy:

- **NIST SP 800-38D**: Authenticated Encryption with Galois/Counter Mode (AES-256-GCM).
- **NIST SP 800-132 & SP 800-63B**: Password-Based Key Derivation (PBKDF2), MFA standards, and session controls.
- **ISO/IEC 27701 & COPPA**: Privacy Information Management, parental consent boundaries, and automated crypto-shredding.
- **OWASP ASVS 5.0.0 Level 2**: Application Security Verification Standard baseline for web applications and APIs.
- **OWASP Top 10 for LLMs**: Large Language Model application security and prompt injection encapsulation boundaries.
- **WCAG 2.2 Level AAA**: Universal web accessibility and contrast (see [`ACCESSIBILITY.md`](ACCESSIBILITY.md)).

## Automated Scanning

Every change is verified by automated static and dynamic security scanners. See [`docs/dev/security-scanning.md`](docs/dev/security-scanning.md).
