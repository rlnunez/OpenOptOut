# OpenOptOut — Testing & Diagnostics Guide

This guide covers the test suite you can run on your own system to find problems and report them back. The goal is simple: **run one command, read the summary, and either see all-green or get a precise pointer to what's broken.**

There are three things you can run:

| Command | What it checks | Needs |
|---|---|---|
| `python -m tests.run_tests` | The full tiered suite (logic, DB, plugin protocol, app wiring) | run in the backend container |
| `python -m plugins.smoke_test` | One real plugin over real gRPC, end to end | grpcio + compiled stubs |
| `python -m plugins.preflight_sandbox` | What OS sandbox isolation your host provides | Linux host |

All three use **only what's already installed** — they install nothing.

---

## Running the suite

From inside the running backend container (recommended, because that's where all dependencies exist):

```bash
docker compose exec api python -m app.tests.run_tests
```

Inside the container the backend is installed as a package named `app` and the working directory is `/`, so every `python -m` command in this guide takes an `app.` prefix there: `python -m app.tests.run_tests`, `python -m app.plugins.smoke_test`, `python -m app.plugins.preflight_sandbox`. The unprefixed forms below are for running from `backend/` in a checkout.

Or on a checkout where the backend deps are installed:

```bash
cd backend
python -m tests.run_tests
```

Useful options:

- `--tier N` — run only up to tier N (e.g. `--tier 1` for pure-logic tests).
- `--only NAME` — run only tests whose name contains NAME (e.g. `--only health`).
- `--verbose` — print full tracebacks for any failure (use this when reporting).

### Reading the result

Every test prints one of:

- **PASS** — the check succeeded.
- **FAIL** — something is broken. This is what to report.
- **skip** — the test couldn't run here because a dependency isn't present. This is **not** a problem by itself; it just means "not testable in this environment." The summary lists what was skipped and why.

The end of the run prints a **TEST SUMMARY** block and an **Environment** block. When reporting an issue, copy everything from `TEST SUMMARY` to the end. If a specific test failed, re-run with `--verbose` and include that traceback too.

---

## The tiers

Tests are grouped by what they depend on, so a missing dependency skips a whole tier cleanly instead of erroring.

- **Tier 1 — pure Python logic.** No database, no gRPC. Always runs.
- **Tier 2 — database models.** Needs SQLAlchemy; uses a throwaway in-memory SQLite (never touches your real data).
- **Tier 3 — plugin protocol.** Needs grpcio and the compiled proto stubs.
- **Tier 4 — application wiring.** Needs the FastAPI app to import.

In the container, all four tiers run. On a bare checkout you may see tiers 2/4 skipped — run inside the container for full coverage.

---

## What each test checks

### Tier 1 — logic (always runs)

**`broker_health.classify_failure`** Confirms failure text is sorted into the right bucket (timeout / captcha / form_not_found / error) that the admin Broker Health page displays.
- *Expected:* PASS.
- *If it FAILS:* the keyword matching in `core/broker_health.py` drifted; the health page would show wrong failure categories. Harmless to data, but misleading to operators.

**`broker_health.auto_disable_threshold`** Confirms the auto-disable threshold is a sane positive integer (default 5).
- *Expected:* PASS.
- *If it FAILS:* someone set the threshold to something that would disable brokers on the first blip (too low) or never (too high).

**`permissions.manifest_validation`** Confirms a good plugin manifest validates, and a manifest requesting **both** `read_pii` and `network` is **blocked by default**.
- *Expected:* PASS.
- *If it FAILS:* the most security-sensitive plugin guardrail regressed — a plugin could get both data access and network egress without the explicit exception. Treat a failure here as serious.

**`permissions.method_allowlist`** Confirms declaring a host method (e.g. `storage.get`) without its backing permission (`storage`) is rejected.
- *Expected:* PASS.
- *If it FAILS:* the method-level allowlist isn't enforcing its required permissions.

**`interpreter.spec_validation`** Confirms a well-formed broker description validates, and a malformed one (a step referencing an unknown member field) is rejected.
- *Expected:* PASS.
- *If it FAILS:* the broker-description schema isn't validating add-ons — a broken add-on could reach execution.

**`interpreter.compile_form_job`** Confirms a form spec compiles to a Job with member field references resolved to real values (and the navigate step auto-prepended).
- *Expected:* PASS.
- *If it FAILS:* the compiler isn't resolving member fields — jobs would be dispatched with unfilled placeholders.

**`interpreter.compile_email_job`** Confirms an email spec renders its subject/body templates with member values.
- *Expected:* PASS.
- *If it FAILS:* email add-ons wouldn't personalize; wrong or empty data would be sent to brokers.

**`interpreter.dry_run_executes`** Confirms the dry-run executor walks a compiled job and pauses at a `solve_captcha` step (the CAPTCHA handoff seam).
- *Expected:* PASS.
- *If it FAILS:* the executor contract or CAPTCHA-pause logic is broken.

### Tier 2 — database (needs SQLAlchemy)

**`models.import_and_create`** Imports every ORM model and creates all tables on a fresh in-memory DB.
- *Expected:* PASS.
- *If it FAILS:* a model or column is malformed, or model/migration drift exists. The traceback names the offending table or column. This is also the test that catches a broken `models/database.py` before it takes down the app.

**`broker_health.auto_disable_flow`** The core resilience behavior end to end: a broker stays enabled below the threshold, auto-disables exactly at it, gets flagged for review with the failure classified, and `re_enable` resets everything.
- *Expected:* PASS.
- *If it FAILS:* roadmap item 1 (broker health/auto-disable) is broken — a failing broker either won't be disabled (wastes runs) or is disabled too eagerly. The assertion message says which half broke.

**`broker_health.success_resets_streak`** Confirms one success zeroes the consecutive-failure counter, so an intermittently-failing-but-working broker heals instead of eventually being disabled.
- *Expected:* PASS.
- *If it FAILS:* brokers that work most of the time would still get disabled over time.

### Tier 3 — plugin protocol (needs grpcio + compiled stubs)

**`plugin.proto_stubs_present`** Confirms the compiled gRPC stubs exist and expose all expected RPCs (18 host, 6 plugin).
- *Expected:* PASS.
- *If it SKIPS with "proto stubs not compiled":* the Docker build's protoc step didn't run. Rebuild the image; the plugin system is inactive without stubs.
- *If it FAILS:* RPCs are missing from the protocol — plugins can't talk to the host.

**`plugin.smoke_round_trip`** Runs the full smoke test as a subprocess: a real plugin over real gRPC does init → ping → event → a host storage callback → clean shutdown.
- *Expected:* PASS.
- *If it FAILS:* the plugin protocol/capability plumbing is broken. Re-run `python -m plugins.smoke_test` directly (see below) and send its full output — it prints which of the 6 steps failed.

### Tier 4 — application wiring (needs FastAPI)

**`app.imports`** Imports `main.py` — the whole FastAPI app.
- *Expected:* PASS.
- *If it FAILS:* **this is almost always why the `api` container crash-loops.** The traceback names the exact module and line. This test is the fastest way to diagnose a container that builds but won't start.

**`app.routes_registered`** Confirms the broker, plugin, auth, and broker-health routes are all registered.
- *Expected:* PASS.
- *If it FAILS:* a router failed to include — that feature's API is dead even though the app booted. The message says which prefix is missing.

---

## The two standalone scripts

### Plugin smoke test — `python -m plugins.smoke_test`

Proves the plugin runtime works end to end. Prints six numbered steps and finishes with `PLUGIN SMOKE TEST PASSED` (exit 0).

- *Expected output:* steps [0/6]–[6/6] all logging OK, then the PASSED banner.
- *Common failures:*
  - `grpcio not installed` → you're not in the container; run inside it.
  - `proto stubs not importable` → the protoc build step didn't run; rebuild.
  - a step failing mid-way → the message says which RPC broke; send the output.

### Sandbox preflight — `python -m plugins.preflight_sandbox`

Reports what OS isolation your host can give plugins. Always exits 0 — its job is to report, not pass/fail.

- *Expected output:* a posture line — **FULL**, **PARTIAL**, **MINIMAL**, or **NONE** — plus a checklist of bubblewrap / seccomp / rlimits.
- *What to look for:* run untrusted third-party plugins only when it says **FULL** (bubblewrap + seccomp + rlimits all present). **PARTIAL** or lower means reduced isolation — fine for trusted first-party plugins, not for arbitrary ones. If bubblewrap is missing, install `bubblewrap` and `libseccomp2` in the image.

---

## How to report an issue

1. Run `python -m tests.run_tests` in the container.
2. Copy everything from `TEST SUMMARY` to the end (it includes the environment).
3. For any FAIL, re-run `python -m tests.run_tests --only <name> --verbose` and include that traceback.
4. If a plugin test failed, also paste the output of `python -m plugins.smoke_test`.

That's enough to pinpoint almost anything without another round trip.

---

## A note on what these tests do and don't prove

These tests exercise **logic, data models, the plugin protocol, and app wiring** — the parts that can be checked deterministically. They do **not** prove that a real opt-out against a live broker website succeeds, because that depends on external sites we don't control (that's what the broker-health system is for). Nor do they prove the OS sandbox contains a genuinely malicious plugin; the preflight reports that the isolation is *present*, but confirming it *holds* against a real escape attempt is a separate hardening exercise. Green here means "the machinery is sound," which is the necessary foundation — not the whole story.
