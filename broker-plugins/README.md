# Broker plugins

Each data broker is its own plugin in its own folder, versioned on its own. Changing one broker never touches another.

The plugins ship with the app and install themselves at startup, so they live with the other built-in plugins:

```
backend/plugins/bundled/brokers/
├── spokeo/           manifest.json, spec.json, README.md
├── mylife/  beenverified/  radaris/  whitepages/  ...
broker-plugins/
├── _template/        copy this into backend/plugins/bundled/brokers/<id>/ to start a new broker
└── tools/
    ├── validate.py   checks every plugin with the app's validators, the rules below, and a dry run
    └── package.py    builds one upload-ready zip per plugin into dist/ (to update a server by hand)
```

At startup each built-in plugin is installed and its broker created (turned on). On an upgrade the copy is refreshed. A plugin an admin turned off stays off, and an admin's own plugin with the same id is never replaced.

## Two kinds of plugin

| Kind | `method` | What happens |
|---|---|---|
| **Automated** | `form` | The app fills and submits the broker's form. CAPTCHAs go to a solver plugin or the CAPTCHA queue; a `pause_for_human` step hands the rest to a person. |
| **Guided** | `manual` | The broker needs something only a person can do (pick their record, answer a call, solve several CAPTCHAs). The request goes on the checklist with `instructions`. Use `{contact_email}` in them: the person gives that one-time address, so the broker's reply is matched and its confirmation link is clicked automatically. |

| Broker | Kind | A person must |
|---|---|---|
| Spokeo | Automated | Nothing with a CAPTCHA solver; otherwise the CAPTCHA queue |
| MyLife | Automated | Nothing with a CAPTCHA solver; otherwise the CAPTCHA queue |
| BeenVerified | Automated, then a person | Pick their record and solve a CAPTCHA |
| Radaris | Automated, then a person | Pick their profile |
| Whitepages | Guided | Answer an automated phone call |
| FastPeopleSearch, TruePeopleSearch, Nuwber, That's Them, USPhoneBook, SmartBackgroundChecks, SearchPeopleFree, FamilyTreeNow, Cyber Background Checks, Clustal, Social Catfish | Guided | Find their record and submit the site's form |

None of these has been run against the live site by OpenOptOut yet (`last_verified` is empty). The automated flows use selectors that were verified upstream in May 2026.

## Rules

- The folder name, `manifest.id`, `manifest.broker_id` and `spec.broker_id` are the same.
- `spec.name` matches the broker's name in the app, so installing updates it instead of creating a duplicate.
- `spec.source` says where the opt-out details came from. `spec.last_verified` is the date someone last ran the flow against the live site (`YYYY-MM-DD`), or empty if nobody has yet.
- Bump `manifest.version` on every change.
- Use the field `contact_email` for "where should we send your confirmation" boxes (and in guided `instructions`). It fills in a unique address for that one opt-out (`jane+oo7f3k2a9@gmail.com` on inboxes that allow it), so the reply is matched to its request. Use `email` only when the form wants an address to remove.
- Use the field `listing_url` for boxes that ask for the address of the person's own listing (Spokeo, Clustal, National Public Data…). It's filled from a listing found by Discovery or pasted under **Find your listings**; if there isn't one yet, the opt-out goes on the checklist asking for it.
- Any point where a person has to take over (pick a listing, answer a phone call) is a `pause_for_human` step whose `text` tells them, in plain words, exactly what to do. The person can do it on the Checklist with **Do it here**: OpenOptOut fills the form again up to that step, shows them the live page, and carries on with the steps after it once they press "I've done this step". So write the text for someone looking at the page ("Enter the 6-digit code the site texted you"), and put any steps that should run afterwards (a final click, `expect_success`) after the pause.
- Don't copy another project's wording. Facts (URLs, selectors, which fields a form needs) are fine; credit the source in `source` and in [CREDITS.md](../CREDITS.md).

## Spec fields beyond the steps

| Field | What it's for |
|---|---|
| `legal_basis` | Which laws apply (`ccpa`, `cpra`, `gdpr`, `vcdpa`, …) |
| `statutory_response_days` | Days the broker has to respond; gives each request a due date |
| `search_url`, `listing_pattern` | The broker's own search page (`{first_name}`, `{last_name}`, `{full_name}`, `{city}`, `{state}`, `{phone}` are filled in). Used for the per-broker links under **Find your listings**, and with `listing_pattern` to check later whether a listing is still up |
| `one_optout_per_email` | The broker accepts one opt-out per email address |
| `accepts_plus_addresses` | Set `false` if the broker's form refuses addresses with a `+`. The app also learns this by itself when a form says the email is invalid, and retries with the plain address |
| `instructions` | For guided (`manual`) plugins: the checklist steps, with `{full_name}`, `{contact_email}`, `{listing_url}`, `{city}`, `{state}`… filled in |
| `requires` | What a person may have to do: `email_confirmation`, `listing_url`, `listing_selection`, `phone_call`, `government_id`, `account`, `payment`, `postal_mail` |

## Commands

```
python broker-plugins/tools/validate.py      # check all plugins (validators, rules, dry run)
python broker-plugins/tools/package.py       # zip each plugin into broker-plugins/dist/
```

Upload a zip under **Settings → Plugins** in the app.
