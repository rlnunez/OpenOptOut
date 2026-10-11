# Cyber Background Checks

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://www.cyberbackgroundchecks.com/removal |
| **A person must** | Find their record and remove it |
| **Response window** | 45 days (CCPA) |
| **Source** | [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) Cyber Background Checks entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The opt-out goes on the checklist with the steps below and, where the site asks for an email, a one-time address.
2. Replies to that address are matched to the request, and any confirmation link is clicked automatically.

## The checklist steps

> Search cyberbackgroundchecks.com for `{full_name}`. If you're listed, open cyberbackgroundchecks.com/removal and remove the record, giving `{contact_email}` as the email address. Then press "I've done this".

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
