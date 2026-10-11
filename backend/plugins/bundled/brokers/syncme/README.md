# Sync.ME

| | |
|---|---|
| **Method** | Automatic (a robot check may wait on the CAPTCHAs page) |
| **Lists people by** | phone number |
| **Opt-out page** | https://sync.me/unsubscribe/ |
| **Response window** | 45 days (CCPA) |
| **Source** | Form fields and timing per CrabClear's Sync.ME opt-out guide (checked 2026-07-27). |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

One request per saved phone number, each with its own reply address. The form asks for an email and the phone number, then a reCAPTCHA (solved by a CAPTCHA helper, or it waits on the CAPTCHAs page). Sync.ME says removal is done within 24 hours.
