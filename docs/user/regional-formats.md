# Regional formats

An admin chooses how dates, times and numbers look for everyone under **Settings → Regional formats**. You need the *System settings* permission. The default is the United States: "Oct 11, 2026", "3:05 PM", "1,234.5", and weeks that start on Sunday.

| Setting | Choices | Default |
|---|---|---|
| Country or region | US, Canada, Mexico, UK, Germany, Brazil, Japan and others | United States |
| Clock | Usual for the region, 12-hour, 24-hour | Usual for the region |
| Weeks start on | Usual for the region, Sunday, Monday, Saturday | Usual for the region |
| Digits | 0–9 in every language, or each language's own digits | 0–9 |
| Time zone for times on screen | Empty (each person's device), or a name like `America/Chicago` | Empty |

The region and each person's language are used together:

- **Numbers** follow the region for everyone. With the region set to the US, every language shows "1,234.5".
- **Dates** use the person's language for month and day names, and the region's clock unless you pick one. A German speaker with the region set to the US sees "11. Okt. 2026, 3:05 PM". An English speaker with the region set to the UK sees "11 Oct 2026, 15:05".
- **Weeks** start on the region's usual day (Sunday in the US, Monday in the UK) unless you pick one.

The browser's own date tables do this work, so nothing extra needs translating.

**Where it applies**
- Every date, time and number on screen. The test `i18n.regional_formats_used` keeps new screens in line.
- The Calendar page: the first day of the week, and opt-out times.
- Text the server writes, which is still English: notice emails and the PDF removal report. There, only the order of day, month and year follows the region ("Oct 1, 2026", "1 Oct 2026" or "2026-10-01").

**Where it doesn't apply**
- Opt-out letters and credit-freeze letters. Their dates follow the law and the country they're sent to, not the admin's choice.
- Dates typed into broker forms. These use the format each broker's form expects.
- Date pickers. These are drawn by each person's browser.

**For developers:** format with `fmtDate`, `fmtDateTime`, `fmtClock` and `fmtNumber` from `frontend/src/i18n/format.js`, and with `core/regional.format_date` on the server. Times from the server without a zone are treated as UTC. A plain date (`2026-10-11`) is a calendar day and never shifts with the time zone.
