# SearchPeopleFree

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://www.searchpeoplefree.com/opt-out |
| **A person must** | Find each record and remove it |
| **Response window** | 45 days (CCPA) |
| **Source** | [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) SearchPeopleFree entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The opt-out goes on the checklist with the steps below and, where the site asks for an email, a one-time address.
2. Replies to that address are matched to the request, and any confirmation link is clicked automatically.

## The checklist steps

> Search searchpeoplefree.com by name, phone number, address and email; people are often listed more than once. For each record, use searchpeoplefree.com/opt-out, giving `{contact_email}` as the email address. Then press "I've done this".

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
