# USA-Official

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://usa-official.com |
| **A person may need to** | pick their own record |
| **Response window** | 45 days (CCPA) |
| **Source** | Opt-out page listed in The Opt-Out Manual 2026 (thumpersecure/opt-out-manual-2026, public domain). On 2026-10-11 OpenOptOut loaded the removal page (no details entered); it explains that each listing is removed from its own page. |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

The opt-out goes on the checklist with these steps, and a one-time email address so any reply and confirmation link are handled automatically:

> Open https://usa-official.com, search for `{full_name}`, open your own record and use the site's opt-out or "Control" link on it. Use `{contact_email}` wherever it asks for an email address. Then press "I've done this".

Each listing has its own address and is removed separately.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
