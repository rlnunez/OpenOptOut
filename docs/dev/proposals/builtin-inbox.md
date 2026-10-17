# Design: built-in receive-only inbox

**Status:** proposal, not built. Follows the family-inbox work (`core/mailboxes.py`).

## Problem

Family inboxes with +addresses solve most of the "one opt-out per email" problem, but not all of it:

- Yahoo, AOL and many smaller providers don't support +addresses, so those inboxes can serve only one family member.
- Some broker forms reject `+` in an address.
- A broker can strip the `+tag` and still see the family's real address, so the address keeps leaking into broker databases and mailing lists.

## Proposal

Let OpenOptOut **receive** mail for a domain the family owns (for example `optout.smithfamily.example`), and give every opt-out a random address there:

```
k7f3m2a9q@optout.smithfamily.example
```

No `+`, no link to the family's real address, and an unlimited supply.

The important point is that **only receiving is needed.** Brokers send their confirmations *to* the address typed into their form; OpenOptOut never has to send mail *from* this domain:

- **Form opt-outs:** the random address goes in the form's email box (`contact_email`).
- **Email opt-outs:** still sent from the family inbox, with `Reply-To:` set to the random address.

Sending from a self-hosted server is the hard part of running email (SPF/DKIM/DMARC, IP reputation, spam folders). Leaving it out keeps this small.

## How it fits the current code

- A `Mailbox` with `transport = "builtin"` and `plus_status = "verified"`. `issue_contact_address()` gets one more branch: for built-in inboxes, generate `random@domain` instead of `base+tag@domain`, stored in the same `ContactAddress.tag` column.
- `resolve_mailbox()` unchanged: a built-in inbox can be assigned to any number of members.
- Sending opt-out emails needs a real outgoing inbox, so a member assigned a built-in inbox also needs a sending inbox (their own or a parent's). Simplest rule: `Mailbox.send_via_id` points at the inbox that sends for it.
- Matching: `match_inbound()` is called with the `RCPT TO` address, so the unexpected-sender check and request matching work as they do now.

## Components

1. **SMTP receiver** — a small service (Python `aiosmtpd`) listening on port 25 in its own container:
   - accepts mail only for configured domains and only for addresses that exist in `contact_addresses`; everything else is rejected at `RCPT TO` (no catch-all spam bucket),
   - size limit (for example 256 KB), rate limits per sending IP,
   - TLS with the same certificates the web front door uses,
   - hands each accepted message to the backend over the internal network; nothing is written to disk unencrypted.
2. **Message store** — confirmation emails must be readable by the family (and later by the automatic link-clicker), so store them encrypted (`EncryptedText`) in a `received_messages` table, linked to the `ContactAddress`, deleted after a retention period (for example 90 days).
3. **Inbox viewer** — a plain list in the app: from, subject, which broker, date, and a "show" button. Links shown, not auto-loaded.
4. **Forwarding (optional)** — forward non-broker mail (the leak cases) to the family inbox with a warning banner, so families see who bought their address.

## Setup the family has to do

1. Own a domain (or a subdomain of one) — roughly $10–15 a year.
2. Add one DNS record: `MX optout.smithfamily.example → mail.<their OpenOptOut host>`.
3. Open inbound port 25 to the server. Many home internet providers block it, which is the biggest practical obstacle for self-hosters. Alternatives:
   - a tiny relay on a cheap VPS that forwards to the home server over a tunnel,
   - an inbound-parse webhook from a mail provider (Cloudflare Email Routing → Worker, Mailgun, Postmark). This removes the port-25 problem but adds an outside party that sees broker mail, so it should be opt-in and clearly labelled.

The setup wizard would check the MX record and send a test message to itself through the public internet before enabling the domain.

## Risks and open questions

- **Disposable-domain blocklists.** Some brokers refuse addresses on unfamiliar domains. A family-owned domain with a real website is less likely to be on those lists than shared temp-mail domains, but the fallback stays the family inbox.
- **Abuse.** A receive-only server that rejects unknown recipients can't be used as an open relay, but it is a new public-facing service: it needs the same sandboxing (bubblewrap + seccomp) and fuzzing as the plugin host.
- **Losing mail.** If the server is down, senders retry for days, so short outages are fine; long ones lose confirmations. The status page should show "last mail received".
- **Hosted option.** A shared domain run by the project for families who can't run a domain. Rejected for now: it would make the project a third party holding families' broker mail, which is exactly what self-hosting avoids.

## Suggested order

1. Built-in inbox via inbound webhook (no port 25), behind an "experimental" flag.
2. Self-hosted SMTP receiver container.
3. Automatic confirmation-link clicking reading from both family inboxes and the built-in store.
