# Web search

OpenOptOut can search the web for pages about each family member. It runs the same searches **Find your listings** offers as links — exact phone numbers, exact street addresses, exact email addresses, name + city, and phrases people-search pages use — for every variant in the identity vault.

It's **on by default**: finding where people are listed is the point of OpenOptOut. Docker installs come with a private SearXNG server, and weekly searches are on. An admin can turn web search off, or stop the weekly runs, under **Admin → Web search**.

## What happens to results

| Result | What OpenOptOut does |
|---|---|
| On a known data broker **and** showing one of the person's exact phone numbers, street addresses or email addresses | Added to removals automatically (can be turned off) |
| Anything else (name + city, name only, or a site OpenOptOut doesn't know) | Waits under **Discovery → Find your listings → Automatic web search** for the person to choose **That's me** (added to removals) or **Not me** (hidden for good) |

Search engines' own pages and a few large general sites are ignored. Titles and snippets are stored encrypted.

## Privacy

Searches send the person's names, phone numbers, addresses and email addresses to your SearXNG server, which passes them on to the search engines it uses. That's unavoidable for web search. The settings page says so, and an admin can turn it off.

## Provider: SearXNG

[SearXNG](https://docs.searxng.org/) is an open-source search server that collects results from other search engines. It's the only provider OpenOptOut supports, so web search stays self-hosted.

`docker-compose.yml` runs one for you (the `searxng` service, settings in `deploy/searxng/settings.yml`). It isn't published on any port, and OpenOptOut reaches it at `http://searxng:8080` (the `SEARXNG_URL` setting of the `api` service).

- **Use a different SearXNG:** enter its address under **Admin → Web search**. Its `settings.yml` must allow JSON results (`search: formats: [html, json]`); otherwise it answers "403 Forbidden".
- **Install without Docker:** there's no bundled SearXNG, so web search stays off until you enter an address.
- **Don't want it at all:** turn it off under **Admin → Web search**, and remove the `searxng` service from `docker-compose.yml` if you like.

Keep **Searches per person per run** modest: the search engines SearXNG uses may start refusing a server that sends many searches quickly.

## Running it

- **Search the web now** on the Discovery page searches for the selected person.
- **Search again for everyone once a week** runs it on a schedule.
