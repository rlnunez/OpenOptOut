# Removal checks

An opt-out isn't finished when the request is sent: brokers ignore some requests and put listings back weeks later. OpenOptOut checks every removal on its own and acts on what it finds.

## How it checks

It tries the most direct check first:

1. **The listing page itself**, when the address is known: pasted under Find your listings, found by Discovery or web search, or required by the broker. A page that's gone (404/410), redirects elsewhere, says the record was removed, or no longer shows the person counts as **gone**.
2. **The broker's own search**, when its plugin has a `search_url` (and ideally a `listing_pattern` for result links). Each result is judged on its own text, so a namesake in another city isn't mistaken for the person.
3. **A web search** through the bundled SearXNG (`site:broker.com "Name" "City"`). Search engines lag behind removals, so a result only counts as **still up** after OpenOptOut visits the page and sees the person there.

"Shows the person" means the same matching web search uses: an exact phone number, street address or email, or their name together with their city. On their own listing page, the name alone is enough.

Sites that only render with script are opened in a hidden browser. Sites that block automated visits (CAPTCHA walls, 403, 429) are recorded as **couldn't check** and tried again later.

## What happens next

| Request was | Check finds | Then |
|---|---|---|
| Sent | Gone | Marked **removed** ("checked: listing gone") |
| Sent, past the broker's legal response window | Still up | **Sent again** |
| Removed | Still up | **Sent again**, noted as "came back" if a check had seen it gone |
| Removed | Gone or not found | Next check pushed out |
| Any | Couldn't check | Nothing changes; the scheduled re-send still happens |

## When it runs

- **Every day** (`verification` job), within a budget of 40 checks a day and 5 per broker:
  - sent requests at least a week old, rechecked weekly
  - removed ones monthly
  - any whose re-check date has come
- **At every scheduled re-check.** It looks first, so a listing that's still gone isn't opted out of again.
- **Whenever the weekly web search** finds a page about someone on a broker they were already removed from. That page is checked straight away.
- **On demand:** **Check now** on the Dashboard's *Removal checks* card, or `POST /api/verification/request/{id}` for one request.

Results are on the Dashboard (gone, still up, not found, couldn't check, plus the latest checks). The full history is in the `verification_checks` table.

## Privacy

Checks only visit the broker's own pages and the bundled SearXNG, at public addresses only. The page addresses and search terms contain the person's name and city, which the broker already has. Nothing is submitted.

## Settings

`verification` in settings (`/api/verification/settings`, needs `settings.system`):

| Setting | Default | What it does |
|---|---|---|
| `enabled` | `true` | Run removal checks |
| `use_browser` | `true` | Use the hidden browser for script-only or blocking sites |
| `per_day` | `40` | Most checks per day |
