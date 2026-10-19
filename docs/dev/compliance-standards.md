# Security & Cryptographic Compliance Standards

OpenOptOut is engineered to protect sensitive personal and family data against unauthorized disclosure, tampering, and offline cryptanalysis. The platform adheres to internationally recognized standards for authenticated encryption, key derivation, privacy information management, and accessible interfaces.

---

## 1. NIST SP 800-38D — Galois/Counter Mode (AES-GCM)

[NIST SP 800-38D](https://csrc.nist.gov/publications/detail/sp/800-38d/final) defines Galois/Counter Mode (GCM) for authenticated symmetric encryption, providing both confidentiality and cryptographic integrity verification.

### Application Field-Level Encryption (`backend/core/encryption.py`)
Sensitive Personally Identifiable Information (PII) — including legal name variants, email addresses, phone numbers, and physical street addresses — is encrypted prior to database insertion.
- **Algorithm**: AES-256-GCM.
- **Key Length**: 256 bits (32 bytes), derived via HKDF-SHA256 (`openoptout:field-encryption-gcm:v1`) from `FIELD_ENCRYPTION_KEY` or `SECRET_KEY`.
- **Initialization Vector (IV / Nonce)**: 96 bits (12 bytes), generated per-record using the OS cryptographically secure pseudorandom number generator (`secrets.token_bytes(12)`), in strict compliance with NIST SP 800-38D §5.2.1.1.
- **Authentication Tag**: 128 bits (16 bytes) appended to ciphertext, verified in constant time.
- **Storage Format**: `gcm1:<base64-urlsafe(12-byte IV + ciphertext + 16-byte tag)>`.
- **Backward Compatibility**: Transparent dual-decryption supporting both modern `gcm1:` tokens and legacy `gAAAAA...` Fernet (AES-128-CBC + HMAC-SHA256) tokens.
- **Fail-Closed Guarantees**: Any tampering or bit modification in the ciphertext or tag fails authentication immediately; in production mode (`ENFORCE_ENCRYPTION_AT_REST=true`), missing keys or verification failures raise strict exceptions rather than falling back to plaintext.

### Backup Archive Encryption (`backend/core/backup.py`)
All system backups exported locally or uploaded to remote destinations (S3, SFTP, NAS) are encrypted using framed AES-256-GCM:
- **Chunk Framing**: 4 MiB streaming authenticated chunks.
- **Nonce Structure**: 64-bit random prefix (`secrets.token_bytes(8)`) concatenated with 32-bit big-endian chunk sequence counter (`struct.pack(">I", idx)`), yielding a 96-bit nonce.
- **Authenticated Additional Data (AAD)**: Chunks bind the file magic header (`OOBACKUP1\n`), JSON manifest header, chunk index, and terminal chunk boolean flag into GHASH calculation to prevent chunk reordering, substitution, or truncation.

---

## 2. NIST SP 800-132 — Password-Based Key Derivation

[NIST SP 800-132](https://csrc.nist.gov/publications/detail/sp/800-132/final) provides recommendations for deriving cryptographic keys and hashes from human passphrases.

### Password Pre-Hashing & Peppering (`backend/core/auth.py`)
To protect stored credentials against GPU-accelerated dictionary attacks and offline rainbow tables while honoring bcrypt's 72-byte ceiling:
- **KDF Algorithm**: PBKDF2-HMAC-SHA256.
- **Iteration Count**: $\ge 210,000$ rounds (conforming to NIST SP 800-132 recommendations and OWASP Password Storage Guidelines).
- **Salt / Pepper**: Derived from the server-side master pepper key (`openoptout:auth:password-pepper:v1`).
- **Storage Digest**: 44-character Base64 string (32 raw bytes), subsequently hashed with bcrypt (cost factor 12).
- **Seamless Hash Migration**:
  - `verify_password` checks modern 210,000-iteration hashes first, falling back to legacy 100,000-iteration hashes or unpeppered hashes.
  - Upon successful authentication with a legacy hash, the system automatically and transparently recalculates and upgrades the stored hash to the modern 210,000-iteration format.

### Backup Key Derivation (`backend/core/backup.py`)
- **KDF Algorithm**: PBKDF2-HMAC-SHA256 (`"pbkdf2_sha256"`) and scrypt (`"scrypt"`).
- **Salt Length**: 128 bits (16 bytes) CSPRNG-generated salt per backup archive.
- **PBKDF2 Iterations**: 210,000 rounds.
- **Header Metadata**: Archives store `"kdf": "pbkdf2_sha256"`, `"iterations": 210000`, and base64-encoded salt in the signed archive header.

### Cryptographic Key Separation (RFC 5869 / HKDF-SHA256)
Master secret keys (`SECRET_KEY`) are never used directly as cipher keys. OpenOptOut uses HKDF-Extract-and-Expand key derivation to isolate subkeys across independent subsystems:

| Subsystem Domain Label | Purpose | Module |
|---|---|---|
| `openoptout:field-encryption-gcm:v1` | AES-256-GCM PII field encryption | `core/encryption.py` |
| `openoptout:field-encryption:v1` | Primary Fernet field encryption | `core/encryption.py` |
| `openoptout:settings:v1` | Sensitive settings & SMTP credentials | `core/settings_store.py`, `routers/settings.py` |
| `openoptout:index-hash:v1` | Keyed HMAC-SHA256 searchable indexes | `core/encryption.py` |
| `openoptout:backup-codes:v1` | Single-use MFA recovery codes | `core/mfa.py` |
| `openoptout:mfa-ticket:v1` | Ephemeral login challenge tickets | `core/mfa.py` |
| `openoptout:envelope:hmac:v1` | Distributed queue message signatures | `core/distributed/envelope.py` |

---

## 3. ISO/IEC 27701 & COPPA Compliance

OpenOptOut implements privacy-by-design controls aligned with **ISO/IEC 27701** (Privacy Information Management) and **COPPA** (Children's Online Privacy Protection Act):

- **Granular Data Retention Schedules** (`Admin → Settings → Lifecycle`):
  - Configurable retention periods for system audit logs, failure screenshots/artifacts, COPPA minor profile data, and staff access logs.
  - Quick-preset duration selectors (`30d`, `90d`, `180d`, `1y`) and custom duration configurations.
- **Automated Crypto-Shredding on Deletion** (`core/people.py`):
  - When a member or child record is deleted, all stored PII fields are overwritten in-place with cryptographically secure pseudo-random bytes (`os.urandom`) across multiple passes before deleting the database row.
  - Optional automated SQLite database vacuuming (`VACUUM`) purges deleted pages from free lists to eliminate remnants on disk.
  - Zero PII is committed to audit event logs during deletion.

---

## 4. WCAG 2.2 Level AAA Accessibility

The user interface is engineered to comply with the highest tier of web accessibility ([WCAG 2.2 AAA](https://www.w3.org/TR/WCAG22/)):

- **Theme Contrast**: Standard and Dark ADA-compliant themes achieve contrast ratios exceeding $7:1$ for normal text and $4.5:1$ for large text; a dedicated High Contrast theme delivers $>14:1$ contrast.
- **Typography & Dyslexia Support**: Self-hosted OpenDyslexic, Antonio, and JetBrains Mono fonts, configurable dynamically during first-run setup or account preferences.
- **Zero Third-Party Assets**: All fonts, stylesheets, scripts, and iconography are 100% self-hosted to maintain air-gap readiness and prevent tracking.
- **RTL & Logical Layouts**: Complete bidirectional mirroring using Tailwind start/end logical properties (`ms-`, `pe-`, `start-`, `text-start`).

---

## 5. OWASP ASVS 4.0.3 Level 2 Compliance

OpenOptOut adheres to the **OWASP Application Security Verification Standard (ASVS) 4.0.3 Level 2** baseline for applications processing sensitive personal and family data:

- **V2: Authentication & Password Security**:
  - Minimum 12-character password policy enforced across registration, setup, and password changes (ASVS 2.1.1).
  - Pre-hash dictionary screening rejecting the top 10,000 common and breach-compromised passwords (`core/password_check.py`, ASVS 2.1.7).
  - Self-service password change route (`POST /api/auth/password/change`) requiring current password verification (ASVS 2.1.10).
  - Token versioning (`token_version`) automatically terminating existing active JWT bearer sessions upon credential change or administrative reset (ASVS 3.3.4).
  - Automated security email notifications dispatched when an administrator changes a user's role, password, or MFA status (ASVS 2.1.11).
  - Elimination of account-enumeration oracles in password reset and magic link endpoints via constant-time responses and normalized timing (ASVS 2.2.2).
  - IP and account rate-limiting on magic link generation to prevent inbox flooding (ASVS 2.3.1).
- **V5: Validation, Sanitization & Encoding**:
  - CSV formula injection protection (`core/csv_safety.py`) prepending single quotes to leading dangerous characters (`=`, `+`, `-`, `@`, `\t`, `\r`) in member and audit exports (ASVS 5.1.4).
  - Content sniffing defense on user/brand SVG uploads enforcing `X-Content-Type-Options: nosniff` and XML root tag validation (ASVS 5.1.5).
  - Audit log forging mitigation through control character escaping (`\r`, `\n`) in event log streams (ASVS 7.1.1).
  - Strict input boundary validation capping profile and configuration text fields to prevent memory denial-of-service (ASVS 5.1.1).
- **V8 & V13: Cryptographic & API Protection**:
  - RFC 5869 HKDF domain separation isolating field encryption, session tokens, settings storage, and backup codes (ASVS 6.2.8).
  - Unauthenticated OpenAPI / Swagger API schema endpoints disabled in production mode (`ENVIRONMENT=production` or `IS_PRODUCTION=true`, ASVS 13.1.5).

---

## 6. OWASP Top 10 for LLMs Hardening

OpenOptOut integrates local and provider-based AI drafting assistants to parse broker opt-out flows while defending against large language model vulnerabilities:

- **LLM01: Prompt Injection Defense**:
  - Untrusted data broker HTML/text is strictly enclosed inside structured `<broker_page_content>` delimiters in `spec_drafter.py`.
  - System prompts instruct the LLM that content within delimiters is untrusted observational data and cannot override system instructions or tool definitions.
  - Operator UI (`SpecHelpers.jsx`) displays explicit visual warning banners reminding administrators that assistant suggestions must be reviewed before saving.
- **LLM10: Unbounded Consumption Defense**:
  - JSON Schema generation (`draft_schema()` in `core/ai_helpers.py`) strictly enforces bounded properties with explicit `maxLength` limits on strings and `maxItems` limits on arrays.
  - Maximum output token caps (`max_output_tokens=16000`, `max_tokens=16000`) enforced across OpenAI, Anthropic, and compatible provider invocations to eliminate unbounded resource exhaustion and token depletion attacks.

