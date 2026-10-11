# Radaris

| | |
|---|---|
| **Method** | Web form, partly automated |
| **Opt-out page** | https://radaris.com/control-privacy |
| **A person must** | Pick their own profile from the results and click the confirmation link Radaris emails |
| **Response window** | 45 days (CCPA) |
| **Source** | [Blake104/OptOut](https://github.com/Blake104/OptOut) `radaris.yml` (AGPL-3.0), verified upstream 2026-05-12; [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) Radaris entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The app opens the opt-out page, reveals the search form, and searches for the member's name and city.
2. Radaris only shows the **Start Removing** button after someone clicks their own profile, and automation can't click it. The flow stops here and adds a plain-language checklist item for the person.
3. The person enters their email and clicks the link Radaris sends.

If the form fails, BADBOOL suggests emailing customer-service@radaris.com with the listing details and replying to their automatic answer until they confirm removal.

## Changing this plugin

Radaris is a single-page app and changes its markup. If a step fails, check the selectors in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested.
