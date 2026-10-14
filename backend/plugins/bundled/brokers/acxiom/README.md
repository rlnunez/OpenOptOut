# Acxiom

| | |
|---|---|
| **Method** | Automatic (a robot check may wait on the CAPTCHAs page) |
| **Opt-out page** | https://www.acxiom.com/optout/ |
| **A person may need to** | click an emailed confirmation link (OpenOptOut does this) |
| **Response window** | 45 days (CCPA) |
| **Source** | Process per redact.dev's Acxiom removal guide (updated 2026-09-10). |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

OpenOptOut opens the opt-out page and fills in the form by its labels. If the form asks for something it doesn't recognize, it stops and the opt-out moves to the checklist. A robot check waits on the CAPTCHAs page.

Acxiom is a marketing data wholesaler, so opting out here cuts off data that flows on to many other brokers. The form asks for name, address, phone and email, then Acxiom sends a confirmation link from noreply-optout@acxiom.com. If the form fails, consumeradvo@acxiom.com is Acxiom's consumer advocate address.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
