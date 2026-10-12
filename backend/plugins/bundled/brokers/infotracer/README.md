# InfoTracer

| | |
|---|---|
| **Method** | Automatic until the record is picked; a person finishes on the live page |
| **Opt-out page** | https://infotracer.com/optout/ |
| **A person may need to** | pick their own record |
| **Response window** | 45 days (CCPA) |
| **Source** | Process per redact.dev's InfoTracer removal guide (updated 2026-08-11). |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

1. OpenOptOut opens the opt-out page and fills in the search by its labels.
2. A person picks their own record and finishes on the live page:

> Find your own record in the results (check the age, city and relatives), select it, and finish the site's steps. Then press "I've done this step".

The site searches by name and state, then a person selects their record and uses "Remove Data", which ends with a slider check. privacy@infopay.com takes requests if the form fails.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
