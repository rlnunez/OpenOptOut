# PeopleFinders

| | |
|---|---|
| **Method** | Automatic (a robot check may wait on the CAPTCHAs page) |
| **Opt-out page** | https://www.peoplefinders.com/opt-out |
| **A person may need to** | click an emailed confirmation link (OpenOptOut does this) |
| **Also covers** | privateeye.com, publicrecordsnow.com |
| **Response window** | 45 days (CCPA) |
| **Source** | Process per redact.dev's PeopleFinders removal guide (updated 2026-09-24). |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

OpenOptOut opens the opt-out page and fills in the form by its labels. If the form asks for something it doesn't recognize, it stops and the opt-out moves to the checklist. A robot check waits on the CAPTCHAs page.

Covers PrivateEye and PublicRecordsNow too. The confirmation link must be clicked within 24 hours. PeopleFinders says it honors only residents of states with privacy laws (about 19), so for others the request may be refused.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
