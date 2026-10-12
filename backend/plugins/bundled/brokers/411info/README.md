# 411.info

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://411.info/manage/ |
| **Response window** | 45 days (CCPA) |
| **Source** | Opt-out page listed in The Opt-Out Manual 2026 (thumpersecure/opt-out-manual-2026, public domain). The page couldn't be loaded for a check on 2026-10-11 (the site blocks automated readers), so this plugin ships turned off. |
| **Starts** | Turned off: run a rehearsal, then turn it on (Brokers page) |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

The opt-out goes on the checklist with these steps, and a one-time email address so any reply and confirmation link are handled automatically:

> Open https://411.info/manage/ and follow the site's steps for `{full_name}`. Use `{contact_email}` wherever it asks for an email address, so the reply is matched. Then press "I've done this".

## Why it starts turned off

Nobody could check this opt-out page yet. Sites like this change hands; some have been taken over by court order. Before turning it on, open the page and make sure it's still the site's own opt-out form, or run a rehearsal (Spec helpers), which uses made-up details and stops before the last click.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
