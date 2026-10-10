# Security policy

OpenOptOut stores sensitive patron data including names, addresses, phone numbers, and email accounts. Security reports are welcome.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report privately via **[Report a vulnerability](https://github.com/rlnunez/OpenOptOut/security/advisories/new)** (Security tab → Report a vulnerability).

Include:
- Vulnerability description and security impact
- Reproduction steps (request, script, or screenshot)
- Affected version or commit (from `/api/health`)

You should receive a reply within 7 days. Fixes will credit reporters in the security advisory unless anonymity is requested.

## Scope

In scope: backend API, web UI, plugin sandbox (bubblewrap, seccomp, gRPC broker), encryption at rest, authentication (local, OIDC, SAML, LDAP, SIP2), distributed workers, installers, and Docker images.

Out of scope: data broker websites, and vulnerabilities requiring an already compromised host/admin account (unless enabling sandbox escapes or cross-tenant privilege escalation).

## Memory Hygiene & Host Hardening

OpenOptOut implements defense-in-depth against data leakage from process memory:
- **Core Dump Suppression**: Core dumps disabled at process level (`RLIMIT_CORE = 0`), container level (`ulimits: core: 0`), and systemd service level (`LimitCORE=0`) so patron PII is never written to disk on crash.
- **In-Memory Zeroization**: Decrypted secrets and patron records wrap in ephemeral scoped buffers (`core.memory_hygiene.SecureBuffer`) and zeroize immediately upon block completion.
- **Encrypted Swap**: Operators should run in pure RAM or configure ephemeral encrypted swap via `/etc/crypttab` (`/dev/urandom` key) to prevent cleartext memory paging.

## Automated scanning

Every change is verified by automated scanners. See [docs/SECURITY_SCANNING.md](docs/SECURITY_SCANNING.md).
