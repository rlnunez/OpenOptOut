# RocketReach

| | |
|---|---|
| **Method** | Automatic (a robot check may wait on the CAPTCHAs page) |
| **Lists people by** | email address |
| **Opt-out page** | https://rocketreach.co/remove-profile |
| **Response window** | 45 days (CCPA) |
| **Source** | Steps per Redact's RocketReach removal guide; fallback privacy@rocketreach.co. |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

RocketReach files people by email. One request per saved email address. If a profile exists, RocketReach sends a link to that address, and the opt-out only finishes after the link is opened and the next page is completed. If that inbox is connected to OpenOptOut, the link is clicked for you.
