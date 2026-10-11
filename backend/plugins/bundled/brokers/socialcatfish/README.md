# Social Catfish

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://socialcatfish.com/opt-out/ |
| **A person must** | Collect the listing pages and fill in the opt-out form |
| **Response window** | 45 days (CCPA) |
| **Source** | [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) Social Catfish entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The opt-out goes on the checklist with the steps below and, where the site asks for an email, a one-time address.
2. Replies to that address are matched to the request, and any confirmation link is clicked automatically.

## The checklist steps

> Search socialcatfish.com and note the address of every page that shows you. Open socialcatfish.com/opt-out, scroll to the section for removing pages, emails, phone numbers and addresses, and ask only for things it already shows. Give `{contact_email}` as your email; Social Catfish emails a confirmation link that OpenOptOut clicks for you. Then press "I've done this".

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
