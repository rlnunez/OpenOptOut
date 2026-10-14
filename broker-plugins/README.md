# Broker plugins

Each data broker is its own plugin in its own folder, versioned on its own. Changing one broker never touches another.

The plugins ship with the app and install themselves at startup, so they live with the other built-in plugins:

```
backend/plugins/bundled/brokers/
├── spokeo/           manifest.json, spec.json, README.md
├── mylife/  beenverified/  radaris/  whitepages/  ...
broker-plugins/
├── _template/        copy this into backend/plugins/bundled/brokers/<id>/ to start a new broker
└── tools/
    ├── validate.py   checks every plugin with the app's validators, the rules below, and a dry run
    └── package.py    builds one upload-ready zip per plugin into dist/ (to update a server by hand)
```

At startup each built-in plugin is installed and its broker created, turned on unless the manifest says `"starts_enabled": false` (see below). On an upgrade the copy is refreshed. A plugin an admin turned off stays off, and an admin's own plugin with the same id is never replaced.

## Three kinds of plugin

| Kind | `method` | What happens |
|---|---|---|
| **Automated** | `form` | The app fills and submits the broker's form. CAPTCHAs go to a solver plugin or the CAPTCHA queue; a `pause_for_human` step hands the rest to a person. |
| **Email** | `email` | The app emails `email.to_address`. Leave out `subject_template` and `body_template` and the broker gets the legal opt-out letter for the law that applies to the person (Opt-out letters page); give both only when the broker needs its own wording. |
| **Guided** | `manual` | The broker needs something only a person can do (pick their record, answer a call, solve several CAPTCHAs). The request goes on the checklist with `instructions`. Use `{contact_email}` in them: the person gives that one-time address, so the broker's reply is matched and its confirmation link is clicked automatically. |

| Broker | Kind | A person must |
|---|---|---|
| Spokeo | Automated | Nothing with a CAPTCHA solver; otherwise the CAPTCHA queue |
| MyLife | Automated | Nothing with a CAPTCHA solver; otherwise the CAPTCHA queue |
| BeenVerified | Automated, then a person | Pick their record and solve a CAPTCHA |
| Radaris | Automated, then a person | Pick their profile |
| Whitepages | Guided | Answer an automated phone call |
| FastPeopleSearch, TruePeopleSearch, Nuwber, That's Them, USPhoneBook, SmartBackgroundChecks, SearchPeopleFree, FamilyTreeNow, Cyber Background Checks, Clustal, Social Catfish | Guided | Find their record and submit the site's form |

### Broker pack 1 (October 2026)

Fifty more brokers, written to a few standard shapes so they're easy to check and translate:

| Shape | Steps | Brokers |
|---|---|---|
| Automatic form | `navigate` → `autofill` (fills by labels; stops for a person when unsure) → `solve_captcha` (optional) → `submit` | Acxiom, Epsilon, PeopleFinders, Pipl, VeriPages, ClustrMaps, PublicDataUSA, WYTY, AbsolutePeopleSearch, National Cellular Directory, CocoFinder, OfficialUSA, SpyFly, SearchQuarry, Neighbor.Report, PeopleByName, PeepLookup, Spytox, ProPeopleSearch, BackgroundAlert, Archives.com, CallTruth, PeopleByPhone, RevealPhoneOwner |
| Form, then a person picks the record | the same, then a `pause_for_human` | InfoTracer, PeopleLooker, PeopleSmart |
| Email with the legal letter | `method: email`, `to_address` only | Experian Marketing, Data Axle, InfoPay network, TruePeopleSearch.net, uFind, Whooster, DelvePoint, IRBsearch |
| Guided | `method: manual` with standard `instructions` | PeopleConnect (Intelius), LexisNexis, TransUnion (TLOxp), CheckPeople, Unmask, VoterRecords, USA People Search, PeopleSearchNow, AdvancedBackgroundChecks, PeopleWhiz, LocateFamily, GladIKnow, USA-Official, 411.info, SearchBug |

LexisNexis and TransUnion (TLOxp) ask for a Social Security or driver's license number. They are guided plugins that say so; OpenOptOut never fills those in.

Sources: current (2026) removal guides from redact.dev and the companies' own pages for the big brokers, and *The Opt-Out Manual 2026* (public domain) for the rest. On 2026-10-11 we tried to load every page taken from the manual, without entering any details. The 16 that blocked automated readers ship turned off (below). These were left out:

| Site | Why it was left out |
|---|---|
| golookup.com | domain transferred by court order |
| revealname.com | domain changed hands after a lawsuit |
| dataveria.com, centeda.com, pub360.com, newenglandfacts.com, rehold.com, telephonedirectories.us | domains transferred to Atlas Data Privacy Corporation by a New Jersey court order |
| backgroundcheck.run, councilon.com, people-background-check.com, vericora.com, veriforia.com | same Radaris-clone network as the seized sites; couldn't be checked, so left out rather than shipped |
| grey-pages.com | the removal page redirects to an unrelated removal service |
| allareacodes.com | says it no longer holds personal details |
| phoneowner.com | now a numbering reference site, not a directory of people |
| idcrawl.com | the listed opt-out address is no longer an opt-out page |
| findpeoplesearch.com | the listed page is a general customer-service form |
| persopo.com | search powered by TruthFinder, so the PeopleConnect plugin covers it |
| addresssearch.com | a PeopleConnect site, so the PeopleConnect plugin covers it |

## Checked and unchecked plugins

A plugin whose opt-out page nobody could check ships with `"starts_enabled": false` in its manifest. It installs, but its broker starts turned off, so nothing is typed into a site that may have changed hands. Data-broker domains do change hands: several from older lists now show court-ordered transfer notices, or redirect somewhere else.

To turn one on, open its opt-out page and confirm it's still the site's own form, or run a rehearsal (**Automatic broker steps**). A rehearsal uses made-up details and stops before the last click. Then press **Turn on** on the Brokers page. Once someone runs the flow against the live site, fill in `last_verified` and remove `starts_enabled`.

### When a listing is found on one that's off

When Find listings or web search finds someone on a broker that's turned off, that broker is clearly live, and it already lists the person. Opting out there can't add anyone new. Under **Broker updates** an admin chooses what happens next ([`core/found_listings.py`](../backend/core/found_listings.py)):

| Choice | What happens |
|---|---|
| **Ask an admin** (default) | The broker is listed with the number of people found and a **Turn on** button. Opt-outs wait until it's on. |
| **Turn on automatically** once listings are found for at least *N* people | It turns on and opts out. Below *N*, it asks an admin or tells the person, whichever the admin chose. It never turns on a broker that an admin turned off, that the health monitor turned off after failures, whose website looked gone, or that has no plugin. |
| **Tell the person** | It goes on their checklist with the site's opt-out page. If the broker is turned on later, the request goes back to OpenOptOut. |

The rule counts distinct people, not listings, and records only a broker name and a number. Brokers imported from a state registry follow their own rule (`core/broker_gate.py`).

## What one opt-out covers

`covers` in `spec.json` lists other sites, by bare domain, that the same company says one request reaches (PeopleConnect's covers Intelius, TruthFinder, Instant Checkmate and more). The Brokers page adds these up, together with families in the parent-company catalog marked `one_optout_covers` and its "confirmed" cascades ([`core/coverage.py`](../backend/core/coverage.py)). It shows "Also removes you from N other sites" on each broker, and how many sites the turned-on brokers reach between them. "Likely" cascades are shown but never counted.

None of these has been run against the live site by OpenOptOut yet (`last_verified` is empty). The automated flows use selectors that were verified upstream in May 2026.

## Rules

- The folder name, `manifest.id`, `manifest.broker_id` and `spec.broker_id` are the same.
- `spec.name` matches the broker's name in the app, so installing updates it instead of creating a duplicate.
- `spec.source` says where the opt-out details came from. `spec.last_verified` is the date someone last ran the flow against the live site (`YYYY-MM-DD`), or empty if nobody has yet.
- Bump `manifest.version` on every change.
- Use the field `contact_email` for "where should we send your confirmation" boxes (and in guided `instructions`). It fills in a unique address for that one opt-out (`jane+oo7f3k2a9@gmail.com` on inboxes that allow it), so the reply is matched to its request. Use `email` only when the form wants an address to remove.
- Use the field `listing_url` for boxes that ask for the address of the person's own listing (Spokeo, Clustal, National Public Data…). It's filled from a listing found by Discovery or pasted under **Find your listings**; if there isn't one yet, the opt-out goes on the checklist asking for it.
- Any point where a person has to take over (pick a listing, answer a phone call) is a `pause_for_human` step whose `text` tells them, in plain words, exactly what to do. The person can do it on the Checklist with **Do it here**: OpenOptOut fills the form again up to that step, shows them the live page, and carries on with the steps after it once they press "I've done this step". So write the text for someone looking at the page ("Enter the 6-digit code the site texted you"), and put any steps that should run afterwards (a final click, `expect_success`) after the pause.
- Don't copy another project's wording. Facts (URLs, selectors, which fields a form needs) are fine; credit the source in `source` and in [CREDITS.md](../CREDITS.md).

## Spec fields beyond the steps

| Field | What it's for |
|---|---|
| `legal_basis` | Which laws apply (`ccpa`, `cpra`, `gdpr`, `vcdpa`, …) |
| `statutory_response_days` | Days the broker has to respond; gives each request a due date |
| `search_url`, `listing_pattern` | The broker's own search page (`{first_name}`, `{last_name}`, `{full_name}`, `{city}`, `{state}`, `{phone}` are filled in). Used for the per-broker links under **Find your listings**, and with `listing_pattern` to check later whether a listing is still up |
| `one_optout_per_email` | The broker accepts one opt-out per email address |
| `accepts_plus_addresses` | Set `false` if the broker's form refuses addresses with a `+`. The app also learns this by itself when a form says the email is invalid, and retries with the plain address |
| `instructions` | For guided (`manual`) plugins: the checklist steps, with `{full_name}`, `{contact_email}`, `{listing_url}`, `{city}`, `{state}`… filled in |
| `covers` | Other sites (bare domains) that one opt-out here also reaches, per the company |
| `requires` | What a person may have to do: `email_confirmation`, `listing_url`, `listing_selection`, `phone_call`, `government_id`, `account`, `payment`, `postal_mail` |

## Commands

```
python broker-plugins/tools/validate.py      # check all plugins (validators, rules, dry run)
python broker-plugins/tools/package.py       # zip each plugin into broker-plugins/dist/
```

Upload a zip under **Settings → Plugins** in the app.
