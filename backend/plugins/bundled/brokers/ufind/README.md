# uFind

| | |
|---|---|
| **Method** | Email (the legal opt-out letter for the person's state) |
| **Sent to** | support@ufind.name |
| **Response window** | 45 days (CCPA) |
| **Source** | BADBOOL uFind entry; on 2026-10-11 the site was live. |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

OpenOptOut emails the broker the opt-out letter for the law that applies to the person (core/legal_letters.py), from a one-time address, and matches the reply. An admin can choose a different letter on the Opt-out letters page.

uFind also has an opt-out page linked from its home page.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
