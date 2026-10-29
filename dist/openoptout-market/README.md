# OpenOptOut Community Marketplace (`openoptout-market`)

> **Official community catalog and add-on registry for OpenOptOut privacy automation plugins, broker specs, and language packs.**

This repository hosts the official declarative registry (`plugins.json`) and automated catalog index (`index.json`) consumed by OpenOptOut instances worldwide.

---

## How It Works

1. **Decentralized Hosting:** Plugin authors host and maintain plugins in their own GitHub repositories.
2. **Automated Release Tracking:** When authors publish a tagged GitHub release (e.g., `v1.1.0`), this repository automatically indexes the release, computes SHA-256 integrity checksums, and updates `index.json`.
3. **One-Click Installation:** Self-hosted OpenOptOut instances fetch `index.json` and allow administrators to browse, install, and update plugins directly from the web interface.

---

## How to Submit a Plugin

Submitting a plugin is a **one-time process**. Once your repository is registered in `plugins.json`, all future releases and updates are synced automatically without requiring new pull requests!

### Step 1: Build Your Plugin
Author your plugin according to OpenOptOut's declarative standards.

- **Using an AI Coding Agent?** Install the verified agent skill directly:
  - [OpenOptOut Broker Development & Repair Plugin on Agensii](https://www.agensi.io/skills/openoptout-broker-development-and-repair-plugin)
  - [Local Skill Package (`dist/agensii-skill`)](https://github.com/rlnunez/OpenOptOut/tree/main/dist/agensii-skill)
- **Official Core Development Documentation:**
  - [Broker Plugin Authoring Guide](https://github.com/rlnunez/OpenOptOut/tree/main/broker-plugins)
  - [Declarative Spec Format (`broker_spec.py`)](https://github.com/rlnunez/OpenOptOut/blob/main/backend/core/interpreter/broker_spec.py)
  - [Instructions for Coding Agents (`AGENTS.md`)](https://github.com/rlnunez/OpenOptOut/blob/main/AGENTS.md)

Key compliance standards to follow:
- Strict **COPPA & GDPR data minimization** (only requesting mandatory fields).
- **Prohibited credentials check** (never automating SSNs, government IDs, or passwords).
- **Isolated email aliases** (`contact_email` vs `email`).
- **Semantic, anti-brittle selectors** (`[name=...]`, button text).

### Step 2: Publish a Release on Your Repository
1. Push your plugin files (`manifest.json`, `spec.json`, and `README.md`) to your GitHub repository.
2. In your repo, go to **Releases** → **Draft a new release**.
3. Create a tag (e.g., `v1.0.0`), attach your packaged `.zip` file (or let GitHub create the release archive), and publish.

### Step 3: Open a Pull Request
1. Fork this repository (`openoptout-market`).
2. Add your plugin entry to `plugins.json`:
   ```json
   {
     "id": "my_broker",
     "name": "My Broker Name",
     "description": "Automated privacy opt-out for My Broker Name.",
     "repo": "your-username/openoptout-my-broker",
     "category": "brokers",
     "author": "Your Name / Organization",
     "tier": 2
   }
   ```
3. Open a Pull Request.
4. Our automated CI will run `tools/validate_submission.py` to verify your submission.
5. Once merged by a maintainer, your plugin will be live in the marketplace within hours!

---

## How to Push Updates

**You do NOT need to open a new PR to push updates!**

Whenever you update your selectors, repair a flow, or add features:
1. Commit the changes to your own repository.
2. Bump the `version` in your `manifest.json`.
3. Publish a new **GitHub Release** (e.g., `v1.1.0`).
4. Our automated GitHub Action runs every 6 hours, detects your new release, verifies checksums, and deploys the update to `index.json`.

---

## Categories

| Category | Description |
|---|---|
| `brokers` | Declarative opt-out removal specs for people-search sites and data brokers. |
| `languages` | Community language packs and regional legal letter translations. |
| `captcha` | Third-party solver extensions and human-in-the-loop bridges. |
| `email` | Inbound verification parsers and webmail bridges. |
| `themes` | High-contrast, accessibility, and visual customization themes. |

---

## Security & Quality Guidelines

All community plugins must adhere to OpenOptOut's core security invariants:
- **Declarative Only:** Broker plugins must be pure JSON specs (`spec.json`). Executable Python/Bash scripts are prohibited in broker add-on paths.
- **Sandbox Isolation:** All plugins execute inside OS-level namespaces (bubblewrap/seccomp).
- **Zero Real PII in Fixtures:** Never commit personal details, real emails, or live credentials.

---

## License

The marketplace registry, submission tools, and catalog index are licensed under the [MIT License](LICENSE). Individual plugins retain their authors' declared open-source licenses.

