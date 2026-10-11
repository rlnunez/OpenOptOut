# USPhoneBook

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://www.usphonebook.com/opt-out |
| **A person must** | Find their number and follow the opt-out steps |
| **Response window** | 45 days (CCPA) |
| **Source** | [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) USPhoneBook entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The opt-out goes on the checklist with the steps below and, where the site asks for an email, a one-time address.
2. Replies to that address are matched to the request, and any confirmation link is clicked automatically.

## The checklist steps

> Look up your phone number on usphonebook.com. If you're listed, open usphonebook.com/opt-out and follow the steps, using `{contact_email}` where it asks for an email. If the opt-out page just hangs, email support+optout@usphonebook.com and ask to be removed. Then press "I've done this".

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
