# OfficialUSA

| | |
|---|---|
| **Method** | Automatic (a robot check may wait on the CAPTCHAs page) |
| **Opt-out page** | https://www.officialusa.com/remove |
| **Response window** | 45 days (CCPA) |
| **Source** | Opt-out page listed in The Opt-Out Manual 2026 (thumpersecure/opt-out-manual-2026, public domain). The page couldn't be loaded for a check on 2026-10-11 (the site blocks automated readers), so this plugin ships turned off. |
| **Starts** | Turned off: run a rehearsal, then turn it on (Brokers page) |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

OpenOptOut opens the opt-out page and fills in the form by its labels. If the form asks for something it doesn't recognize, it stops and the opt-out moves to the checklist. A robot check waits on the CAPTCHAs page.

## Why it starts turned off

Nobody could check this opt-out page yet. Sites like this change hands; some have been taken over by court order. Before turning it on, open the page and make sure it's still the site's own opt-out form, or run a rehearsal (Spec helpers), which uses made-up details and stops before the last click.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
