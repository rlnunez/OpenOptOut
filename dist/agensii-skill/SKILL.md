---
name: data-broker-optout
description: Write a new privacy data-broker opt-out plugin or repair an existing broker flow. Guides AI coding agents to create safe, zero-PII, anti-brittle browser automation specs adhering to COPPA, GDPR, and sandboxed Playwright standards.
---

# Writing or Fixing Data-Broker Opt-Out Plugins

This skill instructs AI coding agents on how to construct, audit, and repair automated opt-out plugins for people-search engines and data brokers.

Plugins are **strictly declarative data specifications** (`manifest.json`, `spec.json`, and `README.md`), never unconstrained executable scripts. The host system compiles this specification into sandboxed browser automation jobs (Playwright). Because this system removes family records and minors' data (COPPA & GDPR), **every plugin change is security-relevant**.

---

## 1. Security, Privacy & Compliance Standards (Non-Negotiable)

1. **Strict Data Minimization (COPPA & GDPR):**
   - Reference only the fields in `steps` or `instructions` that the specific broker's form explicitly mandates.
   - Never request or populate `dob`, `relatives`, `phone`, `street`, or `age` "just in case".
   - Minors' data is handled by privacy tools; minimize every field requested.
2. **Prohibited Credentials & Mandatory Manual Fallback:**
   - **Never** fill, automate, or prompt for Social Security Numbers (SSNs), government ID numbers, driver's licenses, passport scans, passwords, or arbitrary file uploads.
   - If a broker requires any of these (e.g. LexisNexis, TLOxp), the plugin **must** use `"method": "manual"` with clear, plain-language instructions explaining that the user must submit directly because privacy platforms do not store or transmit identity documents.
3. **Email Boundary Isolation (`contact_email` vs. `email`):**
   - Use `contact_email` for any "reply / confirmation email" field or `{contact_email}` placeholder. This injects an isolated, sub-addressed alias (`+alias@...`) that allows automated email verification matching without exposing the person's real primary email.
   - Use `email` ONLY when the broker's form explicitly asks for "an email address you want removed from our search engine". Never conflate the two.
4. **No Marketing or Promotional Opt-Ins:**
   - Only check boxes that represent strictly mandatory legal certifications (*"I certify under penalty of perjury that I am this individual"*).
   - Never tick optional boxes for marketing, newsletter subscriptions, or commercial partner offers.
5. **Sandbox & Domain Isolation:**
   - Broker automation runs inside a restricted sandbox with declared outbound domains. Step URLs and `search_url` must stay strictly on the broker's official domains.
   - Never navigate to or interact with third-party tracking pixels, ad networks, or external analytics.
6. **Synthetic Rehearsal Safety:**
   - **Never enter a real person's details on a broker site during development or testing.**
   - Rehearse flows exclusively using synthetic mock fixtures (e.g., `"Jordan Example"`, `rehearsal@example.invalid`), and stop before triggering the final submission button.
7. **Human-in-the-Loop Safety:**
   - If a broker flow requires SMS verification codes, phone calls, CAPTCHA challenges, picking a profile among duplicates, or manual identity confirmation, use a `pause_for_human` step with plain, non-technical instructions.

---

## 2. Declarative Vocabulary & Architecture

### Available Step Kinds (`STEP_KINDS`)
Declarative specs are restricted to a closed list of safe primitive actions:
- `navigate`: Go to a URL.
- `fill`: Populate a member field or literal value into a form input.
- `type`: Key-by-key character entry (for dynamic frontends that ignore direct value assignment).
- `select`: Choose an option in a `<select>` dropdown.
- `check`: Tick a checkbox or select a radio option.
- `click`: Click an element matching a selector.
- `click_matching`: Click an element matching specific button/link text or field value.
- `press`: Send a keyboard key (e.g., `"Enter"`, `"Tab"`).
- `frame`: Switch execution context to an iframe (or `"main"` to exit).
- `scroll`: Scroll an element into view or scroll the page.
- `wait_for`: Pause until a selector appears in the DOM.
- `wait`: Fixed delay in milliseconds (use sparingly).
- `submit`: Trigger standard form submission.
- `expect_success`: Assert an explicit success signal (text or selector) confirming the request was accepted.
- `solve_captcha`: Request automated or manual CAPTCHA resolution.
- `pick_listing`: Identify and navigate to the person's specific listing from search results.
- `pause_for_human`: Halt automation and prompt the human operator to take over.

### Known Fields (`KNOWN_FIELDS`)
- **Names:** `first_name`, `last_name`, `full_name`, `formal_name`
- **Location:** `address`, `street`, `city`, `state`, `state_name`, `zip`
- **Identifiers:** `phone`, `phone_digits`, `phone_dashed`, `phone_e164`, `all_phones`, `email`, `all_emails`
- **Demographics:** `age`, `age_range`, `dob`, `dob_iso`, `birth_year`, `birth_month`, `birth_day`, `relatives`
- **Routing & Removal:**
  - `contact_email`: Isolated confirmation alias address.
  - `listing_url`: Direct URL to the record being removed.

---

## 3. Step-by-Step Plugin Authoring Workflow

### Step 1: Discover the Opt-Out Flow
1. Locate the broker's official opt-out page and privacy policy.
2. Note all required fields, submission buttons, CAPTCHAs, email verification steps, and human-only requirements.
3. Record the source URL in `spec.source`.

### Step 2: Choose the Method
- `"method": "form"`: Standard web form automation (with optional `pause_for_human` steps).
- `"method": "manual"`: Broker requires physical mail, phone calls, or ID documents. Provide detailed, numbered steps in `instructions`.
- `"method": "email"`: Broker accepts requests by email. Specify `email.to_address`.

### Step 3: Write `spec.json`
- Ensure `broker_id` matches the directory name and `manifest.id`.
- **Selector Stability:**
  - Prefer semantic attributes: `[name=...]`, `[aria-label=...]`, stable `#id`, or `click_matching` on visible button text.
  - **Never** use auto-generated framework IDs (e.g. `#ember1234`, `[id^=react-]`, `.css-19z2x3a`) or deep positional CSS paths (`div > div:nth-child(3)`).
- **Synchronize Requirements:**
  - If any step references `listing_url`, add `"listing_url"` to `spec.requires`.
  - If email confirmation is required, add `"email_confirmation"` to `spec.requires` and ensure `contact_email` is used.
- **Human Guidance:** `pause_for_human.text` and `instructions` must be written for non-technical users. Name buttons exactly as displayed on screen.
- **Verification Integrity:** Leave `last_verified` empty unless you personally executed the flow against the live site.

### Step 4: Write `manifest.json`
- Set `id`, `broker_id`, and directory name identically.
- Assign `"type": "brokers"`, a plain-language `description`, and semantic `version`.
- **Bot Wall Mitigation:** If the broker employs aggressive bot barriers (Cloudflare Turnstile, perimeter walls) or is unverified live, set `"starts_enabled": false`.

### Step 5: Validate
Run the validation script to verify schema compliance, requirement synchronization, and security invariants:
```bash
python3 tools/validate.py <path/to/plugin>
```

---

## 4. Fixing a Broken Plugin

When an existing broker flow stops working:
1. Identify the failing step index and inspect the page snapshot.
2. Change **only what moved** (typically updated button text, altered `name` attributes, or new intermediate confirmation screens).
3. Preserve existing field bindings, URLs, and instructions unless the broker's underlying procedure has changed.
4. Bump `manifest.version`.
5. Run the validator.

