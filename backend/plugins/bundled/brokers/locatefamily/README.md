# LocateFamily

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://www.locatefamily.com/removal2.html |
| **A person may need to** | have the address of their own listing (Find your listings) |
| **Response window** | 45 days (CCPA) |
| **Source** | Opt-out page listed in The Opt-Out Manual 2026 (thumpersecure/opt-out-manual-2026, public domain). On 2026-10-11 OpenOptOut loaded the page (no details entered) and it was an opt-out form. |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

The opt-out goes on the checklist with these steps, and a one-time email address so any reply and confirmation link are handled automatically:

> Open https://www.locatefamily.com/removal2.html and follow the site's steps for `{full_name}`. Use `{contact_email}` wherever it asks for an email address, so the reply is matched. Then press "I've done this".

The form asks for the listing page's address and the entry number shown at the left of each name, so a person finds the page first. One form per page.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
