# PeopleConnect (Intelius)

| | |
|---|---|
| **Method** | Guided (a person does it) |
| **Opt-out page** | https://suppression.peopleconnect.us/login |
| **A person may need to** | click an emailed confirmation link (OpenOptOut does this); pick their own record |
| **Also covers** | intelius.com, truthfinder.com, instantcheckmate.com, ussearch.com, zabasearch.com, addresses.com, addresssearch.com, peoplelookup.com, lookupanyone.com, publicrecords.com |
| **Response window** | 45 days (CCPA) |
| **Source** | Process per redact.dev's Intelius/PeopleConnect removal guide (updated 2026-05-21). Brands covered per the parent-company catalog. |
| **Starts** | Turned on |
| **Last verified by OpenOptOut** | Not yet. Run a live test and fill in `last_verified` in `spec.json` |

## What happens

The opt-out goes on the checklist with these steps, and a one-time email address so any reply and confirmation link are handled automatically:

> Open https://suppression.peopleconnect.us/login and follow the site's steps for `{full_name}`. Use `{contact_email}` wherever it asks for an email address, so the reply is matched. Then press "I've done this".

One suppression request covers the PeopleConnect brands: Intelius, TruthFinder, Instant Checkmate, US Search, ZabaSearch, Addresses.com, AddressSearch, PeopleLookup, LookupAnyone and PublicRecords.com (not Classmates). The site emails a code to the address given, then asks for a date of birth and legal name before showing records to pick; it may ask the person to complete a masked old email or phone. If it can't find the record, privacy@peopleconnect.us takes requests by email.

## Changing this plugin

Broker sites change. If a step stops working, check it in a real browser, update `spec.json`, bump `version` in `manifest.json`, and set `last_verified` to the date you tested. Run `python broker-plugins/tools/validate.py` before opening a pull request.
