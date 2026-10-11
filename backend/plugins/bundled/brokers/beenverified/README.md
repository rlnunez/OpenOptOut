# BeenVerified

| | |
|---|---|
| **Method** | Web form, partly automated |
| **Opt-out page** | https://www.beenverified.com/svc/optout/search/ |
| **A person must** | Pick their own record from BeenVerified's results and solve its CAPTCHA, using the one-time email address shown on the checklist |
| **Response window** | 45 days (CCPA) |
| **Source** | [Blake104/OptOut](https://github.com/Blake104/OptOut) `beenverified.yml` (AGPL-3.0), verified upstream 2026-05-10; [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) BeenVerified entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The app searches BeenVerified's opt-out page for the member's name and state.
2. BeenVerified then needs a person to click the right record and solve a CAPTCHA, so the flow stops with a checklist item that gives the exact steps and a one-time email address.
3. BeenVerified emails a confirmation link to that address. OpenOptOut clicks it and marks the opt-out confirmed.

## Notes

BeenVerified shows search results and a CAPTCHA before the removal form, so a person picks the record. The steps after the pause are kept for when the app can hand a live browser to a person and resume. The state picker is a Material UI list (full state names). A separate opt-out exists for property search: beenverified.com/app/optout/address-search. One opt-out also covers PeopleLooker and PeopleSmart.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
