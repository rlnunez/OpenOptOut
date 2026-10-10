# Email Integration & Confirmation Monitoring

OpenOptOut requires access to an email inbox to transmit data removal requests and automatically monitor incoming confirmation links from data brokers.

---

## Dedicated Removal Inbox

> ⚠️ **Always use a dedicated email address for removals.**  
> Data brokers occasionally add email addresses from opt-out requests onto secondary lead and marketing distribution lists. Containing all opt-out communications within a dedicated mailbox (e.g., `removals@yourdomain.com` or `optout.family@gmail.com`) guarantees that your primary personal inbox remains clean and protected.

Supported providers include **Gmail**, **Outlook / Microsoft 365**, **Yahoo**, **Fastmail**, **ProtonMail** (via Proton Mail Bridge), or any standard IMAP/SMTP mail server.

---

## Authentication Methods

### 1. OAuth 2.0 (Recommended — Highest Security)
Connect your inbox using token-based OAuth directly via the onboarding Setup Wizard or in **Settings → Email**.

- **Supported for**: Gmail (Google Workspace) and Outlook (Microsoft 365).
- **Security Advantages**:
  - Eliminates static plaintext passwords stored at rest.
  - Limits application permissions strictly to required mail scopes (`https://mail.google.com/` or `Mail.ReadWrite`).
  - Compatible with enterprise zero-trust and multi-factor authentication (MFA) policies without requiring app-specific password exceptions.
  - Automatically refreshes tokens in the background and supports instant revocation from the provider dashboard.

### 2. App Passwords and SMTP / IMAP (Fallback)
For providers without automated OAuth integrations (such as Fastmail, Yahoo, ProtonMail Bridge, or self-hosted mail servers):

1. Navigate to your provider's security and account settings.
2. Generate a dedicated **App Password** (e.g., Google Account → Security → App Passwords, or Apple ID / Yahoo Account Security).
3. Enter the IMAP/SMTP server hostname, port, username, and generated app password in **Settings → Email**.
4. Test connectivity using the in-app connection probe before saving.

> 🔒 **Password Security Note**: Never use your primary account password. All email passwords entered in OpenOptOut are encrypted at rest using Fernet symmetric encryption before being saved to the database.

---

## Automated Confirmation Tracking

Once configured, the background APScheduler process periodically queries the configured inbox:

- Scans incoming messages for known confirmation signatures and verification tokens.
- Automatically resolves one-click confirmation links using headless HTTP requests.
- Updates removal request states from `Pending Confirmation` to `Confirmed`.
- Extracts broker tracking IDs and logs them to the audit trail for re-check verification.
