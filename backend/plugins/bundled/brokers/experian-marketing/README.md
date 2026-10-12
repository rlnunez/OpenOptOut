# Experian Marketing

| | |
|---|---|
| **Method** | Email (the legal opt-out letter for the person's state) |
| **Sent to** | optout@experian.com |
| **Response window** | 45 days (CCPA) |
| **Source** | Experian's own page on opting out of direct mail marketing, which gives this address. |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

OpenOptOut emails the broker the opt-out letter for the law that applies to the person (core/legal_letters.py), from a one-time address, and matches the reply. An admin can choose a different letter on the Opt-out letters page.

This removes the person from Experian's marketing lists (Experian marks them Do Not Mail for five years). It does not touch credit reports. Prescreened credit offers are a separate opt-out at optoutprescreen.com.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
