# Administrator & Operations Guide

Welcome to the **OpenOptOut Administrator & Operations Guide**. This documentation covers system installation, security hardening, authentication, automated updates, backups, and operational monitoring for OpenOptOut instances.

---

## Deployment & Networking

- **[Setup Wizard & Initial Onboarding](database.md#backend-selection)**  
  Guided first-run configuration offering a top-level choice between Express Setup (zero-touch SQLite, safe network defaults for home users) and Advanced Setup (enterprise PostgreSQL, custom reverse proxies, mail transports, and branding), with Master Key (`SECRET_KEY`) verification.
- **[Automated HTTPS & Reverse Proxies](https.md)**  
  Comprehensive guide to running OpenOptOut behind Caddy, Traefik, Nginx, or Cloudflare Tunnel (including Authenticated Origin Pulls, client-certificate mTLS, and custom WAF rate limiting).
- **[Native Bare-Metal Installation](native-install.md)**  
  Instructions for deploying directly on Linux (systemd), macOS, and Windows Server (IIS / Windows Service).
- **[Hardware Sizing & Benchmarks](hardware-sizing.md)**  
  Empirical memory scaling profiles, multi-worker sizing, and minimum/recommended specifications for Playwright Firefox.
- **[Database Administration](database.md)**  
  Configuring encrypted SQLite (SQLCipher) for personal/family setups or enterprise PostgreSQL for multi-tenant organizations.

---

## Identity, Access & Governance

- **[Single Sign-On (SSO)](sso.md)**  
  Connecting OpenOptOut to OIDC providers (Google Workspace, Microsoft Entra ID / Azure AD, Keycloak) and SAML 2.0 / LDAP identity stores.
- **[Roles & Permissions](roles.md)**  
  Super admin, manager, family organizer, and member privilege separation.
- **[Housing Communities & Neighborhoods](communities.md)**  
  Onboarding residential communities, HOA groups, and neighborhood associations with address verification.
- **[Terms of Service & Privacy Policy](terms.md)**  
  Configuring customizable terms, privacy disclosures, and mandatory user agreements.

---

## Maintenance & Monitoring

- **[System Updates & Auto-Updater](updater.md)**  
  Automated GitHub release checks, safe maintenance drain mode, and instant automated rollback.
- **[Upgrading Guide](upgrading.md)**  
  Manual upgrade procedures, additive database migrations, and release verification.
- **[Encrypted Backups](backups.md)**  
  Configuring AES-256-GCM encrypted database dumps to local disks, SFTP, AWS S3, Cloudflare R2, Proton Drive, Box, and pCloud.
- **[Monitoring, Metrics & Health](monitoring.md)**  
  Prometheus scrape endpoints, structured JSON logging, and container health probes.
- **[Stats API](stats-api.md)**  
  Aggregated metrics and privacy reporting endpoints for organizational administrators.

