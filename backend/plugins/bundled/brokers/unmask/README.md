# Unmask

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://unmask.com/opt-out |
| **A person may need to** | click an emailed confirmation link (OpenOptOut does this); pick their own record |
| **Response window** | 45 days (CCPA) |
| **Source** | Sister site of CheckPeople (same suppression tool), per redact.dev's CheckPeople guide (updated 2026-10-05). On 2026-10-11 OpenOptOut loaded the page (no details entered) and it was an opt-out form. |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

The opt-out goes on the checklist with these steps, and a one-time email address so any reply and confirmation link are handled automatically:

> Open https://unmask.com/opt-out and follow the site's steps for `{full_name}`. Use `{contact_email}` wherever it asks for an email address, so the reply is matched. Then press "I've done this".

Same suppression tool as CheckPeople: an email address first, then a verification link that leads to the record search.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
