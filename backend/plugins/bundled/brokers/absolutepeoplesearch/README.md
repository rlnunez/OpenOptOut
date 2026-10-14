# AbsolutePeopleSearch

| | |
|---|---|
| **Method** | Automatic (a robot check may wait on the CAPTCHAs page) |
| **Opt-out page** | https://absolutepeoplesearch.com/public.php?funct=optout |
| **A person may need to** | click an emailed confirmation link (OpenOptOut does this) |
| **Response window** | 45 days (CCPA) |
| **Source** | Opt-out page listed in The Opt-Out Manual 2026 (thumpersecure/opt-out-manual-2026, public domain). On 2026-10-11 OpenOptOut loaded the page (no details entered) and it was an opt-out form. |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

OpenOptOut opens the opt-out page and fills in the form by its labels. If the form asks for something it doesn't recognize, it stops and the opt-out moves to the checklist. A robot check waits on the CAPTCHAs page.

The form asks for name, phone, street address, city, state and a verification email; the listing address is optional.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
