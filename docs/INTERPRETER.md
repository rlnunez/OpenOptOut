# Broker Interpretation Engine

The interpretation engine is the reframe at the heart of the roadmap: **a broker is a declarative description, not code.** The core reads that description and executes it, knowing nothing about any specific broker. This is what lets brokers become independently-maintained add-ons.

> **Status: unified and on the live path.** The format, the compiler, validation, the dry-run executor, and the real `PlaywrightExecutor` are built. All form opt-outs in `core/optout_engine.py` run through the interpreter. The legacy combo engine has been completely retired.

---

## The three stages

```
BrokerSpec  ──compile_job(spec, member)──►  Job  ──executor.run(job)──►  ExecResult
 (data)                                    (data)                        (result)
```

1. **BrokerSpec** — a declarative description of how one broker's opt-out works. Pure data (JSON/dict). This is what an add-on ships.
2. **compile_job** — turns a spec plus a member's field values into a **Job**: an ordered list of fully-resolved primitive steps (or a rendered email). No field references remain; no broker-specific logic. This is the "produce a job" boundary that lets execution move to a worker fleet later (roadmap item 7) without a rewrite.
3. **Executor** — consumes a Job and performs it. `DryRunExecutor` performs no I/O (used for tests and "validate this add-on"); `PlaywrightExecutor` drives a real browser.

Everything up to the executor is pure and testable without a browser — which is why the whole layer is covered by the Tier-1 test suite.

---

## Writing a BrokerSpec

A spec has a `method` of `form`, `email`, or `manual`.

### Form method

```json
{
  "broker_id": "example-form",
  "name": "Example Form Broker",
  "method": "form",
  "spec_version": "1.0",
  "opt_out_url": "https://optout.example.com/remove",
  "steps": [
    { "kind": "wait_for", "selector": "#optout-form", "timeout_ms": 10000 },
    { "kind": "fill",   "selector": "input[name=firstName]", "field": "first_name" },
    { "kind": "fill",   "selector": "input[name=email]",     "field": "email" },
    { "kind": "select", "selector": "select[name=state]",    "field": "state" },
    { "kind": "check",  "selector": "input[name=confirm]" },
    { "kind": "solve_captcha", "selector": ".g-recaptcha", "optional": true },
    { "kind": "click",  "selector": "button[type=submit]" },
    { "kind": "expect_success", "text": "Your request has been received" }
  ],
  "success_text": "Your request has been received"
}
```

If `opt_out_url` is set and the steps don't begin with a `navigate`, the compiler prepends one automatically.

**Step kinds:**

| kind | purpose | needs |
|---|---|---|
| `navigate` | go to a URL | `url` |
| `fill` | type a member field (or literal) into an input | `selector` + `field` or `value` |
| `select` | choose a `<select>` option | `selector` + `field`/`value` |
| `check` | tick a checkbox/radio | `selector` |
| `click` | click an element | `selector` |
| `wait_for` | wait until a selector appears | `selector`, `timeout_ms` |
| `wait` | fixed delay | `timeout_ms` |
| `submit` | submit the form | `selector` (optional) |
| `expect_success` | confirm the opt-out succeeded | `selector` or `text` |
| `solve_captcha` | hand off to the CAPTCHA layer (roadmap item 4) | `selector` |
| `type` | like `fill`, but key by key, for React/Material UI inputs that ignore a programmatic fill | `selector`, `field` or `value` |
| `autofill` | fill a privacy-request form by reading its labels; stops for a person when unsure (see [PRIVACY_PAGES.md](PRIVACY_PAGES.md)) | nothing — values come from the member |
| `pause_for_human` | stop here for a person. With a `selector`, only when that element is on the page. On the Checklist, **Do it here** replays the flow to this step on a live page (core/live_captcha.py, kind "step"); after the person does it, the flow continues with the next step | `text` (may use `{field}` placeholders) |

Steps run against the current page, or the iframe chosen with `frame` (every action works inside iframes). `click_matching` prefers an element whose whole text matches (so "Kansas" never picks "Arkansas"). A `navigate` URL may contain `{field}` placeholders: values are slugged in the path (`Jane-Doe`) and percent-encoded in the query; a missing value stops the job at compile time.

After a run the executor also checks the page:

- **A refused email address.** If the page says the email is invalid or not allowed, the result is `email_rejected`. The engine remembers that the broker refuses "+" addresses (`brokers.rejects_plus_addresses`) and tries once more with the inbox's plain address. Replies to a plain address are matched by the sender's domain.
- **Success.** A passing `expect_success` step, or the spec's `success_selector` / `success_text`, marks the result `verified`. A form that submits still counts only as **sent**: it becomes **confirmed** when the broker replies, its confirmation link is clicked, or a person checks the listing is gone.
- **CAPTCHAs.** Visible reCAPTCHA and hCaptcha widgets go to a solver plugin or the CAPTCHA queue; invisible reCAPTCHA is ignored, and Cloudflare Turnstile gets up to 15 seconds to pass on its own.

`"optional": true` on a step means *failure of that step doesn't fail the flow* (e.g. an optional field that may not be present). Note: an `optional` `solve_captcha` still pauses if a CAPTCHA is actually present — optional refers to the element's presence, not to skipping a real challenge.

### Email method

```json
{
  "broker_id": "example-email",
  "name": "Example Email Broker",
  "method": "email",
  "spec_version": "1.0",
  "email": {
    "to_address": "privacy@databroker.example",
    "subject_template": "Opt-out request for {full_name}",
    "body_template": "I request removal of {full_name} at {address}, {city}, {state} {zip}.",
    "locale": "en",
    "require_fields": ["full_name", "address"]
  }
}
```

Templates use `{field}` placeholders drawn from the known member fields. `locale` records the language the broker requires the message to be in. `require_fields` lists fields that must be present — the compiler refuses to build the job (fails fast, on the control plane) if the member is missing them.

### Manual method

`{"broker_id": "...", "name": "...", "method": "manual", "instructions": "..."}` — no steps. The request goes on the checklist with `instructions`, filled in for the member. If they mention `{contact_email}`, a one-time address is issued for the broker, so its reply is matched and any confirmation link is clicked automatically, even though a person submitted the form. A manual request is never counted as sent until the person says they've done it or the broker writes back.

---

## Known member fields

A spec may only reference these (the schema validates against the list, so a typo is caught before execution):

`first_name`, `last_name`, `full_name`, `formal_name`, `email`, `phone`, `address`, `city`, `state`, `zip`, `age`, `dob`, `relatives`, `contact_email`, `listing_url`, `street`, `state_name`, `birth_year`, `phone_digits`

`contact_email` is a one-time address for this opt-out (a +address on inboxes that support it); use it for "where should we send the confirmation" boxes. `email` is an address the person wants removed. `state_name` is the full state name, `phone_digits` ten digits without punctuation, and `birth_year` comes from the member's age (it can be a year off). Values are resolved in `core/interpreter/member_fields.py`. When a required field is missing, the opt-out goes on the checklist asking for it.

---

## Validating an add-on

Every spec has a `.validate()` that returns a list of problems (empty = valid). Validation checks the method, that form specs have steps, that each step is a known primitive with the data it needs, that fields are recognized, and that email specs have a valid address and templates. The compiler runs validation first, so a malformed add-on fails at compile time with a clear message — never mid-run against a live site.

To sanity-check an add-on end to end without touching a browser, compile it for a test member and run it through the `DryRunExecutor`: it walks every step and reports whether the job is coherent (and where it would pause for a CAPTCHA).

---

## Why it's built this way

- **Declarative, not code:** an add-on is data, so it can be shared, diffed, reviewed, and validated without executing anything — essential before any add-on marketplace (roadmap items 8) is safe.
- **Compile/execute split:** the compiler produces a serializable Job that a remote worker can run unchanged, so scaling execution onto a worker fleet (item 7) is a deployment change, not a rewrite.
- **Pure until the browser:** everything except the real Playwright calls is side-effect-free and unit-tested, so the highest-leverage design decision in the roadmap is verifiable without a browser.

---

## How the live engine uses it

Most brokers don't have a hand-written BrokerSpec yet. Instead, `core/interpreter/script_bridge.py` (`spec_from_script`) builds one from the broker's existing automation script (the per-broker selectors edited under Admin → Automation Scripts): field selectors become `fill` steps, the submit selector becomes `submit`, the success signal becomes `expect_success`, and a `requires_captcha` flag inserts a `solve_captcha` step before submit.

`execute_optout` then compiles that spec and runs it through `PlaywrightExecutor` with two plugin hooks wired in:

- **`captcha_solver`**: the plugin manager's `solve_captcha` dispatch. If a CAPTCHA-solver plugin is installed, it gets the challenge and returns a token or defers to a human. With no solver installed, the executor pauses and returns `needs_captcha`. No human-in-the-loop handoff exists yet (roadmap item 4).
- **`plugin_form_handler`**: the `fill_form` dispatch, so a plugin can take over a broker whose page the spec format can't express (roadmap item 3).

Curated broker add-ons ship with the app in `backend/plugins/bundled/brokers/` and install themselves at startup (`broker_addon.sync_builtin_brokers`). An admin who turns one off keeps it off; an admin's own add-on with the same id is never replaced.

If a broker has no add-on spec or automation script but the privacy-page finder found a OneTrust, TrustArc or in-house request form on its website, that form is used (`hosted_forms.spec_for_page`). Otherwise `get_or_build_broker_spec` builds a best-guess spec with generic selectors (`firstName`, `email`, submit buttons). It is **not used by default**: guessing can type a person's details into the wrong box on an unknown page. Such brokers go on the checklist instead. Admins can turn guessing on (`automation.best_guess_forms`); even then a guess only counts when the page says the request was received. The legacy combination-matrix engine (`_fill_one_combo`) has been retired; all form executions route through `PlaywrightExecutor`.

## Trying a spec against a real browser

`core/interpreter/live_test.py` compiles one spec and runs it through the real `PlaywrightExecutor`, screenshotting every step. By default it targets a safe built-in test form, not a real broker:

```bash
docker compose exec api python -m app.core.interpreter.live_test            # safe built-in form
docker compose exec api python -m app.core.interpreter.live_test SPEC.json  # your own spec
```

Read the safety note at the top of that file before pointing it at a live broker: a real run sends a real removal request with real data from your IP.
