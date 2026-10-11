# Broker plugins

Each data broker is its own plugin in its own folder, versioned on its own. Changing one broker never touches another.

```
broker-plugins/
├── _template/        copy this to start a new broker
├── radaris/          manifest.json, spec.json, README.md
└── tools/
    ├── validate.py   checks every plugin with the app's own validators plus the rules below
    └── package.py    builds one upload-ready zip per plugin into dist/
```

## Rules

- The folder name, `manifest.id`, `manifest.broker_id` and `spec.broker_id` are the same.
- `spec.name` matches the broker's name in the app, so installing updates it instead of creating a duplicate.
- `spec.source` says where the opt-out details came from. `spec.last_verified` is the date someone last ran the flow against the live site (`YYYY-MM-DD`), or empty if nobody has yet.
- Bump `manifest.version` on every change.
- Use the field `contact_email` for "where should we send your confirmation" boxes. It fills in a unique address for that one opt-out (`jane+oo7f3k2a9@gmail.com` on inboxes that allow it), so the reply is matched to its request. Use `email` only when the form wants an address to remove.
- Use the field `listing_url` for boxes that ask for the address of the person's own listing (Spokeo, Clustal, National Public Data…). It's filled from a listing found by Discovery or pasted under **Find your listings**; if there isn't one yet, the opt-out goes on the checklist asking for it.
- Any point where a person has to take over (pick a listing, answer a phone call) is a `pause_for_human` step whose `text` tells them, in plain words, exactly what to do.
- Don't copy another project's wording. Facts (URLs, selectors, which fields a form needs) are fine; credit the source in `source` and in [CREDITS.md](../CREDITS.md).

## Spec fields beyond the steps

| Field | What it's for |
|---|---|
| `legal_basis` | Which laws apply (`ccpa`, `cpra`, `gdpr`, `vcdpa`, …) |
| `statutory_response_days` | Days the broker has to respond; gives each request a due date |
| `search_url`, `listing_pattern` | The broker's own search page (`{first_name}`, `{last_name}`, `{full_name}`, `{city}`, `{state}`, `{phone}` are filled in). Used for the per-broker links under **Find your listings**, and with `listing_pattern` to check later whether a listing is still up |
| `one_optout_per_email` | The broker accepts one opt-out per email address |
| `requires` | What a person may have to do: `email_confirmation`, `listing_url`, `listing_selection`, `phone_call`, `government_id`, `account`, `payment`, `postal_mail` |

## Commands

```
python broker-plugins/tools/validate.py      # check all plugins
python broker-plugins/tools/package.py       # zip each plugin into broker-plugins/dist/
```

Upload a zip under **Settings → Plugins** in the app.
