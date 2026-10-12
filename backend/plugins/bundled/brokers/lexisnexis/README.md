# LexisNexis

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://consumer.risk.lexisnexis.com/opt |
| **A person may need to** | decide whether to share an ID number (OpenOptOut never fills it in) |
| **Response window** | 45 days (CCPA) |
| **Source** | Process per redact.dev's LexisNexis removal guide (updated 2026-08-10). |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

The opt-out goes on the checklist with these steps, and a one-time email address so any reply and confirmation link are handled automatically:

> Open https://consumer.risk.lexisnexis.com/opt and follow the site's steps for `{full_name}`. The site asks for a Social Security or driver's license number, which OpenOptOut never fills in; only finish it if you're comfortable sharing that with them. Use `{contact_email}` if it asks for an email address. Then press "I've done this".

LexisNexis asks for a Social Security or driver's license number to find the record. OpenOptOut never fills those in, so a person decides whether to finish it. LexisNexis also takes opt-outs by phone at 1-888-497-0011. Some records (for law enforcement and fraud prevention) are kept regardless.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
