# Changelog

All notable changes to OpenOptOut are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Cloudflare Authenticated Origin Pulls (AOP):** mTLS origin pull verification for Caddy, Traefik, and native Nginx using the official Cloudflare Authenticated Origin Pull CA certificate, ensuring origin servers admit only legitimate traffic from the owner's Cloudflare zone.
- **Cloudflare Tunnel WAF Rulesets:** Preconfigured edge rate-limiting (60 req/min auth endpoints, 1200 req/min site-wide) and WAF firewall rules (`deploy/cloudflare/tunnel-waf-ruleset.json`) with automated CLI deployment helper (`apply-tunnel-waf.sh`).
- **Updater Automated Rollback & Revert:** The companion updater daemon (`openoptout-updater`) now takes pre-update safety snapshots of running container images, SQLite databases, and settings before applying upgrades. If container recreation or post-upgrade health checks fail within 90 seconds, it automatically reverts to the previous release. Super administrators can also trigger on-demand rollbacks via `POST /api/system/updates/rollback` or the UI.
- **Audience-Organized Documentation & MkDocs:** Restructured documentation into User/Family, Administrator, and Developer guides, backed by MkDocs Material with client-side offline search, dark/light themes, and slimmed roadmap.

### Changed
- **Slimmed Roadmap:** Active `ROADMAP.md` now tracks only in-progress and planned items, archiving completed historical milestones to `docs/archive/COMPLETED_ROADMAP.md`.
- **SearXNG Master Secret Decoupling:** Auto-generated SearXNG master secret with dynamic entropy length, separate from the primary application master key.

---

## [0.11.0] — 2026-10-14

### Added
- **Distributed Worker Fleet (Roadmap Item 7):** Scalable stateless Playwright execution workers running in isolated containers, communicating over Redis or in-process priority queues (`removal_high`, `removal_normal`, `discovery`, `retry`), with HMAC-SHA256 signed envelopes and automated lease reclamation.
- **Administrative Worker Fleet Dashboard:** Live capacity tracking, active slots, queue depths, node health metrics, and remote drain controls in `frontend/src/pages/WorkerFleet.jsx`.
- **Universal Localization & RTL (Roadmap Items 17, 52, 53, 56):** 17 fully translated language packs (English, Spanish, French, German, Portuguese, Russian, Ukrainian, Polish, Arabic, Hindi, Urdu, Swahili, Indonesian, Vietnamese, Tagalog, Korean, Chinese) with full right-to-left (RTL) mirroring and logical Tailwind classes.
- **Pluggable Opt-Out Letters (Roadmap Item 58):** Jurisdiction-tailored statutory letters (CCPA, GDPR, UK GDPR, LGPD, PIPEDA) decoupled as installable letter plugins.
- **Cloud Backups via Rclone (Roadmap Item 47):** Added encrypted backup export to Proton Drive, Box, pCloud, MEGA, and Nextcloud.
- **Interactive Live Hand-off (Roadmap Items 50, 54):** Live browser session handoff ("Do it here") for CAPTCHAs, two-factor SMS codes, and manual interactive broker steps.
- **Address-Verified Community Registration (Roadmap Item 64):** Self-service registration restricted to residents of housing complexes and homeowner associations via normalized address matching.

### Security
- Memory zeroization for decrypted secrets and tokens (`core/memory_hygiene.py`).
- Ephemeral in-memory tmpfs mounts for temporary browser artifacts (`/tmp:size=512M`).
- Core dump suppression (`RLIMIT_CORE = 0`).

---

## [0.10.0] — 2026-10-01

### Added
- **Declarative Interpretation Engine (Roadmap Items 1, 2):** Core execution runtime interpreting declarative broker specifications without hardcoded broker logic.
- **80 Built-In Broker Plugins:** Curated data broker plugins covering major people-search directories and data aggregators.
- **Family Inboxes & Plus Addressing (Roadmap Item 30):** Per-broker unique alias generation and automated email confirmation handling.
- **State Broker Registries (Roadmap Item 32):** Direct integration with state registries (California DROP, Texas, Vermont) and dead-site detection.
- **Parent Company Cascading (Roadmap Item 10):** Email-first opt-outs targeting parent companies to clear multiple subsidiary storefronts in one batch.
- **SearXNG General Web Search (Roadmap Item 33):** Integrated metasearch engine discovering exposed broker listings without external API leaks.
- **Multi-Destination Encrypted Backups (Roadmap Item 41):** Scheduled AES-256-GCM backups with local, SFTP, S3, Google Drive, OneDrive, and Dropbox storage.

