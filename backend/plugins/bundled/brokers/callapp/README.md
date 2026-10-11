# CallApp

| | |
|---|---|
| **Method** | Automatic (a robot check may wait on the CAPTCHAs page) |
| **Lists people by** | phone number |
| **Opt-out page** | https://callapp.com/how-to/unlist-phone-number |
| **Response window** | 45 days (CCPA) |
| **Source** | CallApp support article 'Can I wipe my information from CallApp' and its unlisting page. |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

CallApp's unlisting page asks for the phone number. Once unlisted, CallApp stops showing the number in its caller ID. If the page asks anything else, the opt-out moves to the checklist.
