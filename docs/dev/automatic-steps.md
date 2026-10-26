# Automatic broker steps and AI helpers

Data brokers change their opt-out pages without warning, and new brokers appear all the time. OpenOptOut can:

- **Repair** a broker's steps when they stop finding things on its page. This uses the built-in rules first and needs no AI.
- **Draft** steps for brokers nobody has written steps for, with an AI helper you connect.

Both happen on **Admin → Automatic broker steps**.

## The guardrails

- **Rehearsal before use.** Every draft runs in a fresh browser with made-up details (Jordan Example, `rehearsal@example.invalid`). It stops before the click that would send the request, and before any CAPTCHA. That last button is only checked to be on the page. You see a screenshot of the form filled with the made-up details, and the step where it stopped.
- **New steps always wait for an admin.** Nothing drafted for a new broker is used until someone approves it.
- **Repairs apply themselves only in one case.** The rehearsal must pass, and the fix must change nothing but where the steps look (selectors and timeouts). What is typed, which of a person's details are used, where the browser goes, and what a person is told must all stay the same. You get a notice under Broker updates and can undo the fix. Turn this off to approve every fix yourself.
- **No personal details leave.** A helper is sent the broker's public opt-out page (its fields, labels, buttons and opening text) and, for a repair, the current steps and where they broke. Before anything is sent, OpenOptOut checks it against every saved name, email address, phone number and address. If any of them appears, the request is refused and nothing is sent.
- **Drafts are data, not code.** A helper can only answer in the spec's fixed step vocabulary. Before a draft is used, OpenOptOut checks that it:
  - stays on the broker's own site or a known privacy-request platform;
  - never types a fixed email address or number;
  - is flagged when it would give out a date of birth, or when the helper said it wasn't confident.
- **Plugins win when they're updated.** A repair made against version 1.0 of a broker plugin is set aside when version 1.1 installs.

## Helpers

| Helper | What it uses | Default model | Sends to |
|---|---|---|---|
| Claude | Anthropic Messages API with structured outputs | `claude-opus-5-5` (or `claude-sonnet-5-5`, `claude-haiku-5-5`) | `api.anthropic.com` |
| ChatGPT / Codex | OpenAI Responses API with structured outputs | `gpt-6-astra` (or `gpt-6.1-sol`, `gpt-5.3-codex`) | `api.openai.com` |
| Antigravity | Google's Antigravity agent (preview), Gemini Interactions API | `gemini-3.8-flash` | `generativelanguage.googleapis.com` |
| Your own model | Any server with the OpenAI chat-completions API: LM Studio, Ollama, llama.cpp, vLLM, LocalAI, Jan… | whatever you run | the address you give |

**Antigravity** is an agent, not just a model. It may read the broker's public pages itself. OpenOptOut gives it only the read-only `url_context` tool and one function to hand in its draft. It gets no code execution, no search and no sandbox filesystem. Its run is cancelled as soon as the draft arrives.

**Your own model** keeps everything on your network and isn't counted against the monthly limit. Typical addresses:

- LM Studio: `http://localhost:1234/v1`
- Ollama: `http://localhost:11434/v1`

If OpenOptOut runs in Docker, `localhost` is the container itself. Use `http://host.docker.internal:1234/v1`, or the other computer's address (`http://192.168.1.20:1234/v1`).

OpenOptOut asks for the draft's JSON schema. A server that doesn't support that is asked for plain JSON instead. Larger models do noticeably better. A coding model of 30B parameters or more is a reasonable start.

Keys are stored encrypted and never shown again. **Test** sends a one-line request to check a key and model. The online helpers share a monthly request limit, 50 by default.

When more than one helper is on, they're tried in the order you set. The next one is used if one fails.

## Network

The server running OpenOptOut needs to reach the hosts in the table above for the helpers you turn on. It also needs the brokers' sites for rehearsals, which it already reaches for opt-outs.

## Sharing what works

**Save as plugin** downloads an approved draft as a broker plugin `.zip`. You can install it elsewhere, or contribute it: see `broker-plugins/README.md`.

## Coding agents

For people improving OpenOptOut itself with a coding agent:

- `AGENTS.md` (read by Codex and Antigravity, and by Claude Code through `CLAUDE.md`) holds the project's rules.
- `.agents/skills/broker-plugin/SKILL.md` (copied to `.claude/skills/` for Claude Code) is the procedure for writing or fixing a broker plugin.

## How it works

- `backend/core/ai_helpers.py`: the helpers, their settings, the draft schema and the check for personal details
- `backend/core/spec_drafter.py`: page descriptions, rehearsal, the built-in repair rules, checks, decisions, the hourly queue
- `backend/routers/spec_helpers.py`: the API
- `frontend/src/pages/SpecHelpers.jsx`: the page
- The `SpecDraft` table holds every draft. An applied or approved one is used in place of the plugin's steps (`interpreter/script_bridge.get_or_build_broker_spec`).
- A failure classified as `form_not_found` (`core/broker_health.py`) queues one repair per broker per day. The hourly `spec_helpers` job works on them.
- For institutional governance, prompt injection boundaries, and risk management specifications, see [AI Governance Architecture (NIST AI RMF 1.0 & ISO/IEC 42001)](../architecture/ai-governance-nist-iso.md).
