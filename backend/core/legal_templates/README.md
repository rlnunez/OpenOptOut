# Opt-out letters

The wording OpenOptOut sends to data brokers. Each letter is a **plugin** of type `letters`. The built-in ones are in `backend/plugins/bundled/letters/letter-<law>/`. `core/legal_letters.py` picks the letter and fills it in. This folder only holds `_parts.json`, the pieces every letter shares: identifier labels, the scope paragraph and the reference line.

**Every built-in letter is a draft.** None has been reviewed by a lawyer. Each letter's `review_status` stays `"draft"` until one has, and its `review_note` says what to check. Translations other than English are machine-quality drafts and need a native-speaking lawyer as well. If you can help, see "A call to law librarians" in `docs/LEGISLATION.md`.

## Which letter a broker gets

The first of these that applies wins:

1. **An admin's choice.** Make it under **Admin → Opt-out letters**, per broker or parent company. It wins over everything below, including the add-on's own wording.
2. **The broker add-on's own wording**, from the spec's `email_templates`, in the broker's legal language.
3. **The letter the broker add-on names**, in the spec's `letter` field, for example `"letter": "ccpa"`.
4. **Automatic.** The enabled letter whose `jurisdictions` and `residents_of` fit best, as in the table below.

If the choice in step 1 or 3 isn't available (the letter was turned off or removed), OpenOptOut picks again further down the list. The send never fails because of it.

| Broker's jurisdiction | Letter | Written in |
|---|---|---|
| `US`, person lives in California | `ccpa` (letter-ccpa) | English |
| `US`, anywhere else | `us` (letter-us) | English |
| `EU`, `EEA` or an EU/EEA country | `gdpr` (letter-gdpr) | the country's language when there's a version (fr, de, es, it, nl, pt), else English |
| `UK` / `GB` | `uk_gdpr` (letter-uk-gdpr) | English |
| `BR` | `lgpd` (letter-lgpd) | Brazilian Portuguese |
| `CA` (Canada) | `pipeda` (letter-pipeda) | English; French for `CA-QC` |
| anything else | `generic` (letter-generic) | English |

**How automatic matching scores a letter:**
- an exact jurisdiction (`US-CA`) beats a country (`US`);
- a country beats `EU`/`EEA`;
- `EU`/`EEA` beats `*` (anything).

A letter with `residents_of` applies only to people living in one of those US states, and it beats the same letter without that condition. On a tie, an admin's own letter beats a built-in one. The general letter (`generic`) is always available, even when its plugin is turned off, so every broker can be written to.

The letter's language is the broker's **legal language**, never the family's interface language. When no version exists in that language, the letter's `default_language` is used, with no "not translated" note.

## Adding, replacing or turning off a letter

You manage letters on the **Plugins** page:

- **Turn one off.** That letter is skipped and the next best one is used.
- **Replace a built-in letter.** Upload a letters plugin whose `letter.json` has the same `id` (for example `ccpa`). Once it's enabled, it's used instead of the built-in one.
- **Add a new letter.** Use a new `id`, for example a CCPA letter written as an authorized agent. Choose it for particular brokers under **Opt-out letters**. To make it the automatic choice, give it `jurisdictions` (and `residents_of`).

A letters plugin is data only: no code, permissions or network access. It's checked on upload. A letter that leaves out the identifiers or the signature is refused.

```
my-ccpa-letter/
  manifest.json   {"id": "my-ccpa-letter", "type": "letters", "name": "...", "version": "1.0.0", "author": "...", "description": "..."}
  letter.json     the letter (format below)
```

## letter.json

```json
{
  "id": "gdpr",
  "title": "European Union / EEA — GDPR",
  "law": "General Data Protection Regulation (EU) 2016/679",
  "legal_basis": ["gdpr"],
  "jurisdictions": ["EU", "FR", "..."],
  "residents_of": [],
  "deadline_days": 30,
  "default_language": "en",
  "review_status": "draft",
  "review_note": "What a reviewer should check.",
  "languages": {
    "en": { "subject": "...{full_name}{ref_tag}", "body": "...", "law": "...", "law_state": "..." }
  }
}
```

Placeholders in `subject` and `body`:

| Placeholder | Filled with |
|---|---|
| `{broker}` | the broker or parent company's name |
| `{full_name}` | the person's name |
| `{scope}` | "This request applies to … and these sites: …" (from `_parts.json`) |
| `{property_note}` | the property-records paragraph for property brokers, else nothing |
| `{identifiers}` | names, emails, phones, addresses, an age or age range (never a date of birth) |
| `{law}` | the language's `law` text, or `law_state` when the person's state is known |
| `{reference}` | "Reference ID: …" when the request has one, else nothing |
| `{ref_tag}` | ` [<reference>]` in the subject, so replies can be matched |
| `{state}` | the person's US state (in `law_state`) |

Every body must use `{broker}`, `{scope}`, `{property_note}`, `{identifiers}`, `{reference}` and `{full_name}`. Every subject must use `{full_name}` and `{ref_tag}`. These tests check this: `legal.letter_follows_broker_not_interface`, `legal.letters_are_plugins` and `legal.letter_chosen_per_broker`. They also check that `_parts.json` has the same pieces in every language.

## Adding a language or a law to the built-in letters

1. Add the language to the letter's `languages`, and to `_parts.json` if it isn't there.
2. For a new law, add a folder under `backend/plugins/bundled/letters/` with its `jurisdictions`. Also add the jurisdiction's default language to `JURISDICTION_LANGUAGE` in `core/interpreter/broker_spec.py`.
3. Translate the plugin's description in every language pack (`scripts/plugin_texts.py --check`).
4. Leave `review_status` as `"draft"`, and say in `review_note` what a lawyer should check.
