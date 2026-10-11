# MyLife

| | |
|---|---|
| **Method** | Web form, automated |
| **Opt-out page** | https://www.mylife.com/privacyrequest |
| **A person must** | Nothing, if a CAPTCHA solver is installed; otherwise solve MyLife's reCAPTCHA from the CAPTCHA queue |
| **Response window** | 45 days (CCPA) |
| **Source** | [Blake104/OptOut](https://github.com/Blake104/OptOut) `mylife.yml` (AGPL-3.0), verified upstream 2026-05-10; [BADBOOL](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) MyLife entry |
| **Last verified by OpenOptOut** | Not yet — run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. The app opens MyLife's privacy request form (an embedded JotForm) and fills in name, a one-time email, birth year, and address.
2. MyLife's reCAPTCHA is handed to a CAPTCHA solver plugin, or to the CAPTCHA queue.
3. The form is submitted. MyLife has 45 days to act; the opt-out counts as confirmed when MyLife replies or someone checks the listing is gone.

## Notes

MyLife's /privacy-portal/ form is broken and /optout/ is gone; /privacyrequest is the working one. Birth year comes from the member's age, so it can be a year off; the field is optional. MyLife may push people toward an account and an ID upload: never needed for this form. Profiles often reappear after 60 to 90 days, so re-run.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
