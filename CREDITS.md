# Credits

OpenOptOut stands on years of unpaid work by people who mapped data brokers, documented how to get out of them, and published tools to do it. Thank you. This page lists each project we learn from, what we use, and under what terms.

OpenOptOut is open source (AGPL-3.0) and noncommercial.

## Big Ass Data Broker Opt-Out List (BADBOOL)

- **Who:** Yael Grauer and contributors — [yaelwrites/Big-Ass-Data-Broker-Opt-Out-List](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List)
- **License:** [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
- **What we use:** facts about brokers — which companies own which sites, which opt-outs remove listings elsewhere, what each opt-out requires (ID, a phone call, payment), and opt-out addresses. These appear in [`backend/core/catalog/parent_companies.json`](backend/core/catalog/parent_companies.json) and in broker plugin `source` fields.
- **How:** we restate facts in our own words and credit BADBOOL next to each one. We don't copy BADBOOL's text into the codebase: AGPL lets anyone reuse our code commercially, which BADBOOL's noncommercial, share-alike terms don't allow for its text. If you want BADBOOL's write-ups themselves, read them [at the source](https://github.com/yaelwrites/Big-Ass-Data-Broker-Opt-Out-List) — and consider [supporting the project](https://ko-fi.com/kofisupporter11745).

## OptOut

- **Who:** Blake104 — [Blake104/OptOut](https://github.com/Blake104/OptOut)
- **License:** AGPL-3.0-only
- **What we use:** the Radaris opt-out flow and page selectors ([`broker-plugins/radaris`](broker-plugins/radaris)), and design ideas for broker specs: a "a person takes over here" step (our `pause_for_human`), `legal_basis` and `statutory_response_days` for deadline tracking, and per-broker requirement flags.
- **Note:** because OptOut is licensed AGPL-3.0-*only*, any part of OpenOptOut that includes code taken from it stays under AGPL version 3.

## auto-identity-remove

- **Who:** stephenlthorn and contributors — [stephenlthorn/auto-identity-remove](https://github.com/stephenlthorn/auto-identity-remove)
- **License:** MIT
- **What we use:** ideas for removal verification (search the broker again using a search URL and a listing pattern; our `search_url` and `listing_pattern` spec fields), status categories, and refreshing broker lists from state data-broker registries. If we copy code or selectors from it, its copyright notice goes with them.

## Opt-Out Desk

- **Who:** Patrick Carroll — [patrickomatic/opt-out](https://github.com/patrickomatic/opt-out)
- **License:** MIT
- **What we use:** the search patterns behind **Find your listings** ([`backend/core/listing_finder.py`](backend/core/listing_finder.py)): exact-phone and exact-address searches, name-and-city searches, the phrases people-search pages use ("possible relatives", "background check", "reverse phone", age), and per-broker searches through the broker's own search page or a site-restricted web search. We translated them from Rust to Python and extended them to every name, phone format, address and email in the identity vault.
- **Notice:** that module carries Opt-Out Desk's MIT copyright notice, as the license requires:

  > MIT License — Copyright (c) 2026 Patrick Carroll. Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Adding to this page

If a contribution uses another project's data, code or ideas, add it here in the same pull request: who made it, its license, what we use, and how. Broker plugins also record their source in `spec.json` (see [`broker-plugins/README.md`](broker-plugins/README.md)).
