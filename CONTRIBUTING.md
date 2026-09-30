# Contributing to OpenOptOut

Thanks for your interest in improving OpenOptOut. This project helps people remove their personal data from broker sites, and community contributions — especially broker plugins and coverage — make it meaningfully better for everyone.

## License agreement

OpenOptOut is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. By submitting a contribution (code, documentation, broker data, or otherwise), you agree that your contribution is licensed under the same AGPL-3.0 terms. The original copyright is held by Robert Nunez; contributions are credited through the project's Git history.

## High-value contributions

In rough order of impact:

1. **Security & architecture review.** OpenOptOut incorporates complex security components (Bubblewrap sandboxing, gRPC IPC capability broker, SQLCipher/Fernet encryption, and SSO/SAML/SIP2 authentication). Parts of these subsystems were developed with AI assistance (Claude and Gemini). Thorough human code review by security professionals and experienced developers is vital to catch edge cases, privilege escalations, or cryptographic flaws.
2. **Per-broker form selectors and plugins.** The opt-out engine executes real submissions, but broker forms need declarative specs or plugins mapped so automation can fill and submit them. If you work out the selectors or plugin for a broker, please contribute them. This is the single most useful thing you can add.
3. **New broker plugins & specs.** Found a data broker not covered? Add it via a broker plugin or spec, then open a PR.
4. **Resistant-vendor guides.** If you successfully remove from a difficult broker (Epsilon, Ekata, MyLife, etc.) using a method not already documented, add a note and share it.
5. **ILS / SSO integration reports.** If you deploy against a specific ILS (Koha, Sierra, Symphony, Polaris, Evergreen, Alma) or SSO provider, real-world notes on quirks and working configs are valuable — much of that path is validated for correctness but benefits from field testing.
6. **Bug reports.** Open an issue with your Docker version, browser, deployment type (SQLite/Postgres), and steps to reproduce.

## Ground rules

- **Never commit secrets or PII.** `.env`, `*.db`, `openoptout_settings.json` (and legacy `privacyshield_settings.json`), and cert/key files are excluded by `.gitignore` — keep it that way. Don't paste real patron data, credentials, or personal information into issues or PRs.
- **Keep child-safety and privacy front of mind.** This tool handles sensitive personal data, sometimes for minors. Contributions that would weaken access controls, encryption, or the separation of secrets from the app will not be accepted.
- **Be honest about limitations.** The project deliberately describes bot-evasion, broker compliance, and integration testing status accurately rather than overselling them. Keep that tone.

## Development setup

See the [Local Development Guide](docs/DEVELOPMENT.md) for local development instructions (backend, frontend, and Playwright setup), and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the project structure. For anything touching the database schema, migrations are additive — coordinate destructive changes in an issue first.

## Pull request process

1. Fork and branch from `main`.
2. Make your change with a clear commit message.
3. If you added a broker or selectors, note how you verified them.
4. Open the PR with a description of what changed and why.

Thank you for helping people take back control of their personal data.
