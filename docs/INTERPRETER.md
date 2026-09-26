# Broker Interpretation Engine

The interpretation engine is the reframe at the heart of the roadmap: **a broker
is a declarative description, not code.** The core reads that description and
executes it, knowing nothing about any specific broker. This is what lets brokers
become independently-maintained add-ons.

> **Status: skeleton.** The format, the compiler, validation, and a dry-run
> executor are built and tested. The real browser executor is a complete
> control-flow skeleton with the Playwright calls marked as TODOs — those are
> validated in Docker, where Playwright runs. This document describes the design
> and the format so add-ons can be written against it now.

---

## The three stages

```
BrokerSpec  ──compile_job(spec, member)──►  Job  ──executor.run(job)──►  ExecResult
 (data)                                    (data)                        (result)
```

1. **BrokerSpec** — a declarative description of how one broker's opt-out works.
   Pure data (JSON/dict). This is what an add-on ships.
2. **compile_job** — turns a spec plus a member's field values into a **Job**: an
   ordered list of fully-resolved primitive steps (or a rendered email). No field
   references remain; no broker-specific logic. This is the "produce a job"
   boundary that lets execution move to a worker fleet later (roadmap item 7)
   without a rewrite.
3. **Executor** — consumes a Job and performs it. `DryRunExecutor` performs no
   I/O (used for tests and "validate this add-on"); `PlaywrightExecutor` drives a
   real browser.

Everything up to the executor is pure and testable without a browser — which is
why the whole layer is covered by the Tier-1 test suite.

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

If `opt_out_url` is set and the steps don't begin with a `navigate`, the compiler
prepends one automatically.

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

`"optional": true` on a step means *failure of that step doesn't fail the flow*
(e.g. an optional field that may not be present). Note: an `optional`
`solve_captcha` still pauses if a CAPTCHA is actually present — optional refers to
the element's presence, not to skipping a real challenge.

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

Templates use `{field}` placeholders drawn from the known member fields. `locale`
records the language the broker requires the message to be in. `require_fields`
lists fields that must be present — the compiler refuses to build the job (fails
fast, on the control plane) if the member is missing them.

### Manual method

`{"broker_id": "...", "name": "...", "method": "manual"}` — no steps. The engine
queues it for a human.

---

## Known member fields

A spec may only reference these (the schema validates against the list, so a
typo is caught before execution):

`first_name`, `last_name`, `full_name`, `formal_name`, `email`, `phone`,
`address`, `city`, `state`, `zip`, `age`, `dob`, `relatives`

---

## Validating an add-on

Every spec has a `.validate()` that returns a list of problems (empty = valid).
Validation checks the method, that form specs have steps, that each step is a
known primitive with the data it needs, that fields are recognized, and that
email specs have a valid address and templates. The compiler runs validation
first, so a malformed add-on fails at compile time with a clear message — never
mid-run against a live site.

To sanity-check an add-on end to end without touching a browser, compile it for a
test member and run it through the `DryRunExecutor`: it walks every step and
reports whether the job is coherent (and where it would pause for a CAPTCHA).

---

## Why it's built this way

- **Declarative, not code:** an add-on is data, so it can be shared, diffed,
  reviewed, and validated without executing anything — essential before any
  add-on marketplace (roadmap items 8) is safe.
- **Compile/execute split:** the compiler produces a serializable Job that a
  remote worker can run unchanged, so scaling execution onto a worker fleet
  (item 7) is a deployment change, not a rewrite.
- **Pure until the browser:** everything except the real Playwright calls is
  side-effect-free and unit-tested, so the highest-leverage design decision in
  the roadmap is verifiable now, not only after a full Docker run.

---

## What still needs Docker

The `PlaywrightExecutor` has complete control flow (step dispatch, CAPTCHA
pause, optional-step handling, result shaping) but its actual browser calls are
marked `TODO(playwright)`. Wiring them is filling in those marked lines against a
real Playwright `page`, mirroring the logic already in `core/optout_engine.py`,
then confirming a compiled Job runs against a real (or test) broker page. That is
the one part of this layer that can only be validated with Playwright installed.
