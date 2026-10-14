# Usage statistics API

A small web service that a library's own scripts call to pull OpenOptOut's numbers into a **data mart** such as **LibInsight**, a **data warehouse** or a **data lake**. It can return daily, weekly or monthly counts, or one total, for any range of dates, for each library system and branch. **Counts only, never a name or a detail about anyone.**

Turn it on, and make keys, under **Admin → Usage statistics** (super admins).

> An earlier version (#109) offered these numbers as COUNTER reports over SUSHI. COUNTER's metrics are built for journal and book platforms, so it was replaced by this simpler service. The SUSHI code is in git history (commit `a960688`) if it's ever wanted again.

## Calling it

```
Base address:   https://<your server>/api/stats
Authentication: Authorization: Bearer <key>      (every path except /v1/status)
```

| Path | Returns |
|---|---|
| `GET /v1/status` | `{"service", "version", "enabled"}`. Public. |
| `GET /v1/institutions` | The institutions this key may see: `{"id", "name", "type": server\|system\|branch, "parent"}` |
| `GET /v1/metrics` | Each metric's name and meaning |
| `GET /v1/usage` | The counts |

`/v1/usage` takes these parameters:

| Parameter | Values | Default |
|---|---|---|
| `from`, `to` | `yyyy-mm-dd`, both inclusive. `to` may be today, but not later. | required |
| `granularity` | `day`, `week` (Monday to Sunday), `month`, or `total` (one row for the whole range) | `day` |
| `institution` | an id, several ids separated by commas, or `*` for every one the key may see | `all` |
| `metrics` | metric names separated by commas | every metric |
| `format` | `json` or `csv` | `json` |

The longest range is about three years by day, or ten years by week, month or total.

**Every period in the range gets its own row, including periods with zero counts.** Each row has `institution`, `period_start`, `period_end` and `complete`, plus one column per metric. `complete` is `false` for a period that includes today, because today's counts can still go up. A week or month cut off by your range keeps only the days inside it. Days are in UTC.

```bash
curl -H "Authorization: Bearer $OPENOPTOUT_STATS_KEY" \
  "https://optout.example.org/api/stats/v1/usage?from=2026-09-01&to=2026-09-30&granularity=day&institution=*&format=csv"
```

```json
{"from": "2026-09-01", "to": "2026-09-30", "granularity": "total", "timezone": "UTC",
 "generated_at": "2026-10-12T22:10:00Z", "metrics": ["people_added", "…"],
 "institutions": [{"id": "RVL-MAIN", "name": "Main", "type": "branch", "parent": "RVL"}],
 "rows": [{"institution": "RVL-MAIN", "period_start": "2026-09-01", "period_end": "2026-09-30",
           "complete": true, "people_added": 4, "listing_searches": 37, "listings_found": 12,
           "optout_requests_sent": 30, "removals_confirmed": 9}]}
```

**Errors** come back as `{"error", "message"}`:

| HTTP status | `error` | When |
|---|---|---|
| 400 | `bad_request` | Bad dates, `to` in the future, unknown metric, granularity, format or parameter, or a range that's too long |
| 401 | `unauthorized` | No key, or a wrong one |
| 403 | `forbidden` | An institution this key can't see |
| 404 | `not_found` | An unknown path |
| 503 | `off` | The service is turned off |

## What's counted

| Metric | Counts |
|---|---|
| `people_added` | People whose details were added |
| `listing_searches` | One person's listings looked for on one broker on one day |
| `listings_found` | A person found on a broker for the first time |
| `optout_requests_sent` | Opt-out requests sent. A request sent again counts on its latest date. |
| `removals_confirmed` | Removals confirmed |

**Institutions**

| Id | Covers |
|---|---|
| `all` | The whole server |
| `<system code>` | One library system |
| `<system code>-<branch code>` | One branch |

A person counts for the branch of their account. People a parent adds count for that parent's branch.

## Keys

- **One key per script or system**, so you can remove one without breaking the others. A key can be limited to particular institutions.
- **The key is shown once.** Only its hash is stored.
- **Send it in the `Authorization` header, over HTTPS.** Keys put in the address are refused, which keeps them out of web-server and proxy logs.

## The example bridge

`examples/stats-bridge/pull_usage.py` is a starting point (Python standard library only).

- **Daily runs:** each run collects every complete day since the last one, for every institution the key may see. It writes CSV and JSON Lines files and remembers where it stopped.
- **Backfilling:** `--from` and `--to` collect a past range; `--granularity total` gives one row per institution.
- **Loading the files:** change `load()` to send the rows to your destination. For LibInsight, that's your custom dataset's add-records address from **Admin → Widgets & API**. For a warehouse, upsert on `(institution, period_start)`. Re-running a day is safe.

## Testing

- **The self-test button** on the page calls this server the way a script would, using a throwaway key, and runs 15 checks:
  - the public status;
  - refusing no key and a wrong key;
  - institutions and metrics listed;
  - daily rows (one per day, zeros included);
  - monthly, weekly and total counts matching the daily ones;
  - CSV matching JSON;
  - today marked incomplete;
  - refusals for reversed dates, future dates, unknown metrics and institutions the key can't see.
- **`scripts/stats-api-test.py`** runs the same checks from another computer, using only the Python standard library:
  ```bash
  OPENOPTOUT_STATS_KEY='oos_…' python3 scripts/stats-api-test.py https://optout.example.org/api/stats
  ```
- **The automated test `stats_api.counts_and_checks`** runs those checks against made-up data. It also checks:
  - the counts per branch and per day;
  - that a key limited to one branch can't see another;
  - that "off" means off;
  - that keys in the address are refused;
  - that no names appear.

## Limits

- **Counts come from the current records.** For example, a request sent again counts on its latest date.
- **Small branches can have small daily numbers.** Give keys only to people who may see that branch's activity.
