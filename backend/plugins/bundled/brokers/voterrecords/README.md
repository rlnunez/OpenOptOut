# VoterRecords

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://voterrecords.com |
| **A person may need to** | pick their own record |
| **Response window** | 45 days (CCPA) |
| **Source** | Process per redact.dev's VoterRecords removal guide (updated 2026-09-10). |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

The opt-out goes on the checklist with these steps, and a one-time email address so any reply and confirmation link are handled automatically:

> Open https://voterrecords.com, search for `{full_name}`, open your own record and use the site's opt-out or "Control" link on it. Use `{contact_email}` wherever it asks for an email address. Then press "I've done this".

VoterRecords republishes public voter rolls. The "Record Opt-Out" link is at the bottom of each record and has an hCaptcha. It removes the house number, phone and email from the page; the name stays, because voter rolls are public.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
