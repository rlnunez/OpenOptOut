# Data Broker Opt-Out Agent Skill (`data-broker-optout`)

> **Teach AI coding agents (Claude Code, Google Antigravity, Cursor, Codex) to author, audit, and repair safe, declarative, zero-PII data broker opt-out automation plugins.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Compatible with: Claude Code & Antigravity](https://img.shields.io/badge/Compatible-Claude%20Code%20%7C%20Antigravity-orange.svg)](SKILL.md)

---

## 🎯 What This Skill Does

Data brokers and people-search sites store personal details about families, children, and individuals. Writing automated web removal scripts typically leads to two severe failure modes:
1. **Security & Privacy Violations:** Scripts handling real personal data, leaking PII in logs, attempting to bypass legal barriers, or storing sensitive identity credentials.
2. **Brittle Automation:** Flaky scripts that break as soon as frontends change CSS classes or DOM nesting.

This skill equips AI coding agents with a **declarative, sandboxed methodology**:
- **Declarative Form Specs:** Agents generate pure JSON specs with a closed vocabulary of safe primitives (`click_matching`, `fill`, `wait_for`, `pause_for_human`), never unconstrained executable scripts.
- **Strict Data Minimization (COPPA & GDPR):** Enforces field minimization so agents only ask for fields explicitly mandated by the broker's form.
- **Prohibited Credentials:** Hard architectural guard against automating SSNs, driver's licenses, passports, or passwords—mandating manual fallback with clear user instructions.
- **Isolated Email Aliases:** Distinguishes between data to expunge (`email`) and isolated sub-addressed confirmation mailboxes (`contact_email`).
- **Zero-PII Synthetic Rehearsal:** Agents test and debug against live sites using fake identities (`"Jordan Example"`, `@example.invalid`) and halt before final submissions.
- **Anti-Brittle Selectors:** Directs agents to anchor on semantic attributes (`[name=...]`, `[aria-label=...]`, button text) rather than deep positional CSS paths.

---

## 🚀 Quick Install

### 1. Claude Code
Install to your user profile:
```bash
mkdir -p ~/.claude/skills/broker-plugin
curl -fsSL https://raw.githubusercontent.com/rlnunez/OpenOptOut/main/dist/agensii-skill/SKILL.md \
  -o ~/.claude/skills/broker-plugin/SKILL.md
```

### 2. Google Antigravity
Install globally:
```bash
mkdir -p ~/.gemini/antigravity/custom/skills/broker-plugin
curl -fsSL https://raw.githubusercontent.com/rlnunez/OpenOptOut/main/dist/agensii-skill/SKILL.md \
  -o ~/.gemini/antigravity/custom/skills/broker-plugin/SKILL.md
```

### 3. Repository-Specific (Any Agent)
Drop into your workspace:
```bash
mkdir -p .agents/skills/broker-plugin
cp SKILL.md .agents/skills/broker-plugin/SKILL.md
```

---

## 💬 Example Agent Prompts

Once installed, your AI agent automatically activates the skill whenever you ask:

- *"Write an opt-out plugin for FastPeopleSearch by inspecting their form."*
- *"The Whitepages removal button moved. Rehearse the plugin and update the selector."*
- *"Audit the TruePeopleSearch plugin to ensure it complies with COPPA data minimization and doesn't click marketing checkboxes."*
- *"Convert this manual opt-out procedure for LexisNexis into a safe, guided plugin."*

---

## 🛠️ Standalone Validator CLI

Included in `tools/validate.py` is a zero-dependency Python validator that verifies plugin integrity, requirement synchronization, and safety invariants:

```bash
# Validate the template or any plugin folder
python3 tools/validate.py _template/
python3 tools/validate.py examples/mock-broker/
```

Checks performed:
- [x] Schema integrity of `manifest.json` and `spec.json`.
- [x] Matching IDs (`folder_name == manifest.id == spec.broker_id`).
- [x] Requirement synchronization (e.g. `listing_url` and `email_confirmation`).
- [x] Prohibited credential detection (SSNs, government IDs, passwords).
- [x] Selector anti-brittleness warnings.
- [x] Minimum length on human-in-the-loop instructions.

---

## 📁 Package Contents

```text
dist/agensii-skill/
├── SKILL.md                 # Master Agent Skill instructions
├── README.md                # Documentation & install instructions
├── LICENSE                  # MIT License
├── _template/               # Starting template for new plugins
│   ├── manifest.json
│   ├── spec.json
│   └── README.md
├── examples/                # Annotated reference plugin
│   └── mock-broker/
└── tools/
    └── validate.py          # Standalone schema and safety validator
```

---

## 📜 Origin & Upstream

This skill was designed for [OpenOptOut](https://github.com/rlnunez/OpenOptOut), the self-hosted privacy tool for removing family data from broker databases. It is open-sourced under the MIT license to empower any developer or AI agent to build resilient, privacy-preserving automation.
