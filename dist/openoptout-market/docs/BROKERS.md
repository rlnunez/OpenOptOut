# Authoring Broker Add-Ons for OpenOptOut

Broker add-ons automate the removal of personal information from people-search directories and commercial data brokers. They are pure declarative specifications: they describe the steps required to complete an opt-out without writing custom executable code.

---

## 1. Directory Structure

A broker add-on must contain exactly three files:

```text
my-broker/
├── manifest.json
├── spec.json
└── README.md
```

---

## 2. Manifest Schema (`manifest.json`)

The manifest registers the broker with the OpenOptOut engine:

```json
{
  "id": "my_broker",
  "type": "brokers",
  "broker_id": "my_broker",
  "name": "My Broker Name",
  "version": "1.0.0",
  "author": "Your Name / Organization",
  "description": "Automated opt-out for My Broker Name.",
  "spec_file": "spec.json",
  "difficulty": "medium",
  "is_property_broker": false,
  "starts_enabled": true
}
```

Key manifest rules:
- `id`, `broker_id`, and `spec.json`'s `broker_id` must match exactly.
- `type`: Must be `"brokers"`.
- `difficulty`: One of `"easy"`, `"medium"`, or `"hard"`.
- `is_property_broker`: Set to `true` if the directory indexes real estate / deeds rather than personal people records.

---

## 3. Declarative Specification (`spec.json`)

The declarative specification defines the steps executed by OpenOptOut's sandboxed browser runner:

```json
{
  "broker_id": "my_broker",
  "name": "My Broker Name",
  "method": "form",
  "spec_version": "1.0",
  "opt_out_url": "https://example.com/optout",
  "search_url": "https://example.com/search?q={full_name}",
  "listing_pattern": "https://example.com/profile/*",
  "steps": [
    {
      "kind": "wait_for",
      "selector": "form#optout"
    },
    {
      "kind": "fill",
      "selector": "input[name=first_name]",
      "field": "first_name"
    },
    {
      "kind": "fill",
      "selector": "input[name=last_name]",
      "field": "last_name"
    },
    {
      "kind": "fill",
      "selector": "input[name=requester_email]",
      "field": "contact_email"
    },
    {
      "kind": "pause_for_human",
      "selector": "div.captcha-container",
      "text": "Please solve the security challenge on screen, then press 'I have done this'."
    },
    {
      "kind": "click_matching",
      "selector": "button",
      "value": "Submit Request"
    },
    {
      "kind": "expect_success",
      "text": "Your removal request has been received"
    }
  ],
  "legal_basis": ["ccpa", "cpra", "gdpr"],
  "statutory_response_days": 45,
  "requires": ["email_confirmation"],
  "source": "https://example.com/privacy-policy",
  "last_verified": ""
}
```

---

## 4. Supported Step Kinds

| Kind | Required Attributes | Description |
|---|---|---|
| `wait_for` | `selector` | Waits for a DOM element to become visible. |
| `fill` | `selector`, `field` | Clears and fills an input field with member data. |
| `type` | `selector`, `field` | Types text with simulated keystroke intervals. |
| `check` | `selector` | Checks a checkbox or radio button. |
| `select` | `selector`, `value` | Selects a dropdown option by value or visible label. |
| `click` | `selector` | Clicks an element matched by CSS selector. |
| `click_matching` | `selector`, `value` | Clicks an element whose text matches `value`. |
| `pause_for_human` | `selector`, `text` | Pauses automation for human CAPTCHA or verification. `text` must be >= 20 characters. |
| `expect_success` | `text` | Asserts that confirmation text appears on the page. |

---

## 5. Privacy, COPPA, and Security Requirements

1. **Email Isolation:** Always use `contact_email` for form email inputs. `contact_email` supplies a one-time isolated relay address, protecting the member's real email address.
2. **Data Minimization:** Only request fields that the broker's form explicitly requires. Never add fields speculatively.
3. **Prohibited Credentials:** Never automate forms that require Social Security Numbers, government IDs, credit cards, or account passwords.
4. **No Real PII in Git:** Test fixtures must strictly use synthetic data (such as "Jane Sample", "12 Oak St", and "@example.invalid").
