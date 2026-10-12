# VeriPages

| | |
|---|---|
| **Method** | Automatic (a robot check may wait on the CAPTCHAs page) |
| **Opt-out page** | https://veripages.com/inner/removal-service |
| **A person may need to** | have the address of their own listing (Find your listings); click an emailed confirmation link (OpenOptOut does this) |
| **Response window** | 45 days (CCPA) |
| **Source** | Process per redact.dev's VeriPages removal guide (updated 2026-09-10). |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

OpenOptOut opens the opt-out page and fills in the form by its labels. If the form asks for something it doesn't recognize, it stops and the opt-out moves to the checklist. A robot check waits on the CAPTCHAs page.

Needs the address of the person's own VeriPages listing (Find your listings). A Cloudflare Turnstile check may wait for a person. removal@veripages.com takes requests by email.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
