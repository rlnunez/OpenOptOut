# Opt-out letters

The wording OpenOptOut sends to data brokers, one file per law. `core/legal_letters.py` picks the letter and fills it in.

**Every letter here is a draft.** None has been reviewed by a lawyer. Each file's `review_status` stays `"draft"` until one has, and its `review_note` says what to check. Translations other than English were written as machine-quality drafts and need a native-speaking lawyer as well. If you can help, see "A call to law librarians" in `docs/LEGISLATION.md`.

## Which letter a broker gets

The letter depends on **the broker**, not on the language the family uses the app in:

| Broker's jurisdiction | Letter | Written in |
|---|---|---|
| `US`, person lives in California | `ccpa.json` | English |
| `US`, anywhere else | `us.json` | English |
| `EU`, `EEA` or an EU/EEA country | `gdpr.json` | the country's language when there's a version (fr, de, es, it, nl, pt), else English |
| `UK` / `GB` | `uk_gdpr.json` | English |
| `BR` | `lgpd.json` | Brazilian Portuguese |
| `CA` (Canada) | `pipeda.json` | English; French for `CA-QC` |
| anything else | `generic.json` | English |

A broker's jurisdiction and legal language come from its spec (`jurisdiction`, `legal_language`) or, for a parent company, from the Parent companies page. A broker add-on can ship its own letter per language in `email_templates`; that is used before these.

When no version exists in the legal language asked for, the letter is sent in the template's own language. No "this isn't translated yet" note is added: for a US broker English is the authoritative language.

## File format

```json
{
  "id": "gdpr",
  "title": "European Union / EEA — GDPR",
  "law": "General Data Protection Regulation (EU) 2016/679",
  "legal_basis": ["gdpr"],
  "jurisdictions": ["EU", "FR", "..."],
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

Every body must use `{broker}`, `{scope}`, `{property_note}`, `{identifiers}`, `{reference}` and `{full_name}`; every subject `{full_name}` and `{ref_tag}`. The test suite (`legal.letter_follows_broker_not_interface`) checks this, and that `_parts.json` has the same pieces in every language.

## Adding a language or a law

1. Add the language to the letter's `languages`, and to `_parts.json` if it isn't there.
2. For a new law, add a file and a branch in `choose_template()` in `core/legal_letters.py`, and its default language in `JURISDICTION_LANGUAGE` in `core/interpreter/broker_spec.py`.
3. Leave `review_status` as `"draft"` and say in `review_note` what a lawyer should check.
