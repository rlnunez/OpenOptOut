# Email Setup

OpenOptOut uses email in two separate ways:

| | System inbox | Family inboxes |
|---|---|---|
| **Who sets it up** | The administrator, in the Setup Wizard or **Settings → Email** | Each person, under **Email inboxes** after signing in |
| **What it sends** | Sign-in links, status updates, admin alerts | Opt-out requests to data brokers |
| **What it receives** | Nothing OpenOptOut reads | Broker replies and confirmation links, which OpenOptOut matches to requests |

Opt-outs are never sent from the system inbox. Some brokers (BeenVerified, for example) accept only one opt-out per email address, so one shared address for a whole household or organization can't work.

---

## Family inboxes

Every person needs an inbox for their opt-outs. Anyone without one sees a reminder after signing in, and their opt-outs wait on the checklist until one is connected.

- **Connect your own:** go to **Email inboxes → Connect an inbox**, choose your email service and sign in.
- **Parents can connect several** and choose which one each family member uses.
- **One Gmail-type inbox can cover a whole family.** A member with no inbox of their own automatically uses a parent's inbox, as long as that inbox supports +addresses (below).

### One address per opt-out (+addresses)

Many email services deliver mail sent to `you+anything@gmail.com` to `you@gmail.com`. OpenOptOut uses this to give every single opt-out its own address, such as `you+oo7f3k2a9@gmail.com`:

- Each broker reply is matched to the exact request it belongs to.
- Brokers that allow one opt-out per email address get a fresh address each time.
- If mail later arrives at one of these addresses from someone other than the broker it was given to, OpenOptOut records it: that broker's copy of the address has been passed on.

The tag is random. It doesn't reveal the broker's name or the family member.

| Service | +addresses |
|---|---|
| Gmail, Google Workspace | Yes |
| Outlook.com, Hotmail, Live | Yes |
| Microsoft 365 work/school | Usually; an administrator can turn it off, so OpenOptOut checks |
| iCloud Mail, Fastmail, Proton Mail | Yes |
| Yahoo, AOL | No — each Yahoo inbox can only be used for one family member |
| Anything else | OpenOptOut sends one test email to a +address and marks the inbox when it arrives (or after 24 hours, as "same address for every opt-out") |

**Known limits.** Some broker forms reject addresses containing `+`, and a broker could strip the tag and still see the plain address. When a form refuses an address, that opt-out goes on the checklist.

### How inboxes are connected

- **Gmail, Outlook, Yahoo:** sign in with the provider (OAuth). OpenOptOut never sees your password. The access it asks for lets it send mail and read the inbox; it only looks at message headers and short previews. Access is refreshed automatically and you can revoke it from your provider's security page. The administrator must first register the provider's app under **Settings → Email** (see below).
- **Other services:** use an **app password** (not your normal password) with the IMAP and SMTP server names from your provider's help pages. The password is encrypted before it is stored.

Disconnecting an inbox deletes its stored sign-in tokens or password. Deleting a user account deletes their inboxes and the opt-out addresses issued from them.

---

## System inbox (administrator)

The system inbox only sends notifications, so any account works. A dedicated address such as `notifications@yourdomain.com` is best.

### OAuth 2.0 (recommended)

Supported for Gmail / Google Workspace, Outlook / Microsoft 365 and Yahoo. Register an OAuth app with the provider and enter its client ID, secret and redirect URI in **Settings → Email**. The same registration is what lets families connect those inboxes with one click, so set it up even if the system inbox uses SMTP.

- Gmail scopes: `gmail.send` and `gmail.readonly`
- Outlook scopes: `Mail.Send`, `Mail.Read`, `offline_access`

### App password / SMTP

For providers without OAuth (Fastmail, Proton Mail Bridge, self-hosted servers): create an app password in your provider's security settings and enter the SMTP and IMAP details in **Settings → Email**. Never use your main account password.

---

## How replies are matched

The email monitor job checks every connected family inbox on its schedule:

1. If the message was sent to one of OpenOptOut's +addresses, it belongs to that address's request, provided it came from the broker (or parent company) the address was given to. Otherwise it is recorded as an unexpected sender.
2. Otherwise, a tracking ID in the subject or text is used, as before.

Only headers and a short preview are read, plus the links in replies to OpenOptOut's +addresses (see below). OpenOptOut doesn't mark messages as read in IMAP inboxes.

The system inbox is still checked too, so replies to opt-outs sent before family inboxes existed are still matched.

---

## Confirmation links

Some brokers (Radaris, Spokeo, BeenVerified and others) won't act until someone clicks a link they email back. OpenOptOut handles this for you:

1. When a matched reply asks for a click, the request stays **sent** (not removed). OpenOptOut saves the link encrypted and never writes it to the logs.
2. After each email check, OpenOptOut opens the link. If the page has a "Confirm" button, it presses it in a hidden browser.
3. The opt-out only counts as **confirmed** once the page says it worked.

A link is only opened when all of these are true:

- it starts with `https://`
- it goes to that broker's own website, its parent company's, or an email click-tracker (SendGrid, Mailgun, and similar) that leads there
- it doesn't point to a private or local network address (this is checked again at every redirect)
- it isn't an unsubscribe, preferences or policy link

No personal details, cookies or form entries are sent. Mail that reaches a +address from someone other than the broker is never clicked.

If a link can't be clicked, it goes on the **Checklist** under *Confirm these opt-outs* with the reason and one button to open it. This happens when the link goes to a different site, the page says the link expired, the page didn't say whether it worked, or the inbox couldn't show the link. Press **I've confirmed it** when you're done.

Administrators can turn automatic clicking (and the button-pressing browser) off on the **Email Monitor** page.

**Which inboxes can supply links:**

| Inbox | Links read |
|---|---|
| Gmail (OAuth), Outlook / Microsoft 365 (OAuth) | Yes, from replies to +addresses |
| App-password / IMAP inboxes, including Yahoo over IMAP | Yes |
| Yahoo (OAuth) | Not yet: these replies go on the checklist |
| Third-party email plugins that predate this feature | No: these replies go on the checklist |

For +address inboxes, only messages sent to an OpenOptOut +address are opened to look for links. Inboxes without +addresses have every recent message checked. In both cases the message body stays inside the email plugin's sandbox, and only the links leave it.
