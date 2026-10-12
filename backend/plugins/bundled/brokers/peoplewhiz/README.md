# PeopleWhiz

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://www.peoplewhiz.com/optout |
| **A person may need to** | decide whether to share an ID number (OpenOptOut never fills it in); possibly send a letter or fax |
| **Response window** | 45 days (CCPA) |
| **Source** | Process per redact.dev's PeopleWhiz removal guide (updated 2026-09-09). |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

The opt-out goes on the checklist with these steps, and a one-time email address so any reply and confirmation link are handled automatically:

> Open https://www.peoplewhiz.com/optout and follow the site's steps for `{full_name}`. Use `{contact_email}` wherever it asks for an email address, so the reply is matched. Then press "I've done this".

PeopleWhiz may ask for a copy of an ID by fax or mail. If it does, black out the ID number and photo before sending, or skip it: OpenOptOut never sends ID documents.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
