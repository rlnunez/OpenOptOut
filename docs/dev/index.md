# Developer & Contributor Guide

Welcome to the **OpenOptOut Developer Guide**. This documentation provides architectural blueprints, development workflows, plugin authoring tutorials, and security engineering guidelines for contributing to OpenOptOut.

---

## Core System & Architecture

- **[Architecture Overview](architecture.md)**  
  High-level architecture, module decomposition, background tasks, data encryption at rest, and IPC isolation.
- **[Development Workflow](development.md)**  
  Setting up your local environment, managing dependencies, frontend hot reload, and running the unified test runner.
- **[Release Testing & Quality](release-testing.md)**  
  Pre-flight test matrices, automated browser checks, and regression test suites.

---

## Data Broker Plugins & Interpreter

- **[Interpreter Runtime](interpreter.md)**  
  Deep dive into the declarative JSON step engine, Playwright execution, and sandbox isolation.
- **[Writing Broker Plugins](plugins.md)**  
  Authoring guide for creating new data broker add-ons with `manifest.json` and `spec.json`.
- **[Automatic Steps & Drafter](automatic-steps.md)**  
  Interactive browser inspection, auto-generating opt-out specs, rehearsal without submission, and self-healing selectors.

---

## Security & Proposals

- **[Security Policy](../../SECURITY.md)**  
  NIST SP 800-38D (AES-256-GCM), NIST SP 800-132 (PBKDF2), ISO/IEC 27701, COPPA, OWASP ASVS L2, and OWASP LLM Top 10.
- **[Accessibility Guidelines](../../ACCESSIBILITY.md)**  
  WCAG 2.2 Level AAA compliance, high-contrast themes, OpenDyslexic support, self-hosted assets, and RTL layouts.
- **[Security Scanning & Hardening](security-scanning.md)**  
  Static analysis with CodeQL, Semgrep, and bandit; bubblewrap/seccomp plugin sandbox policies; PII encryption rules.
- **[Security Audit Scope](audit-scope.md)**  
  Independent penetration testing boundaries, threat models, cryptographic invariants, and test harnesses (Roadmap Item #68).
- **Proposals & Architecture RFCs**:
  - [Catalog & Localization Design](proposals/catalog-design.md) — Dynamic broker catalog caching and localization architecture.
  - [Builtin Inbox Proposal](proposals/builtin-inbox.md) — Embedded mail receiver engine specifications.

