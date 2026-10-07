# Security policy

OpenOptOut stores some of the most sensitive data people have: names,
addresses, phone numbers and email accounts. Security reports are very welcome.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately instead:
**[Report a vulnerability](https://github.com/rlnunez/OpenOptOut/security/advisories/new)**
(the repository's **Security** tab → **Report a vulnerability**).

Please include:

- what the problem is and what an attacker could do with it
- steps to reproduce it (a request, a script, or a screenshot is fine)
- the version or commit you tested (shown at `/api/health`)

You should get a reply within 7 days. Once a fix is released, you'll be credited
in the advisory unless you'd rather stay anonymous.

## Scope

In scope: the backend API, the web interface, the plugin sandbox (bubblewrap,
seccomp, gRPC capability broker), encryption at rest, sign-in (local, OIDC,
SAML, LDAP, SIP2), distributed workers, the installers and the Docker images.

Out of scope: data brokers' own websites, and problems that need an already
compromised server or administrator account (unless they let someone escape the
plugin sandbox or cross from one family or library branch into another).

## Memory Hygiene & Host Hardening

OpenOptOut implements strict defense-in-depth against data leakage from process memory:
- **Core Dump Suppression**: Core dumps are disabled at the process level (`RLIMIT_CORE = 0`), container level (`ulimits: core: 0`), and systemd service level (`LimitCORE=0`) so patron PII is never dumped to disk on crash.
- **In-Memory Zeroization**: Decrypted secrets and patron records are wrapped in ephemeral scoped buffers (`core.memory_hygiene.SecureBuffer`) and wiped with zeros immediately upon block completion.
- **Encrypted Swap**: Host operators are strongly advised to run on pure RAM or configure ephemeral encrypted swap via `/etc/crypttab` (`/dev/urandom` key) to prevent cleartext memory paging.

## Automated scanning

Every change is checked by free automated scanners. See
[docs/SECURITY_SCANNING.md](docs/SECURITY_SCANNING.md).

