# PrivacyShield — Architectural Roadmap: Broker-Addon Engine

Status: **partly built.** This document captures the intended direction; each
item carries its own STATUS line, and the "Status at a glance" table below
summarizes what is shipped vs. still open. It reframes PrivacyShield from a
monolithic opt-out app into an **interpretation engine that runs broker
add-ons**, where the core hosts orchestration and each broker is maintained
independently.

The guiding principle: **the core should not contain broker-specific logic.**
The core interprets a declarative description of how a broker's opt-out works
(form, email, the language an email must be in, multi-step flows) and executes
it. Brokers become data + optional code, maintained by whoever owns that add-on.

---

## Vision in one paragraph

Each data broker becomes its own installable add-on describing how to opt out —
the forms on the page, the fields to fill, whether an email must be sent and in
what language, and any CAPTCHA or multi-step handling. The core provides: an
interpretation engine that executes these descriptions, a CAPTCHA-handling layer
with pluggable solvers and a human-in-the-loop fallback, health monitoring that
disables a broken broker before it wastes resources or crashes runs, and a
distribution mechanism (starting as a Git-backed repository, eventually a
marketplace) so add-ons can be discovered, installed, and updated independently
of the core.

---

## Status at a glance

| # | Item | Status |
|---|------|--------|
| 1 | Broker-as-add-on model | Partial — spec format exists; declarative-vs-code boundary still open |
| 2 | Interpretation engine | Built, live; legacy combination-matrix engine still the fallback |
| 3 | Multi-form page add-on | Partial — `fill_form` hook wired; richer page context still open |
| 4 | CAPTCHA handling | Partial — solver hook wired; human-in-the-loop default not built |
| 5 | Enable/disable brokers | Built |
| 6 | Broker health + auto-disable | Built |
| 7 | Control plane + worker fleet | Not started (rate-limiting/chunking groundwork built) |
| 8 | Git repo → marketplace | Not started |
| 9 | Capacity calculator | Not started |
| 10 | Email-first via parent companies | Substantially built; automatic trigger, live test, legal review open |
| 11 | First-run setup wizard | Built; email-mode switching + grace period not built |
| 12 | School district parent-portal SSO | Not started |
| 13 | SAML 2.0 SSO | Built; not yet run against a live external IdP |
| 14 | Built-in HTTPS | Built; DNS-01 and some real-host runs outstanding |
| 15 | Memory hygiene | Not started |
| 16 | Operational visibility | Part A built; parts B (log viewer) and C (verbosity) not started |

---

## Work items

### 1. Broker-as-add-on model
Make every broker its own add-on rather than a row of hardcoded behavior.
- A broker add-on = a manifest + a declarative opt-out description (+ optional
  custom code for the hard cases).
- The description covers: opt-out method (form / email / manual / phone),
  the fields and how to fill them, and for email brokers, the **required
  language / template / locale** the email body must be in.
- Users select which brokers to enable or disable individually.
- **Design tension to resolve:** how much is declarative (safe, sandboxable,
  easy to write) vs. how much needs real code (powerful, but reintroduces the
  untrusted-code security problem). Likely a spectrum: declarative for simple
  brokers, sandboxed plugin code for complex ones.
- **STATUS: partial.** The declarative `BrokerSpec` format (item 2) is the
  add-on description, and per-broker enable/disable is built (item 5). Not yet
  built: packaging a broker as an independently installable add-on (manifest +
  spec + optional code), and the declarative-vs-code boundary is still open.

### 2. Interpretation engine (the core's main job)
A runtime that reads a broker add-on's declarative description and executes it
against the live site — filling forms, sending the correctly-localized email,
or walking a multi-step flow — without broker-specific logic in the core.
- This is the heart of the reframing. Getting the description format right (a
  small DSL or schema) is the highest-leverage design decision in this roadmap.
- **STATUS: built and wired into the live path.** The declarative `BrokerSpec`
  format, the compiler, and both `DryRunExecutor` and `PlaywrightExecutor` exist
  and are tested. The real form opt-out path (`execute_optout`) now routes
  through the interpreter: a `script_bridge` builds a spec from each broker's
  existing `BrokerScript`, and the executor runs it with the plugin manager's
  CAPTCHA-solver and fill_form dispatchers wired in (items 3 & 4 fire live).
  See `docs/INTERPRETER.md`.
- **Two engines coexist during migration.** Brokers with a usable `BrokerScript`
  use the interpreter; the rest fall back to the legacy combination-matrix engine
  (`_fill_one_combo`), unchanged. **Goal: retire the legacy engine** (less to
  maintain). Prerequisite: port the combination-matrix logic (name×address×phone
  permutations) into the interpreter or the spec format, then backfill scripts so
  every broker has one. Until then the fallback stays as a safety net.

### 3. Multi-form / page interpreter (scraper) — AS AN ADD-ON
**Reframed:** multi-form-per-page handling is NOT built into the core engine.
Instead it's an extension point — an add-on registers a strategy for the messy
pages that the declarative spec format can't express. The core provides a solid
default (single-form execution via the interpreter) and the hook; a plugin
handles the hard multi-form cases for a specific broker.

Rationale: multi-form pages vary enormously and change constantly. Baking one
scraping approach into the core locks everyone into it; making it an add-on lets
each deployment/community contributor extend the platform as needed. This cashes
in the plugin architecture that already exists.

**What this requires (API-robustness work, not core features):**
- ~~Connect the existing `fill_form` plugin hook to the interpreter/executor so a
  plugin can actually take over execution for a broker.~~ **Done** — the
  plugin manager's fill_form dispatcher is wired into `PlaywrightExecutor` on
  the live path (see item 2).
- Give the hook enough context (the page/DOM handle or a mediated interface, the
  member fields it's permitted to use) to do real multi-form work.
- Keep it inside the sandbox + permission model already built.

**STATUS: partial.** Hook wired; the richer page context and a real multi-form
plugin are still open.

### 4. CAPTCHA handling — AS AN ADD-ON (pluggable solvers)
**Reframed:** the core does NOT solve CAPTCHAs. It detects them, pauses, and
hands the challenge to whatever CAPTCHA-solver add-on a deployment has installed
— or to a human, if that's the installed strategy. Different deployments plug in
different solvers (human-in-the-loop, a paid solving service, an AI-vision
solver) based on their own budget and ethics. The core stays neutral and honest:
it exposes the seam, it doesn't pick the answer.

Rationale: CAPTCHA solving is the hardest, most variable, most ethically-loaded
part of the problem. Making it an add-on means the core never has to "solve" it
(which it can't do universally anyway), and the community owns the fight — the
open-source strategy applied concretely.

**What this requires (the real gap to close):**
- ~~Add a CAPTCHA-solving HOOK + capability to the plugin API.~~ **Done** — a
  `solve_captcha` hook exists in the plugin API (`plugins/proto/plugin.proto`,
  `plugins/manager.py`) and `PlaywrightExecutor` takes a `captcha_solver`
  callback wired from the plugin manager. With no solver installed it still
  pauses (`needs_captcha`). (`DryRunExecutor` only simulates the handoff.)
- Define the challenge/solution contract: the plugin receives challenge context
  (type, site-key, page URL, maybe a screenshot) and returns a token/answer, or
  signals "hand to a human."
- A human-in-the-loop reference implementation as the honest default (pause,
  surface to an operator, resume) so the platform works out-of-the-box without a
  paid service.
- All within the existing sandbox/permission/monitoring model — a CAPTCHA solver
  that phones a third party is exactly the kind of thing the network-egress and
  read_pii guardrails were built to govern.

**Honest note:** exposing these seams makes the add-ons *possible*; it does not
make CAPTCHAs *solved*. A no-CAPTCHA-solver deployment still can't get past them
except via the human path. The value is that the platform is extensible enough
that someone CAN build the solver, rather than the core pretending to.

**STATUS: partial.** Solver hook built and wired. Not built: the
human-in-the-loop reference implementation (pause, surface to an operator,
resume) — so today a CAPTCHA with no solver plugin installed just stalls that
opt-out. No solver plugin ships.

### 5. Enable/disable brokers individually
Users choose which brokers are active. Disabled brokers consume no resources and
are skipped by the engine and scheduler.

**STATUS: built.** `Broker.enabled` (`models/database.py`); only enabled brokers
are attempted by the batch runner. Brokers can be disabled manually by an admin
or automatically by the health monitor (item 6).

### 6. Broker health reporting + auto-disable (resilience)
A mechanism to report that a broker's add-on isn't working, and let an admin
(or the system automatically) disable it so it doesn't crash runs or waste
resources.
- Detect failure (add-on errors, form-not-found, repeated timeouts, CAPTCHA
  walls it can't pass).
- Surface it to the admin with a clear "this broker is broken" signal.
- Auto-disable after a threshold; never let one broken broker take down a batch.
- This is the single most important reliability feature for running at scale —
  it's what turns "one broker breaks and wastes hours" into "one broker is
  quietly marked broken and skipped."

**STATUS: built.** `core/broker_health.py` + the `BrokerHealth` model record
every attempt, classify failures (timeout / form_not_found / captcha / error),
auto-disable after a run of consecutive failures (a success resets the count),
and flag `needs_review` for the admin. Health tracking never raises into the
opt-out pipeline.

### 7. Distributed execution: control plane + worker fleet (horizontal scaling)
Split the system into two roles so the removal workload can scale independently
of the interface, and eventually run on separate machines.

**The problem this solves:** a single server can only run so many concurrent
browser automations before it's out of CPU/RAM. Vertical scaling (a bigger box)
hits a hard ceiling fast — headless browsers are heavy. Past roughly a couple
hundred active profiles, you physically need **multiple removal/bot servers**
doing the actual opt-out calls in parallel. The interface, meanwhile, is light
and does not need to scale the same way.

**Target architecture:**
- **Control plane (1 instance):** the web UI/API, the database, the scheduler,
  broker/add-on management, health monitoring. Light load. This is what an
  operator interacts with. It does NOT run browser automations itself.
- **Worker fleet (N instances):** stateless "remover"/"bot" servers that pull
  jobs from a queue, run the actual Playwright automations and email sends
  against brokers, and report results back. Add more workers to remove faster;
  they scale laterally.
- **A job queue between them** (e.g. Redis/RQ, Celery, or a lightweight broker)
  replaces the current in-process APScheduler-drives-everything model. The
  scheduler on the control plane *enqueues* work; workers *consume* it.

**Chunked / batched execution:**
- Removal work is dispatched in **chunks** rather than one giant run, so a batch
  can be spread across workers, retried per-chunk on failure, rate-limited per
  broker, and paused/resumed without losing the whole batch.
- Chunk size and concurrency become tunable knobs per deployment.
- **Partly built already:** the scheduler already throttles dispatch with a
  per-member daily cap AND a global daily ceiling (whichever is hit first),
  admin-configurable with per-member overrides, and orders each day's batch
  worst-offenders-first (`core/broker_priority.py`, `scheduler._select_pending_batch`).
  This is the per-member/global rate-limiting a worker fleet needs; the remaining
  work is moving execution of those chunks onto queue-fed workers.

**Why this is a big change (be honest):**
- The current design runs the scheduler and the opt-out engine **in the same
  process as the API** (`core/scheduler.py` + `core/optout_engine.py` inside the
  API container). Splitting them means introducing a queue, making workers
  stateless, and moving shared state (sessions, browser context, screenshots,
  PII access) across a network boundary safely.
- **Interacts with the plugin sandbox:** if workers run broker add-ons / plugins,
  the sandbox has to work *on the workers*, not the control plane — and the
  read_pii + network exposure now spans machines. Heavier security implication.
- **Interacts with the database:** SQLite cannot be the shared store across
  multiple machines. A worker fleet effectively *requires* PostgreSQL (already
  supported as an option) — SQLite is single-node only.
- **Interacts with proxies:** multiple workers making broker calls need
  coordinated proxy/IP management so they don't collide or get the shared IP
  pool banned.

**Scale guidance (rough, for the roadmap):**
- **Family / handful of people:** single container, in-process scheduler. What
  exists today. No queue needed.
- **Up to ~100–200 active profiles:** single beefier box may cope; chunked
  batching helps; still one node.
- **Couple hundred+ / institutional:** control plane + worker fleet + queue +
  PostgreSQL becomes necessary. Removal is the part that needs lateral scaling;
  the interface does not.

**Build order note:** this is infrastructure, not a user feature — do it when
load actually demands it, but design the job boundary *early* (item 2's engine
should be written as "produce a job" / "execute a job" from the start, so
splitting execution onto workers later is a deployment change, not a rewrite).

**Worker capacity planning (profiles-per-worker):**
How many profiles a single worker can handle is NOT a fixed number — it depends
on how many brokers are enabled and how heavy each opt-out is. It must be
**measured on real hardware**, not guessed. The variables:

- **Enabled broker count per profile** is the dominant factor. One profile with
  400 enabled brokers is ~400 opt-out operations; the same profile with 20
  enabled brokers is ~20. Worker capacity scales with *total opt-out operations*
  (profiles × enabled brokers), not raw profile count.
- **Method mix.** Email-method opt-outs are cheap (send a templated email —
  low CPU, fast). Form-method opt-outs are expensive (spin up a headless
  browser, navigate, fill, submit — high RAM, seconds-to-minutes each).
  CAPTCHA-gated brokers are the most expensive (may block on a solver or a human
  handoff). A worker's real limit is set by how many *concurrent browser
  automations* it can hold in RAM, not by email sends.
- **Concurrency per worker.** Each simultaneous Playwright browser context uses
  meaningful RAM (rough order: ~150–350MB each, to be measured). Available RAM ÷
  per-context RAM ≈ max concurrent form opt-outs per worker.
- **Recheck cadence.** Profiles aren't opted-out continuously — work happens on
  a schedule and on re-check intervals. Throughput needed = total operations ÷
  the window they must complete in, which sets how many workers you need.

**The planning formula (fill the measured constants in later):**

```
operations_per_cycle   = active_profiles × avg_enabled_brokers_per_profile
worker_throughput       = concurrent_slots_per_worker × (3600 / avg_seconds_per_form_optout)
                          [operations per hour per worker, for form-method work]
workers_needed          = operations_per_cycle ÷ (worker_throughput × hours_in_completion_window)
```

`concurrent_slots_per_worker` and `avg_seconds_per_form_optout` are the two
numbers that MUST come from benchmarking, not estimation. Until then, treat any
profiles-per-worker figure as unknown.

**How to get the real numbers (the benchmark to run once the engine works):**
1. On a representative worker (fixed CPU/RAM), run a batch of form-method
   opt-outs against real brokers and record: peak RAM per concurrent context,
   average wall-clock seconds per opt-out, and failure/retry rate.
2. Derive `concurrent_slots_per_worker` = usable RAM ÷ measured per-context RAM.
3. Publish a small table in this doc: for a given worker spec, "X concurrent
   slots, Y seconds/op → Z operations/hour → supports N profiles at M enabled
   brokers on a daily cycle." Replace all guidance below with measured values.

**Placeholder guidance until measured (DO NOT provision money against this):**
- These are order-of-magnitude guesses to be replaced, not commitments.
- A single modest worker (e.g. 4 vCPU / 8GB) likely holds only a *handful* of
  concurrent headless-browser opt-outs (single digits to low teens), which is
  why form-heavy deployments need workers early. Email-heavy deployments scale
  far better on the same box.
- The practical takeaway that IS safe to state: **capacity is driven by enabled
  form-method brokers × profiles, and form/CAPTCHA work — not profile count —
  is what exhausts a worker.** Enabling fewer, higher-value brokers per profile
  dramatically increases how many profiles a worker supports.

**STATUS: not started** beyond the rate-limiting/chunking groundwork noted
above. Execution still runs in the API process on APScheduler; no job queue.

### 8. Distribution: Git-backed repo → marketplace
Start simple, grow into a marketplace.
- **Phase 1:** a Git repository of add-ons the system can pull from. An add-on's
  manifest can link back to other Git repos, allowing automated installation
  (pull an add-on, which pulls its dependencies).
- **Phase 2:** a curated marketplace with discovery, ratings, versioning, and
  trust signals.
- **Security is the hard part here** (see cross-cutting concerns): automated
  installation from arbitrary Git repos is a supply-chain attack surface. This
  must ride on the existing sandbox + permission + method-allowlist model, and
  needs add-on signing / provenance / review before it's safe for a marketplace.

**Prior art worth following for phase 2 (added as a note, not yet designed):**
Drupal's model is a good reference point — Drupal.org itself is the catalog
(listings, versioning, ratings/usage signals), but the actual code for a
module lives in the developer's own repo; Drupal.org just points at it (in
practice, often a packaged zip on the developer's GitHub releases). The
marketplace is a *directory*, not a code host. That maps cleanly onto phase 1
above (the manifest + linked Git repo already work this way) — phase 2 is
mostly about building the discovery/browsing layer on top, plus the
trust/signing work already called out. Browsing and installing from directly
inside the app (the way WordPress's plugin browser works — search, one-click
install, no leaving the admin UI) is the right end-state for the in-app side
of this; PrivacyShield's existing Plugins admin page would be the natural
place for that browser once phase 2 exists.

For the marketplace *website* itself (the public catalog/directory site,
separate from PrivacyShield's own app) — WordPress is worth considering as
the actual host, given how well-trodden "WordPress + a plugin-directory-style
theme/plugin" is for exactly this kind of catalog site. That's a separate
build from PrivacyShield's own codebase (a marketing/directory site, not
something bundled in this repo) and would need its own listing format, review
process, and a way to keep it in sync with what the in-app browser reads —
worth scoping properly, including how it talks to the in-app browser (a
simple JSON feed the app polls is the obvious starting point), when phase 2
is actually picked up.

**STATUS: not started.**

### 9. Capacity calculator (operator-facing planning tool)
A form where an operator enters their worker's system specs and their intended
broker mix, and sees how many broker add-ons / profiles that worker can support
— broken down by opt-out type (**email vs. form vs. form-with-CAPTCHA**).

**Inputs the operator provides:**
- Worker specs: vCPU count, RAM, (optionally) disk and network.
- Intended workload: number of active profiles, and either the count of enabled
  brokers per profile or the actual enabled-broker list.
- Optionally, the completion window (e.g. "all opt-outs must finish daily").

**Output:**
- Estimated capacity: how many profiles / total opt-out operations this worker
  can handle within the window.
- **Breakdown by opt-out type**, since they have wildly different costs:
  - **Email-method:** cheap — low RAM, fast, high throughput.
  - **Form-method:** expensive — one headless browser context per concurrent
    op, RAM-bound.
  - **Form-with-CAPTCHA:** most expensive — may block on an automated solver or
    a human handoff; effectively serializes or stalls a slot.
- A recommendation: "this worker supports ~N profiles at your mix" and, when
  over capacity, "you need M workers" (ties directly into item 7's fleet sizing).

**The critical dependency (do not ship this as authoritative without it):**
- The calculator is only as accurate as its **coefficients**: RAM per browser
  context, average seconds per form opt-out, email-send cost, CAPTCHA-handoff
  cost, failure/retry rate. These come from the item-7 benchmark, NOT from
  estimation.
- **Build it with coefficients as data, not hardcoded numbers.** The tool reads
  a small coefficients config (measured values) and does the arithmetic. Until
  benchmarks exist, it ships with clearly-labeled *placeholder* defaults and a
  visible warning that outputs are estimates pending real measurement. As real
  telemetry accumulates (item 7 workers reporting actual per-op timings), the
  coefficients — and thus the calculator — get more accurate over time.
- **Ideal end state:** the calculator's coefficients are auto-derived from the
  fleet's own historical run data, so it self-calibrates per deployment instead
  of relying on generic numbers. A deployment full of email brokers and one full
  of CAPTCHA-heavy brokers would correctly get very different answers.

**Why it's valuable:** it turns "it depends" into a concrete provisioning answer
an operator can act on, and it makes the email/form/CAPTCHA cost difference
visible — which nudges operators toward enabling cheaper, higher-value brokers.
It is a planning aid, not a guarantee; label it as such.

**STATUS: not started.** Blocked on the item-7 benchmark for real coefficients.

---

## Cross-cutting concerns (do not skip)

- **Security / trust:** items 1, 4, and 7 all introduce untrusted third-party
  code or config, executed against real sites with access to real PII. This is
  exactly what the existing plugin sandbox, permission gating, method
  allowlisting, and the read_pii+network block were built for. A real plugin
  (the bundled Gmail email-provider plugin, via the OAuth email-connect flow's
  auto-provisioning) has now actually run end-to-end in that sandbox — launch,
  seccomp, the network namespace, credential delivery, a genuine outbound API
  call — not just statically validated. That proved the mechanism works and
  surfaced (and fixed) real bugs the static-only validation had missed
  entirely: a seccomp rule that blocked thread creation for every plugin
  unconditionally, a memory-accounting bug that measured the wrong process's
  footprint, and a missing credential-delivery path with no working channel at
  all. One plugin type, run by the host's own auto-provisioning, is not the
  same trust bar as an admin knowingly installing an arbitrary third-party
  plugin from a future marketplace (item 8) — that step is still ungated by
  real-world running experience beyond this one case.
- **Testing reality:** the plugin system's static validation is no longer the
  only evidence it works — see above. What's still untested: a plugin OTHER
  than the bundled, first-party email providers; an admin-driven install from
  an upload (not host auto-provisioning) going through the full enable flow on
  a real, non-sandboxed-test host; and anything using capabilities the email
  providers don't exercise (storage, broker-read, the request lifecycle
  methods, scheduling). Each of those is a real gap, not a formality, before a
  marketplace (item 8) opens this to arbitrary third-party code.
- **Single-node vs. distributed (item 7):** everything in the current codebase
  assumes one process — in-process scheduler, in-process opt-out engine, SQLite.
  Scaling removal onto a worker fleet forces PostgreSQL, a job queue, and moving
  PII/browser work across a network boundary. Design the engine's job boundary
  early (produce-job / execute-job) so this is a deployment change later, not a
  rewrite. Don't build the fleet before load needs it; do accommodate it in the
  engine's shape from the start.
- **Maintenance model:** this architecture *relocates* the broker-drift burden
  (from core edits to add-on updates); it does not remove it. A community that
  maintains 400+ add-ons against constantly-changing sites is a hope, not a
  mechanism, until that community exists. The health/auto-disable system (item
  6) is what keeps the product usable in the meantime.

---

## Suggested build order (highest-leverage first)

1. ~~**Broker health reporting + auto-disable (item 6).**~~ **Done.**
2. ~~**Prove the sandbox runs one real plugin end-to-end.**~~ **Done** for the
   bundled email-provider plugins (see cross-cutting concerns); a third-party
   plugin is still untested.
3. **Interpretation engine + declarative broker description (items 2, 1).**
   Engine built and live; remaining work is retiring the legacy engine and
   packaging brokers as add-ons.
4. **Multi-form page interpreter (item 3).** Hook wired; needs richer page
   context and a real plugin.
5. **CAPTCHA layer — human-in-the-loop first, pluggable solver second (item 4).**
   The pluggable-solver hook now exists; the human path is the remaining gap and
   gates many brokers.
6. **Design the job boundary now, build the worker fleet when load demands it
   (item 7).** Write the engine (item 3) as produce-a-job / execute-a-job from
   the start so execution can move to workers later without a rewrite. Actually
   splitting into control plane + worker fleet + queue + PostgreSQL is done when
   you cross ~100–200 profiles, not before — but the *design* accommodation is
   free if done early and expensive if retrofitted.
7. **Git-backed add-on repo (item 8, phase 1).** Distribution, once there are
   add-ons worth distributing and a proven sandbox to run them in.
8. **Marketplace (item 8, phase 2).** Last; needs signing, review, and trust
   infrastructure that only matters once the ecosystem exists.

**Alongside, not in sequence:**
- **Capacity calculator (item 9)** can be built as a shell any time, but only
  becomes *accurate* after the item-7 benchmark produces real coefficients, and
  best after fleet telemetry lets it self-calibrate. Build the UI/math early if
  useful; gate any authoritative claims on real measurements.

---

### 10. Email-first opt-out via parent companies
Lean into email-method opt-outs, which sidestep the CAPTCHA + email-verification
walls that gate most form-method brokers. Brokers are largely a smaller set of
**parent companies** running many themed front-sites sharing one data pool and
often one opt-out inbox — so one strong email to the parent, enumerating all its
child sites, can clear a whole family of listings.

**STATUS: substantially built.**
- Parent-company data model with child-broker grouping (`ParentCompany`,
  `Broker.parent_company_id`). ✓
- Effectiveness tracking (does this parent honor email opt-outs?) with a derived
  honor_status. ✓
- Parent-company admin API + UI (create/edit, group/ungroup child brokers, see
  effectiveness). ✓
- Strong opt-out email template: full identifier list, age/range (never exact
  DOB), child-site enumeration, CCPA + general law citation, firm wording. ✓
- Send path (`send_parent_optout_email`) that composes + sends + records
  effectiveness. ✓
- Discovery→email link: cites the exact profile URL of the person's record on
  each child site where discovery found one. ✓

**Remaining:**
- Trigger the parent-send from a real action/scheduler hook (currently the
  capability exists but its only caller is the admin test-broker tool,
  `routers/test_broker.py`).
- Live SMTP test to a real parent company.
- Legal-wording review (the template's CCPA/rights language is a strong starting
  point, not vetted law — see docs/LEGISLATION.md law-librarian callout).

### 11. First-run setup wizard
On a fresh install the app detects zero accounts and shows a create-administrator
screen instead of a dead-end login (**built**). The next step is a full guided
wizard after the admin account is created.

**STATUS: built** (`routers/wizard.py`: database, email, branding, deployment,
skip, complete). The email step offers provider choices (OAuth-first, with
Proton-via-Bridge guidance). **Not built:** email-mode switching with the
old-inbox grace period (Prerequisite 2 below) — the wizard records the mode, but
nothing yet keeps monitoring the old inbox after a switch.

**Wizard steps (all strongly-prompted but SKIPPABLE):**
1. **Database** — detect/confirm SQLite (assumed same machine) vs PostgreSQL.
   If Postgres, collect connection details for a **dedicated/remote server**
   (host, port, db, user, password) — do NOT assume localhost.
2. **Email (the core step)** — operator chooses a deployment MODE:
   - **Shared inbox** — one account sends all opt-outs and receives confirmations.
   - **Per-user email** — each user grants access to their own email; opt-outs
     come from their own address, confirmations land in their own inbox.
   - An admin setting preserves the ability to split/change this later.
   - Sub-toggle **"Advanced: separate admin SMTP"** — OFF by default (one account
     handles both the tool's own admin/notification mail and opt-out send/receive);
     ON splits the admin SMTP from the opt-out account.
   - Skippable, but with a LOUD warning: opt-outs silently do nothing without it.
3. **Branding / logos** — optional, clearly cosmetic, separate/skippable.
4. **"You're ready" summary** — what's configured, what was skipped (with a
   warning for skipped email), and next actions (add members / import brokers).

**PREREQUISITE 1 — email TRANSPORT, must be designed BEFORE the email step:**
SMTP is NOT a safe default. Google Workspace and Microsoft 365 disable basic SMTP
auth by default (and admins often can't/won't re-enable it); consumer Gmail/Outlook
killed password SMTP in favor of app-passwords/OAuth; and local deployments have
no SMTP endpoint at all unless the operator runs their own mail server. Since
Workspace/365 are exactly the environments an institution is most likely to run,
"enter SMTP host/port/user/password" will fail for a large fraction — maybe most —
of real deployments. The email layer must therefore support multiple transports:
  1. **SMTP + IMAP** — for self-hosted mail servers and the shrinking set of
     providers that still allow it (SMTP sends; IMAP is needed to READ confirmations).
  2. **OAuth 2.0 to Google / Microsoft** — the "grant access to your email" flow.
     This is what actually works in Workspace/365/Gmail/Outlook, handles BOTH send
     and receive (Gmail API / MS Graph), and is precisely the mechanism for the
     per-user email model (a user authorizes their own account; opt-outs send from
     it). This is the modern default these providers push.
  3. **Dedicated purpose-built accounts** — the fallback: when neither works
     cleanly, the operator spins up separate accounts (one admin, one for removals)
     that then connect via whichever transport that account supports.
The wizard's email step must ASK which transport, not assume SMTP. Note: the
current code path is SMTP-only (`smtplib`); OAuth send/receive is new work.

**PRINCIPLE — OAuth-first, SMTP/app-password only as fallback (security):**
Prefer OAuth 2.0 wherever the provider supports it (Google, Microsoft, Yahoo);
fall back to app-password IMAP/SMTP ONLY where OAuth isn't available (Apple,
Proton-via-Bridge, self-hosted). OAuth is the more secure design and the default
the system should steer operators toward:
  - Stores a scoped, expiring, revocable TOKEN — not the account password. Far
    less damaging if the database is compromised.
  - Access is scoped to "send" / "read mail" only, not full-account.
  - Revocable instantly from the provider's security page without a password change.
  - Durable: Google/Microsoft are actively killing password SMTP, so OAuth
    integrations keep working while SMTP ones keep breaking.
The wizard should present OAuth as the recommended path and app-password/SMTP as
"use only if your provider or setup requires it," with a brief note on why.

**Provider ADAPTER interface (make providers pluggable, like CAPTCHA/form add-ons):**
Don't hardcode providers into the core — define an email-provider ADAPTER
interface (authenticate, send, list/read confirmations) and implement each
provider against it, plus expose it so community adapters can be added. This is
the same "core provides the seam, add-ons cover the variable stuff" pattern used
for CAPTCHA and form handling. Start with these five built-in adapters — but note
they do NOT share one mechanism, which is exactly why the adapter layer is needed:
  - **Gmail / Google Workspace** — OAuth 2.0 + Gmail API. Reference case.
  - **Outlook / Microsoft 365** — OAuth 2.0 + Microsoft Graph API. Different
    endpoints/scopes than Google.
  - **Yahoo** — OAuth 2.0 available, AND still allows app-passwords over IMAP/SMTP.
    The most forgiving; can go either way.
  - **Apple / iCloud Mail** — NO public email API and NO OAuth flow for MAILBOX
    access. IMPORTANT: "Sign in with Apple" is an IDENTITY provider (OIDC auth —
    "who is this user"), NOT email access; it cannot send or read a user's iCloud
    mail, and there is no scope for that. Do not chase it for the email adapter.
    The only supported path for iCloud Mail is IMAP/SMTP with an **app-specific
    password** (user generates it at appleid.apple.com; requires 2FA). This is the
    one provider where OAuth-first genuinely doesn't apply, because Apple offers no
    OAuth-for-mail at all. (Sign in with Apple could be worth adding LATER as a
    LOGIN option alongside the existing OIDC providers — a separate feature from
    email, and the only thing an Apple Developer membership would unlock here.)
    - **TO VERIFY (recent, evolving):** reports that Microsoft enabled Outlook to
      connect to iCloud Mail via OAuth. This is almost certainly a PRIVATE
      Apple↔Microsoft partnership for Microsoft's first-party Outlook client, NOT
      a public iCloud Mail OAuth API a third-party app could register against. The
      only question that matters for our adapter: can a THIRD-PARTY developer
      register an app and obtain iCloud Mail OAuth credentials with published
      send/read scopes? If yes (find Apple's public developer docs for it), Apple
      moves to the OAuth column. If all that exists is coverage of the Outlook
      integration with no registerable public API, it's a partnership and the
      app-password path above still stands. Verify against Apple's current
      developer documentation before assuming OAuth is available for iCloud.
  - **Proton Mail** — NO standard IMAP/SMTP or public API. Requires the operator to
    run **Proton Mail Bridge** locally, which exposes a local IMAP/SMTP endpoint;
    the adapter then connects to that. Hardest to support; document the Bridge
    requirement clearly. NOTE: Proton needs NO custom plugin — once Bridge is
    running it is just a local SMTP/IMAP server, so the built-in **generic SMTP**
    provider handles it. The wizard offers a "Proton (via Bridge)" choice that
    explains the prerequisite, links Proton's docs, and pre-fills the generic-SMTP
    fields with Bridge's local defaults (127.0.0.1:1025 / :1143). The wizard CANNOT
    install Bridge — it's OS-level software with an interactive Proton login + 2FA;
    the operator installs and runs it on the host (SSH / remote desktop / console)
    first. **STATUS: wizard guidance built.**

**General pattern — external mail bridges / local relays → generic SMTP:**
Proton is one instance of a broader pattern: any mail service reachable only
through a **local relay or bridge** (Proton Bridge, a corporate SMTP relay, a
local mail gateway, an on-prem appliance) is handled by pointing the **generic
SMTP provider** at that relay's host/port. The system never installs or manages
the relay — the operator stands it up on the host (or a reachable machine), then
configures generic SMTP against it. A recurring wrinkle to document: when
PrivacyShield runs in Docker, `127.0.0.1` is the CONTAINER, so a host-run relay
must be reached via the host address (e.g. `host.docker.internal`) and the relay
configured to accept that connection. This keeps the core simple (it only ever
speaks SMTP/IMAP) while supporting arbitrary bridged/relayed providers.

So underneath five provider names are ~three mechanisms: OAuth-API (Google, MS),
IMAP/SMTP-with-app-password (Yahoo, Apple, Proton-via-Bridge, self-hosted), and
generic SMTP+IMAP. The adapter interface unifies them behind one contract the
rest of the system (send opt-out, read confirmation) calls without caring which.

**PREREQUISITE 2 — must be designed BEFORE building the email step:**
Email-mode SWITCHING + a grace period. When a deployment changes email mode
(e.g. shared inbox → per-user), confirmations for already-in-flight requests will
still arrive at the OLD inbox for weeks (brokers take 30–60 days to respond). So
switching modes must NOT immediately stop monitoring the old inbox — the old
admin inbox keeps being checked for a configurable grace period (30/60 days) so
in-flight confirmations still get matched. This is a background monitoring
behavior with its own state (which inbox, until when, matched against which
pending requests), NOT a wizard step — but the wizard's email-mode choice creates
the state the switching logic later acts on, so the two must be designed together.
Decision: design email-mode-switching + grace period first, then build the wizard.

Keep the whole wizard skippable — power users configure via Settings directly.
The value is meeting a first-time operator where they are, so the tool is usable
without hunting through settings to find what's mandatory (SMTP especially).

---

### 12. School district authentication (parent portal SSO)
**Goal:** when deployed by a school district, parents log in with the account they
already use for the district's parent portal, while staff, faculty, and
administration log in with the district's Google or Microsoft accounts. This is
the school equivalent of the library-card (SIP2) login that already exists.

**What already works:**
- Staff/faculty/admin sign-in via the existing Google and Microsoft OIDC presets.
- The login page's two-tab layout (currently Staff/Patron for libraries) can
  become Staff/Parent for schools.
- A `parent` role already exists, which portal users map onto naturally.

**How parent portals are usually set up (verify per district; do not assume):**
Parent portals are typically part of the district's Student Information System
(e.g. PowerSchool, Infinite Campus, Skyward, Synergy/ParentVUE, Aeries). Whether
the portal can act as an identity provider for an outside app varies by vendor,
version, and district configuration. Some can via SAML or OIDC; some districts
put an identity platform in front (ClassLink, Clever, Okta, Microsoft Entra).
District IT has to register PrivacyShield as an application either way.

**Work needed:**
1. **SAML 2.0 support — see item 13.** Many district identity systems use SAML,
   so this item depends on the general SAML feature.
2. **Per-provider role mapping.** Parent-portal logins get the `parent` role.
   Staff logins get a configurable role, optionally mapped from IdP groups or
   attributes (e.g. district IT staff -> admin). A dedicated `staff` role may be
   needed; today there is only super_admin / parent / member.
3. **Side-by-side login options** (Parent login / Staff login), each tied to its
   own identity provider.
4. **Minimal claims only.** Request identity (name, email, stable user ID) and
   nothing else.

**Privacy and compliance cautions:**
- **FERPA:** SSO must never pull student records from the SIS. The login proves
  who the parent is and nothing more. Parents add family members themselves;
  never auto-import students from portal data.
- Districts will likely require a data-sharing / privacy agreement before
  deployment. Document exactly what data PrivacyShield receives and stores.
- Children's data removal is sensitive (see the minors provisions in
  docs/LEGISLATION.md); keep defaults conservative for school deployments.

**Open question:** which SIS and identity platforms to support first. Let the
first real district deployment decide, rather than building for vendors blind.

**STATUS: not started.**

---

### 13. SAML 2.0 single sign-on for staff (admin-configured)
**Goal:** an administrator can configure a SAML identity provider so staff log in
with their institution's existing credentials, alongside the existing OIDC,
LDAP, and SIP2 options.

**Why, given OIDC already exists:** Google Workspace and Microsoft 365 staff SSO
already works through the existing OIDC presets, and OIDC is the simpler, more
modern option there. SAML is still needed for:
- **Academic libraries** — campuses overwhelmingly use Shibboleth / InCommon
  (SAML-based).
- **On-premises Microsoft (ADFS)** and other older enterprise identity setups.
- **IT departments that mandate SAML** for all third-party apps.
- **School districts** whose identity systems speak SAML (item 12).

**Work needed:**
1. SAML service-provider support: SP metadata endpoint, IdP metadata upload/URL,
   assertion signature validation, ACS (assertion consumer) endpoint.
2. Admin UI to configure the IdP (metadata, entity ID, attribute mapping for
   email/name, optional group attribute).
3. Role mapping from IdP groups/attributes, with the same safety rules as OIDC:
   never auto-grant super_admin; respect the registration mode.
4. Tests with a local test IdP (e.g. a SimpleSAMLphp or Keycloak container).

**Security notes:** validate signatures strictly, reject unsigned assertions,
check audience/recipient/expiry, and protect against replay. SAML libraries are
a common source of vulnerabilities; use a maintained library, not hand-rolled
XML parsing.

**STATUS: built.** SAML 2.0 SP on pysaml2 7.5.4 + xmlsec1 (core/saml_sp.py,
routers/saml.py), admin panel on the Branding page, login button, and the shared
sign-in policy (core/sso_policy.py). Tested end to end against a real in-process
IdP with signed XML: sign-in works, and replayed, tampered, unsigned,
unsolicited, and impostor-signed responses are all rejected. Not yet run against
a live external IdP. Setup guide: docs/SSO.md.

**Prerequisite — OIDC sign-in hardening (found while scoping this item):**
- OIDC auto-provisioning currently skips the admin's registration rules
  (invite-only, admin-only, domain restrictions only apply to password sign-up).
- The Google preset has no hosted-domain restriction, so any Google account can
  sign in. (Microsoft is tied to the tenant ID, which is safer.)
- If an admin sets a provider's default role to super_admin, any account that
  can sign in becomes a super admin.
Fix: apply registration rules to SSO sign-ups, add a per-provider allowed-domain
restriction (Google `hd`), and never auto-provision super_admin via SSO.
**STATUS: fixed.** All external logins (OIDC, LDAP, SIP2, SAML) now go through
one policy. Fixing this also surfaced two more bugs, both fixed: (1) SSO login
never completed — the redirect used a hash URL the path-based router never
matched; (2) passwordless SSO users got a 401 on every request because
`can_login` meant "has a password" (fixed with `User.auth_source`).
**LDAP hardening (follow-up):** explicit LDAPS / StartTLS / None modes with
always-on certificate + hostname verification and a pasted CA certificate for
internal/self-signed CAs; blank-password "unauthenticated bind" bypass blocked;
connection timeouts; admin test button diagnoses the exact TLS problem. Also
fixed: LDAP login had never worked (`ldap.filter` was used without being
imported). Verified against a live OpenLDAP server with an internal CA.
**Certificate renewal safety (follow-up):** trust is anchored to the issuing CA
so auto-renewed certificates (Let's Encrypt 90-day, 47-day industry max by 2029)
keep working with no admin action; pasting a server certificate is refused
(it would break at the next renewal — demonstrated live); a daily scheduler job
(now running even when opt-out scheduling is off) checks the live certificate
and raises a dashboard alert when renewal appears to have failed.
**SIP2 over TLS + certificate monitor (follow-up, built):** SIP2 TLS verification
can no longer be turned off (pasted CA instead; legacy verify_cert=false is
ignored). Also fixed in SIP2: a login bypass (the ILS reply was searched for the
substrings "BLY"/"CQY", and the ILS echoes the barcode, so a barcode like
BLYCQY1 passed as a valid patron + PIN), field/message injection via "|" or CR
in the barcode/PIN, a NameError crash on any connection error, and card-number
enumeration via distinct error messages. A daily certificate monitor now covers
LDAP, SIP2, and the SAML IdP signing certificate (30-day warning; suppressed if a
rollover cert is already published), with dashboard alerts and one email to super
admins per milestone (30/14/7/3/1 days, expiry). Possible follow-up: automatic
refresh of SAML IdP metadata from its URL when the IdP rotates its certificate.

---

### 14. Built-in HTTPS with Let's Encrypt (automatic certificates)
**Goal:** PrivacyShield's own web interface gets a trusted HTTPS certificate
automatically, with no manual certificate handling — on Docker or on a native
(no-container) install.

**Why it matters:**
- Real deployments need HTTPS: staff and patron passwords cross the network at
  sign-in, and Google/Microsoft OAuth require HTTPS redirect URIs (only
  `localhost` is exempt). SAML assertions should also only be posted over HTTPS.
- Certificate lifetimes are shrinking (Let's Encrypt 90 days today; the industry
  maximum falls to 47 days by 2029), so manual renewal isn't realistic.
- Let's Encrypt stopped sending expiration-reminder emails in 2025, so a failed
  renewal is otherwise silent. The certificate monitor (built) should watch
  PrivacyShield's own certificate too.
- **Docker isn't the only enterprise deployment shape.** A lot of institutional
  IT — this is especially true of the libraries/school-districts/credit-unions
  this app targets — runs traditional VM or bare-metal infrastructure with no
  container runtime at all, sometimes by explicit policy. That's a genuinely
  different technical path (systemd + nginx + certbot; a Windows Service + IIS
  + win-acme), not just a smaller version of the Docker one, so it needed its
  own scripts and docs rather than being folded into the Docker path. Docker
  running on a VM, by contrast, is identical to Docker on bare metal from
  PrivacyShield's side — that split is the real fork, not deployment "size".

**Built — Docker path:** an optional Caddy front-end container
(`deploy/caddy/`), enabled via a docker-compose profile
(`COMPOSE_PROFILES=https`) so it costs nothing for deployments that don't want
it. `deploy/caddy/entrypoint.sh` generates the Caddyfile from environment
variables, with every value validated (including against multi-line Caddyfile
injection). `scripts/enable-https.sh` (Linux/macOS) and
`scripts/enable-https.ps1` (Windows, with a `.cmd` double-click launcher for
execution-policy-averse admins) are the guided way to turn it on —
interactive or fully flagged, with a DNS preflight check, `.env` backup, and a
matching `--disable`/`-Disable`. Modes: `letsencrypt`, `letsencrypt-staging`
(Let's Encrypt's test environment, to avoid rate limits while testing),
`acme` (any ACME server, e.g. an internal step-ca, with an optional internal
CA root), `internal` (Caddy's own private CA, LAN-only), and `custom`
(operator-supplied certificate files). HTTP→HTTPS redirect, HSTS, and security
headers are on by default. See `docs/HTTPS.md`.

**Built — native (no-container) path:** `deploy/native/install.sh` installs
PrivacyShield directly on a Debian/Ubuntu host — creates a dedicated system
user, lays the backend out as an importable `app` package (the exact same
transform the Docker image's build step does, since main.py's relative
imports require it), sets up a venv, installs Python deps + Playwright's
Firefox, compiles the plugin proto stubs, builds the frontend, and installs
`deploy/native/privacyshield-api.service` (a systemd unit). nginx serves the
built frontend and reverse-proxies `/api/` to the systemd-run process
(`deploy/native/nginx-privacyshield.conf.example`). `scripts/enable-https-native.sh`
is the native-path equivalent of `enable-https.sh` — same shape (validation,
DNS preflight, `.env` backup, `--disable`), but calls certbot's nginx plugin
directly instead of managing a container. Windows: no containers there either
— a Windows Service (via NSSM) runs the API, IIS serves the frontend and
reverse-proxies to it, and win-acme handles certificates; see
`docs/NATIVE_INSTALL.md` for the full walkthrough (this side is documentation-
led rather than script-led — automating IIS/NSSM registration reliably across
Windows Server versions isn't a good fit for a single script the way certbot's
CLI is).

**Deployment realities handled:**
- **Public server (HTTP-01):** `letsencrypt`/`letsencrypt-staging` modes —
  needs a public DNS name and ports 80+443 reachable from the internet; the
  enable script checks DNS resolution before proceeding. (Docker path: Caddy;
  native path: certbot.)
- **Internal ACME CA (e.g. step-ca):** `acme` mode with `ACME_CA` (+
  `ACME_CA_ROOT` if that CA isn't already trusted by browsers) — Docker path
  only; the native path relies on certbot/win-acme's own CA support instead.
- **LAN-only, no external CA at all:** `internal` mode (Caddy's own CA;
  browsers warn until that root is installed on client devices) — Docker path.
- **Setup wizard step ("deployment"):** asks how HTTPS is actually handled —
  **managed** (Docker + the built-in Caddy container; points the operator at
  `enable-https.sh`/`.ps1`), **native** (no containers; points at
  `enable-https-native.sh` or `docs/NATIVE_INSTALL.md` on Windows), or
  **external** (something else — a load balancer, IIS, nginx, another team's
  proxy — already terminates TLS in front of PrivacyShield either way; the
  wizard then stays out of the way entirely: no suggestion to run either HTTPS
  script, which would otherwise fight an existing proxy for ports 80/443, and
  the plain-HTTP nag is suppressed once that choice is recorded). The choice
  is stored and drives the wizard summary and the dashboard's warnings.
- **Windows, Docker path:** `scripts/enable-https.ps1` is a full port of the
  bash script (same options, same `.env` keys, same validation), plus
  `enable-https.cmd` for admins who'd rather double-click than fight execution
  policy. The containers themselves are unaffected either way — they're Linux
  containers under Docker Desktop or Docker Engine on Windows Server
  regardless of which host script drives them.
- **Windows, native path / IIS as the reverse proxy:** `docs/NATIVE_INSTALL.md`
  and `docs/HTTPS.md` cover IIS (ARR + URL Rewrite + a forwarded-proto server
  variable) with win-acme suggested for certificates — whether PrivacyShield
  itself runs as a native Windows Service or is just being fronted by IIS for
  other reasons.
- **Confirming setup worked, without giving the app host access:** the wizard
  can't run the script, `docker compose`, or `systemctl`/NSSM itself and show
  the output — that would mean giving the running app the host's Docker
  socket, its live `.env` file, or OS-level service control (none of which it
  has; `docker compose`/systemd only read `.env` at container/process startup,
  not afterward), a level of host access deliberately withheld given the
  plugin system's attack surface. Instead, `GET /api/cert-monitor/https-status`
  is a fast, side-effect-free, read-only TLS check (reusing the same code path
  the daily cert monitor already uses) that the dashboard calls automatically
  for the "managed" or "native" choice, with a **Check again** button — a
  real, live answer to "did this work?" without needing exec access to the
  host, on either deployment path.
- **Monitoring:** the daily certificate monitor also watches PrivacyShield's
  own HTTPS certificate — over the internal Docker network to the `caddy`
  container on the Docker path, or over `127.0.0.1` on the native path (set
  `HTTPS_CHECK_HOST=127.0.0.1` in `.env` — `enable-https-native.sh` does this
  for you) — the same way it already watches LDAP/SIP2/SAML. A failed
  automatic renewal raises a dashboard alert (and admin email) before the
  certificate actually expires. Skipped for `internal` mode (self-renewing)
  and for the external-proxy case (nothing here is PrivacyShield's to
  monitor).
- **`docker-compose.yml` fixes made along the way (Docker path):**
  `FRONTEND_URL` is now actually passed to the `api` container (previously
  commented out — SSO redirects and the SAML public base URL were silently
  falling back to `http://localhost` even when the operator set it); the API
  port is bound to `127.0.0.1` by default instead of all interfaces (avoids
  exposing a plain-HTTP login endpoint on the LAN); `WEB_BIND`/`WEB_PORT` let
  Caddy take over 80/443 without a second web server fighting it for the
  ports; nginx passes through `X-Forwarded-Proto`/`X-Forwarded-For` from the
  front door.

**Tested:** `deploy/tests/acme_e2e.sh` runs real ACME issuance and an
automatic renewal end-to-end against Caddy + Pebble (Let's Encrypt's own test
ACME server) with short-lived certificates — verified HTTPS, HTTP→HTTPS
redirect, security headers, and a real renewal mid-test while the site keeps
serving. The entrypoint's input validation was tested under both bash and
BusyBox `sh` (the actual shell in the `caddy:alpine` image) against injection
attempts, including multi-line values that a naive single-line check would
miss. `scripts/enable-https.sh` was tested for enable/validate/disable and for
never blocking on a prompt when run non-interactively.

`deploy/native/install.sh` was actually run end-to-end (not just read-checked)
on a real Debian/Ubuntu host: real system-user creation, a real `apt-get
install`, a real venv with the full `pip install` (including the optional
SQLCipher encryption package), the app-package layout transform, proto stub
compilation, and the frontend build all completed successfully and were
verified by directly importing `app.main` with the installed venv's Python
(186 routes registered) and then actually starting `uvicorn app.main:app`
against it — `/api/health` returned `200 {"status":"ok"}` from a real running
process, with migrations applying against a real SQLite database. Two real
bugs were caught and fixed this way: an unguarded `playwright install firefox`
that would abort the entire install (skipping the frontend build and systemd
setup) if that download failed for any reason — including a blocked CDN behind
a corporate firewall/proxy, a routine occurrence at exactly these target
institutions — now degrades to a warning; and a missing `mkdir -p` before the
frontend `rsync` that failed outright. `systemctl daemon-reload` itself
couldn't be exercised in the sandbox used to build this (no systemd as PID 1
there) — a real VM/bare-metal Linux server has one; that step is a thin,
well-trodden wrapper (copy unit file, `daemon-reload`, `enable --now`) rather
than novel logic, but it's still worth a real run on Windows and on a genuine
systemd host before a production cutover. `scripts/enable-https-native.sh`
had its validation functions, `--help`, the certbot-presence guard, and the
`--disable` path exercised directly; the actual `certbot` issuance call
wasn't (needs a real reachable domain + certbot installed).
`scripts/enable-https.ps1` mirrors the bash script's logic line-for-line and
was structurally reviewed (brace/paren/quote balance, cmdlet syntax) since
this environment has no PowerShell runtime to execute it against — also worth
a real run on Windows before relying on it for a production cutover.

**One-line installer:** `install.sh` at the repo root is a `curl | sh`-style
entry point (`curl -fsSL .../install.sh | sh`), written in POSIX `sh` (not
bash — same reason installers like get.docker.com ship that way: it has to
run correctly under whatever `/bin/sh` actually is, dash on Debian/Ubuntu
included). It clones the repo (or updates an existing checkout in place — a
directory that exists but isn't a git checkout is left alone, not clobbered),
detects Docker vs. a native-installable Debian/Ubuntu-as-root situation, and
hands off to that path's existing script rather than duplicating its logic —
`docker compose up -d` (generating `.env` with a fresh `SECRET_KEY` first, if
one doesn't already exist) or `deploy/native/install.sh`. An existing `.env`
is never touched on a re-run. Actually exercised end-to-end against a local
git mirror (not just read-checked): a forced `--docker` run with no Docker
installed fails cleanly before touching anything; the real fake-docker path
was run through a stub `docker` binary and produced a correct `.env` (a real
64-hex-char generated key) and the expected `docker compose up -d` call;
re-running against the same directory correctly took the update path instead
of re-cloning and left `.env` (including a hand-added custom variable)
untouched; the "directory exists but isn't a git checkout" guard, the
"already inside a checkout, no `--dir` needed" shortcut, the native path's
handoff into a fresh clone, and genuinely piping the script through `sh -s --`
(rather than running it as a file, which is what a real `curl | sh` user
experiences — `$0` isn't a real path in that mode) were all exercised
directly too.

**Follow-up, not built:** a bundled DNS-01 challenge provider (e.g. a
Cloudflare API plugin) for hosts that can't open ports 80/443 to the internet
at all and don't have their own internal ACME CA to point `acme` mode at (or,
on the native path, certbot's own DNS plugins for the same situation).

**STATUS: built.**

---

### 15. Memory hygiene: clear secrets promptly, hold minimal PII in memory
**Goal:** decrypted secrets (OAuth tokens, SMTP/IMAP passwords, database
encryption keys, session tokens) and in-flight member PII spend as little time
in process memory as possible, and nothing holds more of either than the
immediate operation actually needs — so a core dump, an attached debugger, a
swap file, or an unrelated bug that leaks process memory exposes as little as
achievable, not a full settings blob or a whole batch of family members' data.

**Why now:** this session's plugin credential work is a concrete example of
the RIGHT shape — `GetEmailCredentials` hands a plugin only the current access
token for the one send in progress, never the refresh token or OAuth client
secret, and the plugin never has a reason to hold it past that one call. The
rest of the app doesn't consistently follow that same discipline yet, and the
memory-accounting bug this session found and fixed (a plugin's declared
memory limit was silently measuring the wrong process's footprint) is a
reminder that assumptions about what's actually happening in memory are worth
verifying, not just stating.

**Be honest about what Python actually allows here** — this is not a
"just add secure_zero_memory()" fix:
- Python strings are immutable. Once a password or token exists as a `str`
  (which it will — decryption, JSON parsing, and most libraries hand back
  `str`, not `bytearray`), there is no way to overwrite those bytes in place.
  `del` removes a *reference*; it doesn't scrub the memory the string
  occupied, and CPython may keep the freed block ready for reuse (not
  zeroed) or intern short strings, extending their lifetime unpredictably.
- CPython's primary GC mechanism is reference counting, so dropping the last
  reference to an object usually does free it promptly — but "usually" is
  doing real work in that sentence: a lingering reference in a closure, a
  cache, a log line, or an exception traceback (tracebacks hold local
  variables, including any secret that was in scope when the exception was
  raised) all keep the real memory alive far longer than the code appears to
  suggest.
- True secure erasure (mlock to prevent swapping, explicit overwrite of the
  actual pages) needs either C-level access (ctypes) or accepting the
  limits of a managed-memory language. Treat this as risk *reduction*
  (smaller window, fewer copies, fewer places to check) rather than a
  cryptographic guarantee — and say so plainly in whatever ships, rather than
  implying a guarantee the language can't actually make.

**Concrete, achievable work:**
- **Audit for lingering secrets:** find every place a decrypted password,
  token, or key ends up in a variable with a longer lifetime than the single
  operation using it — module-level caches, objects attached to a long-lived
  session/connection, or a settings dict held onto across multiple requests
  instead of reloaded and dropped. `core/settings_store.py`'s
  `decrypt_password`, `core/oauth_engine.py`'s token handling, and the SMTP/
  IMAP paths in `core/email_send.py` are the highest-value places to start,
  since those are the ones actually shipping today.
- **Never let secrets reach a log or an exception message.** A few call
  sites already truncate/avoid this; make it a review checklist item rather
  than something caught ad hoc — an f-string built from an exception that
  happened to be raised inside a block holding a password in scope is an
  easy, easy-to-miss way to put a secret in a log file.
- **Minimize PII batch size in memory:** the opt-out engine and any reporting/
  export code should pull only the member records the current operation needs
  and let them go out of scope promptly, rather than loading a broad query
  result and holding it for the duration of a long-running job.
- **RLIMIT_CORE=0 already applies to plugin subprocesses** (prevents a crash
  from writing a core dump full of whatever was in that process's memory —
  see `plugins/sandbox.py`). The main API process doesn't have this today;
  consider whether it should, weighed against losing core dumps for real
  debugging.
- **Extend the "hand over only what's needed, only when it's needed" pattern**
  from `GetEmailCredentials` to other places holding secrets — e.g., the SAML
  signing key, LDAP bind credentials, and SIP2 credentials, checking each for
  whether the decrypted value outlives the single connection/operation that
  needed it.

**STATUS: not started — added to the roadmap based on a real gap this session's
work surfaced, not yet scoped into concrete tasks.**

---

### 16. Operational visibility: version in logs, in-app log viewer, adjustable verbosity
**Goal:** an admin can always tell exactly what code is running, can pull up
the logs that actually matter without shelling into the host, and can turn
verbosity up while debugging a problem and back down to security-relevant-only
once things are stable — all from the app itself.

**Why this matters, concretely:** this exact session is the case study. Every
fix required asking the operator to run `docker compose logs api` and paste
output back, iterating blind between messages on whether a rebuild had
actually picked up a given change, and no way to confirm from inside the app
which commit was actually running. An in-app view of this would have
shortened several multi-turn back-and-forths to one.

**Part A — version reporting (BUILT this session, small enough to just do):**
`backend/VERSION` (canonical; the Docker build context is `backend/` only, so
a repo-root file wouldn't be visible to the image) is logged as the very
first thing at API startup, before anything that could fail — `PrivacyShield
0.1.0 (commit a1b2c3d) starting up` — and served from `GET /api/health`
(`{"status": "ok", "version": "0.1.0", "commit": "a1b2c3d"}`). The commit
comes from a `GIT_COMMIT` build-arg (docker-compose.yml passes it through;
`install.sh` and `deploy/native/install.sh` capture it automatically from the
checkout being built/updated) with a live `git rev-parse` as a same-process
fallback for a native/dev run, and "unknown" — never a crash — if neither
source has an answer (e.g. a downloaded zip release with no git history).
Covered by a dedicated test (`version.reports_file_env_and_fallback_correctly`)
exercising all three paths plus the missing-file case.

**Part B — in-app log viewer (not started):** select a system (API, database,
scheduler/background jobs, each plugin process, and anything else that logs
separately) and see recent entries without leaving the admin UI. Real design
questions, not yet resolved:
- **Where do these logs actually live to be read back?** Today they go to
  stdout/stderr (`docker compose logs` / `journalctl` for the native path) —
  ephemeral, rotated by the container runtime, not queryable by the app
  itself. Reading them back means either the app writing its own log files
  to a persistent volume/directory it can also read from (simplest, but
  duplicates what Docker/systemd already capture and needs its own rotation
  policy so it doesn't grow unbounded), or querying `docker logs`/`journalctl`
  from inside the container (needs the API container to reach the Docker
  socket or the host's journal, which is exactly the kind of host-level
  access this app has deliberately avoided giving the API process elsewhere
  in this codebase — see item 15 and the plugin sandbox's own
  least-privilege posture — so this would need a clearly-scoped, narrow
  exception if it's the chosen path, not a blanket grant).
- **Multi-source in one place:** the API process, the plugin manager
  (separate log lines already prefixed `[plugin:id]` — see `broker.py`'s
  `log_message`), and — for Docker deployments — the `web`/`caddy` containers
  are all genuinely separate log streams today. "Select what I want to see"
  needs a real per-source model, not just a text filter over one merged
  stream.
- **Access control:** logs can contain operationally-sensitive detail (IPs,
  internal errors, stack traces) even with PII/secrets kept out of them (item
  15) — this should be a super-admin-only view, and itself worth a look
  before shipping given the same "don't hand out more than necessary" theme
  as this session's credential-delivery work.

**Part C — adjustable log verbosity (not started):** a setting (likely
Settings → somewhere near the plugin system toggle) to switch between at
least two presets — verbose/debug (everything, for active troubleshooting)
and a quieter default (security-relevant events: auth failures, permission
denials, plugin crashes/violations, cert/HTTPS problems — not routine
per-request info logs). Needs:
- Deciding whether this is a Python `logging` level change applied at
  runtime (achievable without a restart — `logging.getLogger(...).setLevel(...)`
  — but only affects log CALLS already written with the right level, so this
  also means auditing existing log statements for whether they're at a level
  that makes the "security messages only" preset actually mean what it says,
  not just "everything still comes through because it was all logged at
  INFO"), or an env-var-set level requiring a restart (simpler, less capable).
- Whether plugin subprocesses (separate processes, separate Python logging
  configuration) pick up the same setting or need their own — they don't
  automatically inherit the host process's logging configuration today.

**STATUS: Part A built and tested this session. Parts B and C scoped above,
not started — real design decisions (log storage/access model, per-source
filtering, verbosity-level audit) that deserve their own pass rather than a
rushed implementation.**

---

## Explicitly deferred / open questions

- Declarative-vs-code boundary for broker add-ons (item 1).
- Add-on signing / provenance model for safe automated install (item 8).
- Job-queue technology choice and how PII crosses the control-plane/worker
  boundary safely (item 7).
- Whether human-in-the-loop CAPTCHA solving is viable at institutional scale, or
  only for small deployments (item 4).
- Economic/ethical stance on third-party CAPTCHA-solving services (item 4).
- Which SIS / identity platforms to support first for school districts (item 12).
