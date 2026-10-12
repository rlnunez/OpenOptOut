# Usage statistics over SUSHI (COUNTER Release 5.1)

Libraries and universities collect monthly usage from the services they offer through the **COUNTER API** (formerly SUSHI). Their systems include ERMs, Celus, Alma and LibInsight. OpenOptOut can answer those harvesters, so its usage appears next to the library's journal and database statistics.

**Admin → Usage statistics (SUSHI)** (super admins).

**SUSHI-compatible, not COUNTER-audited.** OpenOptOut doesn't serve journals or books, so it isn't in the COUNTER Registry, and its namespace for custom reports isn't registered. The format, error codes and messages follow the COUNTER Code of Practice, Release 5.1.

## What harvesters can collect

**Base URL:** `https://<your server>/api/sushi`

| Path | What it returns | Credentials |
|---|---|---|
| `/r51/status` | whether the service is up | none (public) |
| `/r51/members` | the institutions this harvester may see | requestor_id + api_key |
| `/r51/reports` | the reports offered, with the first and last months available | + customer_id |
| `/r51/reports/pr` | **Platform Report** (standard): `Searches_Platform`, Data_Type `Platform`, Access_Method `Regular` | + customer_id, begin_date, end_date |
| `/r51/reports/pr_p1` | **Platform Usage** (standard view of PR) | same |
| `/r51/reports/openoptout:oo1` | **OpenOptOut Usage** (custom): `OpenOptOut:People_Added`, `:Listing_Searches`, `:Listings_Found`, `:Optout_Requests_Sent`, `:Removals_Confirmed` | same |

**Institutions (customer IDs)**
- `all`: the whole server.
- `<system code>`: one library system.
- `<system code>-<branch code>`: one branch.

A person counts for the branch of their account. People a parent adds count for that parent's branch.

**What's counted** (per calendar month, up to the last complete month)

| Metric | Counts |
|---|---|
| `Searches_Platform` / `Listing_Searches` | one person's listings looked for on one broker on one day |
| `People_Added` | people whose details were added |
| `Listings_Found` | a person found on a broker for the first time |
| `Optout_Requests_Sent` | opt-out requests sent; a request sent again counts in its latest month |
| `Removals_Confirmed` | removals confirmed |

Months with nothing in them are left out, as COUNTER asks. **The reports hold counts only, never a name or a detail.** Small branches can still have small numbers, so share reports only with people who would be allowed to see that branch's activity.

**Supported parameters:** `begin_date` and `end_date` (`yyyy-mm` or `yyyy-mm-dd`), `metric_type`, `data_type`, `access_method`, `attributes_to_show=Access_Method` (PR only), `granularity=Month` and `platform`. Anything else gets exception 3050 and is ignored.

**Errors** follow Appendix D:

| Code | When |
|---|---|
| 1000 | the service is turned off |
| 1030 | credentials or dates are missing |
| 2000 | unknown requestor ID |
| 2010 | an institution the harvester may not see |
| 2011 | global reports ("The World", `0000000000000000`) |
| 2020 | wrong API key |
| 3020 | bad dates, or a begin date in the current month |
| 3030 | no usage in the requested months |
| 3031 | months that aren't complete yet |
| 3050, 3060, 3062 | parameters, filters or attributes that aren't supported (ignored) |

## Setting it up

1. **Turn it on.** Give the platform a name if "OpenOptOut" isn't what your patrons know it as.
2. **Add a harvester** for each system that will collect, and choose which institutions it may see. Copy the API key straight away: only its hash is kept.
3. **In the harvester**, enter:
   - the base URL;
   - the requestor ID and API key;
   - a customer ID from the table on the page.
4. **Serve it over HTTPS.** The COUNTER API must use TLS, and API keys are sent in the address. OpenOptOut removes `api_key=` from its own logs, but a proxy in front of it might log the address too.

## Testing it

There are three layers, from quickest to most independent:

1. **Run the self-test** on the page. It asks this server what a harvester would ask, using a throwaway key that's never saved, and checks every answer. The checks cover:
   - the public status;
   - each wrong credential's error code;
   - the report list;
   - every report's header and monthly counts;
   - bad dates (3020);
   - the current month (3031);
   - an unknown parameter (3050);
   - the standard error messages.
2. **`scripts/sushi-harvest-test.py`** runs the same checks over the network, the way a harvester reaches the server. Run it on any computer that has the OpenOptOut files and Python, against your own server:

   ```bash
   python3 scripts/sushi-harvest-test.py https://optout.example.org/api/sushi \
       --requestor-id oo-… --api-key '…' --save sushi-reports
   ```

   It exits with 0 when every check passes. `--save` keeps each report.
3. **The COUNTER Validator** (counter-validator.readthedocs.io) is COUNTER's own checking service. It needs a free account. Upload the saved reports, or give it your base URL and a harvester's credentials.

**Automated tests:**
- `sushi.api_follows_counter_51` runs the self-test against made-up data. It also checks the counts per branch, that a harvester limited to one branch can't see another, and that no names appear anywhere.
- `sushi.celus_client_reads_reports` reads the Platform Report and the custom report with **celus-nigiri**, the open-source harvesting client behind Celus, in strict mode. It runs when celus-nigiri is installed (`pip install celus-nigiri`) and is skipped otherwise.

## Limits

- **Not tested against a library's live harvester yet.** It passes Celus's own parser, but no real ERM has collected from a real server so far.
- **No COUNTER audit or registration.** A library may treat these reports as unaudited, which they are.
- **Counts come from the current records.** For example, a removal request that was sent again counts in its latest month.
