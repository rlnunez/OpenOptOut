# Authoring Email Provider Plugins for OpenOptOut

Email provider plugins deliver opt-out emails and handle inbound verification confirmations. Because email delivery transmits removal requests on behalf of members, email plugins are governed by strict isolation controls.

---

## 1. Directory Structure

```text
my-email-provider/
├── manifest.json
├── plugin.py
└── README.md
```

---

## 2. Manifest Schema (`manifest.json`)

```json
{
  "id": "my-email-provider",
  "name": "Custom SMTP Relay Provider",
  "version": "1.0.0",
  "author": "Your Name / Organization",
  "type": "email",
  "description": "Sends opt-out requests through institutional SMTP relay.",
  "entrypoint": "plugin.py",
  "hooks": ["email_provider"],
  "permissions": ["email_provider", "network", "settings_read", "storage"],
  "outbound_domains": ["smtp.example.org"]
}
```

Key manifest rules:
- `type`: Must be `"email"`.
- `hooks`: Must include `"email_provider"`.
- `outbound_domains`: Must declare the exact SMTP or API gateway endpoints.

---

## 3. Security and Identity Safeguards

1. **Encrypted Credentials:** Email credentials (API keys, SMTP passwords) are stored encrypted at rest using HKDF-derived subsystem keys.
2. **Dedicated Relays:** The provider must deliver requests using per-member disposable aliases rather than an administrator's primary mailbox.
3. **Audit Logging:** All outbound transmissions record message ID, broker destination, and timestamp without writing sensitive body PII to unencrypted system logs.
