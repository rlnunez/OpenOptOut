# Web search

OpenOptOut can search the web for pages about each family member. It runs the same searches **Find your listings** offers as links — exact phone numbers, exact street addresses, exact email addresses, name + city, and phrases people-search pages use — for every variant in the identity vault.

It's **off by default**. An admin turns it on under **Admin → Web search**.

## What happens to results

| Result | What OpenOptOut does |
|---|---|
| On a known data broker **and** showing one of the person's exact phone numbers, street addresses or email addresses | Added to removals automatically (can be turned off) |
| Anything else (name + city, name only, or a site OpenOptOut doesn't know) | Waits under **Discovery → Find your listings → Automatic web search** for the person to choose **That's me** (added to removals) or **Not me** (hidden for good) |

Search engines' own pages and a few large general sites are ignored. Titles and snippets are stored encrypted.

## Privacy

Searches send the person's names, phone numbers, addresses and email addresses to the search provider. A SearXNG server also passes them on to the search engines it uses. That's unavoidable for web search, and it's why the feature is off until an admin turns it on.

## Providers

### SearXNG (self-hosted, free)

[SearXNG](https://docs.searxng.org/) is an open-source search server that collects results from other search engines. Run it next to OpenOptOut, for example by adding to `docker-compose.yml`:

```yaml
  searxng:
    image: searxng/searxng:latest
    restart: unless-stopped
    volumes:
      - ./searxng:/etc/searxng
```

In `searxng/settings.yml`, allow JSON results:

```yaml
search:
  formats:
    - html
    - json
```

Then enter `http://searxng:8080` as the SearXNG address. Without `json`, SearXNG answers with "403 Forbidden".

### Brave Search API (paid)

Create an API key in Brave's Search API dashboard and paste it in. Brave charges per search, so keep **Searches per person per run** modest; a family of four with 12 searches each, run weekly, is roughly 200 searches a month.

Google's Custom Search JSON API isn't offered: it's closed to new customers and being shut down.

## Running it

- **Search the web now** on the Discovery page searches for the selected person.
- **Search again for everyone once a week** runs it on a schedule.
