# AdvancedBackgroundChecks

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://www.advancedbackgroundchecks.com/removal |
| **A person may need to** | pick their own record |
| **Response window** | 45 days (CCPA) |
| **Source** | Process per redact.dev's AdvancedBackgroundChecks removal guide (May 2026). |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

The opt-out goes on the checklist with these steps, and a one-time email address so any reply and confirmation link are handled automatically:

> Open https://www.advancedbackgroundchecks.com/removal and follow the site's steps for `{full_name}`. Use `{contact_email}` wherever it asks for an email address, so the reply is matched. Then press "I've done this".

A two-form flow: first a search, then a removal form for the chosen record.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
