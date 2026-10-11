# Truecaller

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Lists people by** | phone number |
| **Opt-out page** | https://www.truecaller.com/unlisting |
| **Response window** | 45 days (CCPA) |
| **Source** | Truecaller's unlisting page; steps per meprism's 2026 Truecaller opt-out guide. |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

Unlisting is per number and usually takes about 24 hours. A number can come back if someone with Truecaller uploads their contacts again, so it's rechecked like any other listing.

## The checklist steps

> Truecaller shows your name to people you call. Open https://www.truecaller.com/unlisting and unlist each of these numbers, one at a time, with the country code: {all_phones}. Finish the robot check for each. If you use the Truecaller app yourself, deactivate your account in the app first, then uninstall it, or the unlisting won't stick. Then press "I've done this".
