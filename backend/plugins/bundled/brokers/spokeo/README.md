# Spokeo

| | |
|---|---|
| **Method** | Web form, automated |
| **Opt-out page** | https://www.spokeo.com/optout |
| **A person must** | Nothing, if a CAPTCHA solver is installed; otherwise tick Spokeo's "I'm not a robot" box from the CAPTCHA queue |
| **Response window** | 45 days (CCPA) |
| **Source** | [Blake104/OptOut](https://github.com/Blake104/OptOut) `spokeo.yml` (AGPL-3.0), verified upstream 2026-05-10; [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) Spokeo entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The app opens Spokeo's opt-out page and fills in the listing's address and a one-time email address.
2. Spokeo's reCAPTCHA is handed to a CAPTCHA solver plugin, or to the CAPTCHA queue for a person.
3. The form is submitted. Spokeo emails a confirmation link to the one-time address; OpenOptOut clicks it and only then counts the opt-out as confirmed.

## Notes

Needs the address of the person's own Spokeo listing (Discovery → Find your listings). Spokeo shows a reCAPTCHA checkbox: with a CAPTCHA solver plugin the flow finishes itself, otherwise it waits in the CAPTCHA queue. Spokeo then emails a confirmation link to the one-time address, which OpenOptOut clicks. Links expire within about a day. FreePeopleDirectory listings are removed through this same page. Spokeo may keep data for paid accounts even after it disappears from free search.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
