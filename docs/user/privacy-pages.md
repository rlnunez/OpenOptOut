# Privacy pages and hosted privacy forms

Most of the hundreds of data brokers have no opt-out steps written for them. For those, OpenOptOut looks at the broker's own website to find where a person asks it to delete their data, and fills that form itself when it safely can.

## Finding the page

The **privacy-page finder** (`backend/core/privacy_finder.py`) reads the broker's home page and follows the links that matter, such as "Do Not Sell or Share", "Your Privacy Choices", "Privacy Request", "Opt out" and "Remove my information". If those don't turn anything up, it tries the usual addresses (`/opt-out`, `/do-not-sell`, `/privacy`, …).

| It records | Used for |
|---|---|
| A **OneTrust** or **TrustArc** privacy-request form | Filled automatically |
| The company's **own request form** (asks for an email and talks about deletion or opting out) | Filled automatically |
| Another hosted privacy platform (Osano, Securiti, Ketch, …) | Named on the checklist |
| An **opt-out page** or the **privacy policy** | Named on the checklist |
| A **privacy email address** on the broker's domain | Only after an admin approves it (**Brokers → Privacy pages → Use for email opt-outs**) |

It sends no personal data and submits nothing. It fetches at most 8 public `https` pages, all on the broker's own domain or a known privacy platform.

**When it runs:**
- every day, for up to 20 brokers without steps whose site hasn't been checked in 30 days
- right away, when someone pastes a listing on a site OpenOptOut doesn't know (if it finds a form it can fill, that opt-out goes back into the queue as automated)
- whenever an admin presses the search button next to a broker

Results show under **Brokers → Privacy pages found on brokers' websites**. Mark a wrong one **Not it** and it won't be used again.

## Filling the form

Hosted forms differ in markup but not in meaning. The `autofill` step (`backend/core/interpreter/hosted_forms.py`) reads every visible field's label and decides what goes where:

- **Request type:** delete and do-not-sell/share. Never "access", "correct" or other requests.
- **Who is asking:** "myself" / "I am the consumer", never "authorized agent".
- **Details:** name, the one-time email address for this opt-out, address, state, country. Free-text boxes get a short plain request to delete the data and stop selling it.
- **Certification boxes** ("I certify…") are ticked. **Marketing and newsletter boxes never are.**

It stops and hands the form to a person, with the page's address on the checklist, when:
- there's no email box, or no name box (a lone email box is a newsletter, not a privacy form)
- the request types don't include deletion or opting out
- a required field asks for something OpenOptOut never fills in: ID or licence numbers, SSNs, dates of birth, passwords, uploads
- a required field or question can't be placed

After submitting, OneTrust and TrustArc usually email a verification link. It goes to the one-time address and is clicked automatically (see [EMAIL_SETUP.md](EMAIL_SETUP.md#confirmation-links)); their domains are allowed for that broker.

## Which steps a broker uses

1. An installed broker plugin
2. Selectors an admin saved under Automation scripts
3. A form the finder found (this page)
4. Otherwise a checklist item, naming the page the finder found if any. Best-guess filling is an admin opt-in (Settings → Automation).
