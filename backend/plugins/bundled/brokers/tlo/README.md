# TransUnion (TLOxp)

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://service.transunion.com/dss/ccpa_optout.page |
| **A person may need to** | decide whether to share an ID number (OpenOptOut never fills it in) |
| **Response window** | 45 days (CCPA) |
| **Source** | TransUnion's California privacy opt-out page, listed in The Opt-Out Manual 2026 (public domain). |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

The opt-out goes on the checklist with these steps, and a one-time email address so any reply and confirmation link are handled automatically:

> Open https://service.transunion.com/dss/ccpa_optout.page and follow the site's steps for `{full_name}`. The site asks for a Social Security or driver's license number, which OpenOptOut never fills in; only finish it if you're comfortable sharing that with them. Use `{contact_email}` if it asks for an email address. Then press "I've done this".

TLOxp is TransUnion's investigations database. The opt-out page asks for identifying numbers that OpenOptOut never fills in, so a person decides whether to finish it. This doesn't affect TransUnion credit reports.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
