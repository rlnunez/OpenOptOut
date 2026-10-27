# Mock People Directory

| Field | Value |
|---|---|
| **Method** | Automated Web Form with CAPTCHA Gate |
| **Opt-out URL** | https://example.com/optout |
| **Human Checkpoint** | Solve visual CAPTCHA and click email verification link |
| **Response Window** | 45 Days (CCPA/CPRA) / 30 Days (GDPR) |
| **Source Citation** | https://example.com/privacy-center/opt-out-guidelines |
| **Last Verified** | Reference example |

## Flow Walkthrough

1. The user provides their listing URL on the directory (`listing_url`).
2. The automation fills the listing link and an isolated confirmation alias (`contact_email`).
3. Automation pauses safely (`pause_for_human`) to allow the user to complete the visual CAPTCHA challenge without leaking private data to third-party bypass services.
4. The submission button is clicked using visible label matching (`Submit Removal Request`).
5. Success text is asserted.
6. The user clicks the verification link in their email inbox.

