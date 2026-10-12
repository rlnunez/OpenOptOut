# Instructions for coding agents

These instructions are for AI coding agents working in this repository: Claude Code (which loads this file through `CLAUDE.md`), OpenAI Codex, Google Antigravity, and others that read `AGENTS.md`. People are welcome to read them too.

OpenOptOut is a self-hosted tool that removes families' personal details from data-broker websites. It is licensed AGPL-3.0 and handles sensitive personal data, sometimes for children. Treat every change as security-relevant.

## Layout

| Path | What's there |
|---|---|
| `backend/` | FastAPI app. `core/` holds the logic, `routers/` the API, `models/database.py` the SQLAlchemy models, and `core/migrations.py` additive migrations. |
| `backend/core/interpreter/` | Broker steps: `broker_spec.py` (the spec format), `compiler.py`, `executor.py` (Playwright) |
| `backend/plugins/bundled/brokers/<id>/` | One plugin per data broker: `manifest.json`, `spec.json`, `README.md` |
| `backend/plugins/bundled/languages/lang-*/` | Language packs. `texts.json` holds screen phrases, and `plugins/<id>.json` translates other plugins. |
| `backend/core/legal_templates/` | Opt-out letters per law. All are drafts awaiting a lawyer's review. |
| `broker-plugins/` | The broker plugin template, `tools/validate.py` and `tools/package.py` |
| `frontend/src/` | React + Vite. Every phrase a person sees goes through `tx()`, `txn()` or `txr()` from `i18n/tx.js`; every date, time and number through `fmtDate()`, `fmtDateTime()`, `fmtClock()` or `fmtNumber()` from `i18n/format.js` (the admin's regional formats). |
| `docs/` | Architecture, plugins, roadmap |

## Commands

```bash
# Backend tests (stdlib runner; sip2.live_tls_server and access.route_gates may fail in sandboxes without TLS/network)
python3 -m backend.tests.run_tests            # everything
python3 -m backend.tests.run_tests --only legal.   # a subset by name

# Broker plugins
python3 broker-plugins/tools/validate.py      # validators, repo rules, dry run, for every built-in broker
python3 scripts/plugin_texts.py --check       # every language pack translates every built-in plugin

# Frontend
cd frontend && npm run check:names && npx vite build
python3 scripts/extract_page_texts.py         # after changing any on-screen phrase; then translate it in every pack
```

## Rules that are never negotiable

- **No personal data outside encrypted storage.** Never log a family member's name, email, phone, address or date of birth. Never write it to disk unencrypted, put it in a test fixture, or commit it. Use made-up details such as "Jordan Example" and `@example.invalid` addresses.
- **Never store SSNs.** Never fill an SSN, a government ID number, a password or a file upload in a broker form.
- **Keep the plugin sandbox.** That means bubblewrap, seccomp, declared `outbound_domains`, and the read_pii + network block. Don't weaken it to make something work.
- **Keep OAuth refresh working.** Never put keys in code. Secrets are stored encrypted (`oauth_engine._encrypt`) and handed only to the code that needs them.
- **CAPTCHA images sent anywhere must have personal details blacked out** (`core/captcha_privacy.py`).
- **Plain language and accessibility.** Write UI text a non-technical person understands. Give every control a label, keep keyboard access, and don't rely on colour alone.
- **Right-to-left works.** Use start/end Tailwind classes (`ms-`, `pe-`, `start-`, `text-end`, `border-s`), never `ml-`/`pr-`/`left-`/`text-right`. Arrow-like icons are mirrored by the list in `frontend/src/index.css`; add new ones there instead of swapping icons by hand. The tests `i18n.rtl_logical_classes` and `i18n.rtl_mirrored_icons` enforce this.
- **Every new on-screen phrase is translated.** Run the extractor, then add the phrase to `texts.json` in all 12 packs. The test `i18n.page_texts_current` enforces this.
- **Database changes are additive.** Add a model (created automatically) or an `ALTER TABLE ... ADD COLUMN` migration. Never drop or rename.
- **Be honest about limits.** If something is untested against a live site or needs a lawyer, say so. Don't claim it works.

## Writing or fixing a broker plugin

Follow the procedure in `.agents/skills/broker-plugin/SKILL.md`. Claude Code has the same file at `.claude/skills/broker-plugin/SKILL.md`. The rules are in `broker-plugins/README.md`, and the spec format is in `backend/core/interpreter/broker_spec.py`.

In short:

1. Copy `broker-plugins/_template/` to `backend/plugins/bundled/brokers/<id>/`. Make the folder name, `manifest.id`, `manifest.broker_id` and `spec.broker_id` the same.
2. Describe the opt-out with the fixed step vocabulary (`STEP_KINDS`) and member fields (`KNOWN_FIELDS`). Use `contact_email` for "where should we reply" boxes, and `listing_url` for "link to your listing". Wherever a person must take over, add a `pause_for_human` step with plain instructions.
3. Set `jurisdiction` and `legal_language` for brokers outside the US (for example, `FR`/`fr` or `BR`/`pt-BR`).
4. Fill in `source`. Leave `last_verified` empty unless you actually ran the flow against the live site.
5. Bump `manifest.version` on every change.
6. Run `broker-plugins/tools/validate.py` and the tests.

**Never test against a live broker with real personal details.** The app's rehearsal, `core/spec_drafter.rehearse()`, runs steps with made-up details and stops before the final click. Use it, or the safe form in `core/interpreter/live_test.py`.

## When a broker's steps break

The app repairs many breakages by itself (`core/spec_drafter.py`). It rehearses the steps, finds the moved field or button by its label, and applies the fix only when nothing but selectors changed and the rehearsal passed. If you fix a bundled plugin by hand, bump its version: a repair made against an older version is then set aside automatically.
