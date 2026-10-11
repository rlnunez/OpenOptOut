# TruePeopleSearch

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://www.truepeoplesearch.com/removal |
| **A person must** | Solve several CAPTCHAs and pick their record |
| **Response window** | 45 days (CCPA) |
| **Source** | [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) TruePeopleSearch entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The opt-out goes on the checklist with the steps below and, where the site asks for an email, a one-time address.
2. Replies to that address are matched to the request, and any confirmation link is clicked automatically.

## The checklist steps

> Open truepeoplesearch.com/removal. Enter `{full_name}`, your city and state (`{city}`, `{state}`) and `{contact_email}` as the email address, then solve the CAPTCHAs. If your record is listed, press the button to remove it. OpenOptOut clicks any confirmation link sent to that address. Then press "I've done this".

## Notes

TruePeopleSearch.net is a different site with its own opt-out form.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
