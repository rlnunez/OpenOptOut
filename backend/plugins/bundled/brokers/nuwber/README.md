# Nuwber

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://nuwber.com/removal/link |
| **A person must** | Find and paste the address of their Nuwber page |
| **Response window** | 45 days (CCPA) |
| **Source** | [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) Nuwber entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The opt-out goes on the checklist with the steps below and, where the site asks for an email, a one-time address.
2. Replies to that address are matched to the request, and any confirmation link is clicked automatically.

## The checklist steps

> Find your page on nuwber.com (searching `{full_name}` and filtering by `{state}` helps) and copy its address. Open nuwber.com/removal/link, paste it, and enter `{contact_email}` as the email address. Nuwber emails a link to confirm; OpenOptOut clicks it for you. Then press "I've done this". If the form won't take the address, email support@nuwber.com with a screenshot of your listing and ask to be removed.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
