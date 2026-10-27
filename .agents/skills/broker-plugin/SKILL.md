---
name: broker-plugin
description: Write a new OpenOptOut data-broker plugin, or fix one whose opt-out steps stopped working. Use when asked to add a broker, update a broker's opt-out steps, or repair a broken broker flow.
---

# Writing or fixing a broker plugin

Each data broker is a plugin in `backend/plugins/bundled/brokers/<id>/` with `manifest.json`, `spec.json` and `README.md`. The spec is data only: a closed list of step kinds, never code.

OpenOptOut is an AGPL-3.0 tool handling sensitive personal data, including children's records (COPPA). Every plugin change is security-relevant.

## Security, privacy and compliance standards (Non-negotiable)

- **Data minimization (COPPA & GDPR):** Only include fields in `steps` or `instructions` that the specific broker's form strictly requires. Never populate `dob`, `relatives`, `phone`, `street`, or `age` "just in case". Minors' data is handled by this system; minimize every field requested.
- **Strictly prohibited data & mandatory manual fallback:** Never fill, automate, or request SSNs, government IDs, driver's licenses, passports, passwords, or file uploads. If a broker requires any of these (e.g. LexisNexis, TLOxp), the plugin **must** use `method: manual` with clear instructions explaining that the user must submit directly because OpenOptOut never stores or transmits identity documents.
- **Email privacy (`contact_email` vs. `email`):**
  - Use `contact_email` for any "reply / confirmation email" field or in `{contact_email}` instructions. It provides an isolated, sub-addressed alias (`+oo...`) that enables automatic confirmation matching without exposing the person's real email.
  - Use `email` ONLY when the broker's form explicitly asks for "an email address you want removed from our search engine". Never mix them up.
- **No marketing or promotional boxes:** Only check boxes that are strictly mandatory legal certifications (*"I certify under penalty of perjury that I am this individual"*). Never tick optional boxes for marketing, newsletters, or partner offers.
- **Sandbox & domain isolation:** Plugins execute inside a bubblewrap/seccomp sandbox with declared `outbound_domains`. Step URLs and `search_url` must stay strictly on the broker's own domains. Never touch third-party tracking pixels, ad networks, or external analytics.
- **Rehearsal & testing safety:** Never enter real personal details on a broker's site. Rehearse only with synthetic mock data ("Jordan Example", `rehearsal@example.invalid`), and stop before the final submit button (`rehearse()` enforces this).
- **Human-in-the-loop safety:** If a broker flow requires SMS verification codes, CAPTCHA challenges, picking a profile among duplicates, or manual identity confirmation, use a `pause_for_human` step with plain, non-technical instructions.

## 1. Find out how the opt-out works

- Read the broker's privacy policy and opt-out page. Note the opt-out address, every form field, the buttons, any CAPTCHA, any email confirmation, and anything only a person can do (pick their record, answer a phone call, upload ID, pay).
- Check `broker-plugins/README.md` and `CREDITS.md` for an existing source. Record yours in `spec.source`. Facts are fine to use; don't copy another project's wording.
- **Never type a real person's details into a broker's site.** If you need to see a later page, use made-up details ("Jordan Example", `rehearsal@example.invalid`) and stop before the final submit.

## 2. Choose the kind

| Situation | `method` |
|---|---|
| A form the app can fill and submit (CAPTCHAs are fine) | `form` |
| A person must do part of it (phone call, picking a record, ID upload, several CAPTCHAs) | `form` with a `pause_for_human` step, or `manual` with `instructions` |
| The broker takes requests by email | `email`, with `email.to_address` from a source you can cite |

## 3. Write `spec.json`

- Start from `broker-plugins/_template/spec.json`.
- Step kinds come from `STEP_KINDS` in `backend/core/interpreter/broker_spec.py`. Member fields come from `KNOWN_FIELDS` in the same file.
- **Stable selectors:** Prefer semantic attributes: `[name=...]`, `[aria-label=...]`, stable `#id`, or `click_matching` on visible button text. Never use framework-generated dynamic IDs (e.g. `#ember1234`, `.css-19z2x3a`) or deep positional CSS paths (`div:nth-child(...)`).
- `contact_email` goes in any "email for the confirmation / reply" box. `email` is only for an address the person wants removed.
- `listing_url` goes in boxes asking for the person's own listing.
- **Synchronize `requires`:**
  - If any step uses `listing_url`, add `"listing_url"` to `spec.requires`.
  - If the broker requires email confirmation, add `"email_confirmation"` to `spec.requires` and ensure `contact_email` is used.
- Never fill SSNs, ID numbers, passwords or uploads. Never tick marketing boxes.
- `pause_for_human.text` and `instructions` are read by non-technical people. Write numbered-feeling plain steps, name the buttons exactly as the site shows them, and end with: press "I've done this".
- Fill in `legal_basis`, `statutory_response_days`, `requires`, `search_url` and `listing_pattern` when known.
- For brokers outside the US, also fill in `jurisdiction` and `legal_language` (e.g. `FR`/`fr`, `BR`/`pt-BR`). The opt-out letter follows these, not the family's language.
- If the automatic letter is wrong for this broker, name another with `"letter": "<letter id>"` (for example `uk_gdpr`); letters are listed under Admin → Opt-out letters and in `backend/core/legal_templates/README.md`. An admin's choice still wins.
- **Verification integrity:** Leave `last_verified` empty unless you ran it against the live site yourself. Never invent verification dates.

## 4. Write `manifest.json`

- Make `id`, `broker_id` and the folder name identical, with `"type": "brokers"`, a plain-language `description`, and a `version` you bump on every change.
- **Bot mitigation & unchecked brokers:** If the broker's page blocks automated access (Cloudflare, bot walls) or has not been verified live by hand, set `"starts_enabled": false`. The broker will install turned off until confirmed by an admin.

## 5. Translations

The description, `instructions` and `pause_for_human` text are shown to people in their language. After adding or changing them, run `python3 scripts/plugin_texts.py --check`. Then add the translations to `backend/plugins/bundled/languages/lang-*/plugins/<id>.json` in all 12 packs, keeping every `{placeholder}`.

## 6. Check

```bash
python3 broker-plugins/tools/validate.py <id>
python3 scripts/plugin_texts.py --check
python3 -m backend.tests.run_tests --only interpreter.
```

To rehearse against the live page without sending anything:

```python
from backend.core.interpreter.broker_spec import BrokerSpec
from backend.core.spec_drafter import rehearse
import json
print(rehearse(BrokerSpec.from_dict(json.load(open("backend/plugins/bundled/brokers/<id>/spec.json"))), "/tmp/rehearsal.png"))
```

It uses made-up details and stops before the final click. Look at the screenshot.

## Fixing a broken plugin

1. Rehearse it as above. `failed` is the index of the step that no longer finds its element. `page_map` describes the page at that point.
2. Change only what moved, usually the selector. Keep `field`, `value`, `url` and `text` unless the site's flow itself changed.
3. Bump `manifest.version`. Any automatic repair the app made against the old version is set aside when the new version installs.
4. Run the checks.
