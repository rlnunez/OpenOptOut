# Whitepages

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://www.whitepages.com/suppression-requests |
| **A person must** | Answer Whitepages' automated phone call and type in the code |
| **Response window** | 45 days (CCPA) |
| **Source** | [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) White Pages entry; [Blake104/OptOut](https://github.com/Blake104/OptOut) `whitepages.yml` (AGPL-3.0) |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. Needs the address of the person's own Whitepages listing (Discovery → Find your listings).
2. The checklist item lists each click. Whitepages ends with an automated phone call and a code, which only a person can answer.

## The checklist steps

> Whitepages confirms by phone, so you need to do this one. Open whitepages.com/suppression-requests, paste `{listing_url}`, press Next, then "Remove Me". Pick a reason, press Next, and enter the phone number Whitepages shows for you. Answer the automated call and enter the code it gives you. When the page says your request was received, press "I've done this".

## Notes

411.com uses the same opt-out. Whitepages Premium listings may need a separate request through Whitepages support. Listings can come back within about 90 days.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
