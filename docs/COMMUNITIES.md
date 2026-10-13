# Residents-only sign-up

Some places want OpenOptOut for their own residents only: a management district, an apartment complex, a senior living community, or another housing community. They upload a list of their addresses, and only people at an address on the list can create an account.

Turn it on under **Admin → Branding → Registration controls** (permission `users.registration`).

## How someone signs up

The sign-in screen gets a **"Create an account"** link, which opens `/signup`:

1. **Home address.** The person enters their street address, apartment or unit, city, state and ZIP code.
   - If the address isn't on the list, they see why, plus the contact you set (for example, the office's phone number).
   - Lookups are limited to 10 a minute from one connection, so nobody can work through the list quickly.
2. **Email.** A 6-digit code is emailed to them. The code expires in 15 minutes and allows 5 wrong tries.
   - If the email already has an account, that person is emailed a reminder to sign in, and no code. The page looks the same either way, so it doesn't reveal who has an account.
3. **Name and password.** The account is made, and they're signed in.
   - Their address becomes their own primary address, ready for opt-outs.
   - If the address row had a branch, the account joins that branch.

The server checks every step again when the account is created, so the sign-up API can't be used to skip them.

**Other ways in:**
- **Google or Microsoft sign-in buttons can't start a new account** while the address check is on, because those buttons never ask for an address. People can sign up first, then use the button; it links to the same email.
- **Directories you set to create accounts** (library card, LDAP, SAML with "auto-provision") still create accounts. You chose who comes from those.
- **Accounts that admins create are never checked.**

## Settings

| Setting | What it does |
|---|---|
| Show a "Create an account" page | Turns the page on. People confirm their email with a code first. Registration mode (open, domain, invite code) still applies; with invite codes, the page asks for one. |
| Only people who live at an address on our list can sign up | The address check. Turning it on also turns on the page. |
| Accounts per home | How many accounts one home (address plus unit) may have. 0 means no limit. |
| Who to contact if an address isn't on the list | Shown on the sign-up page. |

The sign-up page needs the server's notification email (Settings → Email). Without it, the page says it can't make accounts yet, and the admin section shows a warning.

## The address list

Upload a CSV file, either replacing the list or adding to it.

**Accepted columns** (header names aren't case-sensitive):

| Column | Other names accepted |
|---|---|
| `address` (the street line, e.g. `123 Main St`) | `street_address`, `address1`, `line1`, `site_address`, `situs_address`, `property_address` |
| or `house_number` + `street_name` | `street_number`, `addr_num`; `prefix`, `street_suffix`, `street_type`, `postdir` |
| `unit` | `apt`, `apartment`, `suite`, `address2`, `line2` |
| `city`, `state` | |
| `zip` (required) | `zipcode`, `zip_code`, `postal_code`, `zip5` |
| `branch` (optional) | `branch_code` |

A file with no header, one full address per line (`123 Main St Apt 4, Houston, TX 77060`), also works.

**What each row means:**
- A row **without a unit** stands for the whole building: any unit there matches.
- If a building's rows **have units**, the person must give one of them.

Your county's mapping (GIS) or property office can usually export address points or parcels.

**Rows that can't be used** are reported by row number only, for example "Row 6: Add the 5-digit ZIP code." The address in that row isn't shown.

**Size limits:** 30 MB and 500,000 rows per file. Split bigger lists and upload them with "Add to the list".

**Trying an address:** the "Check" box tries an address exactly the way the sign-up page will, and says how many accounts it already has.

## How addresses are matched

Both the list and what people type are cleaned up the same way, so `123 Main Street, Apt 04` and `123 MAIN ST #4` match:

- upper case, with punctuation removed;
- street types and directions shortened as the USPS does (`STREET` → `ST`, `NORTH` → `N`);
- the unit is whatever follows `APT`, `UNIT`, `#`, `STE`, `LOT`, `SPACE`, `BLDG` and the like, without leading zeros or dashes;
- the first five digits of the ZIP code.

City and state aren't part of the match, because people write unincorporated areas differently. The ZIP code decides.

## Privacy

- **Addresses are encrypted.** The list is stored encrypted. Lookups use a hash of the cleaned-up address.
- **Nothing logs an address.** The sign-up page never shows an address back.
- **Managers see counts:** how many addresses are on the list and how many accounts were made at them. They don't see who signed up.
- **Removing the list doesn't remove anyone's account.** With the check on, nobody new can sign up until a list is uploaded again.

## Limits

- **This keeps the service for your community, but it doesn't prove where someone lives.** Anyone who knows an address on the list passes the check. If you need proof, use invite codes and check people yourself first. Mailed invitations and an application form that a manager approves are planned for 0.12.
- **Matching covers common spellings, not every one.** Numbered street names written as words ("First St" vs "1st St") and rural route formats aren't treated as the same. Use "Check" to try the forms your residents are likely to type.
- **Not yet tried with a real county export or a real mail server.** It's tested with made-up addresses only.
