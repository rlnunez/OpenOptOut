# Pipl

| | |
|---|---|
| **Method** | Automatic (a robot check may wait on the CAPTCHAs page) |
| **Opt-out page** | https://pipl.com/personal-information-removal-request |
| **Response window** | 45 days (CCPA) |
| **Source** | Process per redact.dev's Pipl removal guide (updated 2026-09-10). |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

OpenOptOut opens the opt-out page and fills in the form by its labels. If the form asks for something it doesn't recognize, it stops and the opt-out moves to the checklist. A robot check waits on the CAPTCHAs page.

The form asks for name, email, request type and a message, with a simple math question and a reCAPTCHA. The math question usually needs a person. privacy@pipl.com takes requests by email.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
