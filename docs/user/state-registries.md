# State data broker registries, dead sites, and California DROP

## Registries

California, Vermont, Texas and Oregon require data brokers to register. Admins can import those lists under **Admin → State registries**.

**Getting the file.** Each card links to the state's registry page with a short note on how to download it. Upload the CSV (or Excel, if the server has `openpyxl`). If a state offers a stable download link, save it on the card and OpenOptOut refreshes that state once a month. Column names differ by state; the preview shows which columns were used.

| State | Registry |
|---|---|
| California | [cppa.ca.gov/data_broker_registry](https://cppa.ca.gov/data_broker_registry/) — "Download CSV" |
| Vermont | Secretary of State data broker search and export |
| Texas | [Secretary of State registry](https://texas-sos.appianportalsgov.com/data-broker-registry) |
| Oregon | [Division of Financial Regulation registry](https://dfr.oregon.gov/business/licensing/data-broker-registry) |

**What an import does.** Every import is previewed first. Applying it:

- adds each new broker **turned off**, with its registered website and contact email,
- adds registry details (which states, contact email, last seen) to brokers you already have, matched by domain, without changing anything else,
- lists brokers that dropped off that state's registry, without deleting them,
- notes when a new broker's domain belongs to a family in the parent-company catalog.

### Why new brokers start turned off

Turning a broker on sends every family member's names, addresses, phone numbers and email addresses to it. Most registered brokers are advertising or business-data companies with no record about a given family. Contacting them can confirm that your details are real and current, and some keep the request itself. So:

- a family member who **finds a listing about themselves** on a registry broker (Discovery or Find your listings) gets an opt-out for it even while it's off,
- an admin can turn brokers on one at a time or all at once, after reading and acknowledging the warning,
- turned-off registry brokers aren't included in automatic discovery scans.

## Dead sites

Opt-out failures are now told apart: "the site is gone" (no DNS, connection refused, 404/410) versus "the form changed". A site that stays unreachable for 30 days is marked defunct and turned off. If it's still on a state registry, the note says it may have moved. Once a day, OpenOptOut also checks up to 50 broker home pages (no personal data is sent; private network addresses are never contacted). A defunct site that answers again is flagged for review rather than turned back on. Admins can run a check from the State registries page.

## California DROP

Since August 1, 2026, Californians can ask every registered broker to delete their data with one free request through the state's DROP. Brokers have 90 days to act. The person has to confirm their own residency, so OpenOptOut can't submit it for them. Instead:

- every family member with a California address gets one checklist item linking to [privacy.ca.gov/drop](https://privacy.ca.gov/drop/),
- when they mark it done, the date is kept,
- 90 days later, brokers OpenOptOut knows only from California's registry are skipped for that person. Brokers registered in other states too, and people-search sites where they're actually listed, still get direct opt-outs.
