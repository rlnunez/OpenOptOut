# Clustal

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://www.clustal.org/privacy-control |
| **A person must** | Copy their full-record address and submit the privacy form |
| **Response window** | 45 days (CCPA) |
| **Source** | [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) Clustal entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The opt-out goes on the checklist with the steps below and, where the site asks for an email, a one-time address.
2. Replies to that address are matched to the request, and any confirmation link is clicked automatically.

## The checklist steps

> Search clustal.org for `{full_name}`, open "view full record", and copy that page's address (the search result's address won't work). Open clustal.org/privacy-control, paste it, press "remove my info", enter `{contact_email}` and press "remove my info" again. Clustal emails a link to finish; OpenOptOut clicks it for you. Then press "I've done this".

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
