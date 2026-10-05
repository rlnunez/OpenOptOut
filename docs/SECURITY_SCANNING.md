# Automated security scanning

OpenOptOut runs free, open-source security scanners on every change. Their results
are collected in one place: the repository's **Security → Code scanning** tab.

This guide covers:

- [What runs, and when](#what-runs-and-when)
- [One-time setup (about 10 minutes)](#one-time-setup-about-10-minutes)
- [Reading the results](#reading-the-results)
- [Handling findings](#handling-findings)
- [Running the scanners on your own computer](#running-the-scanners-on-your-own-computer)
- [Maintenance](#maintenance)

---

## What runs, and when

| Tool | What it looks for | When |
|---|---|---|
| **CodeQL** | Injection, path traversal, unsafe deserialization, auth mistakes, and more, in Python and TypeScript | Every push and pull request (GitHub's CodeQL *default setup*, configured in Settings — not in `security.yml`) |
| **Semgrep** | Known insecure patterns (OWASP Top 10, FastAPI, React, Dockerfiles), **plus OpenOptOut's own rules** in `.semgrep/` | Every push and pull request |
| **Bandit** | Python-specific problems: weak crypto, shell commands, temp files | Every push and pull request |
| **Gitleaks** | Passwords, API keys and tokens anywhere in the **entire git history** | Every push and pull request |
| **TruffleHog** | The same, but it checks whether each secret is **still live**. A live one **fails the run**. | Every push and pull request |
| **OSV-Scanner** | Python and npm packages with known vulnerabilities, including indirect dependencies | Every push and pull request |
| **Trivy (config)** | Insecure Dockerfile and deployment settings | Every push and pull request |
| **Hadolint** | Dockerfile best practices | Every push and pull request |
| **ShellCheck** | Bugs in `install.sh`, `scripts/` and `deploy/`, which people pipe straight into a shell | Every push and pull request |
| **zizmor + actionlint** | Security holes and mistakes in these GitHub workflows themselves | Every push and pull request |
| **Trivy (images)** | Known vulnerabilities in the built Docker images | Push to `main`, weekly, on demand |
| **Schemathesis** | Sends thousands of generated requests to every API endpoint. Finds crashes, **endpoints that skip the login check**, and data that's still reachable after it was deleted. | Push to `main`, weekly, on demand |
| **OWASP ZAP** | Attacks the running API like a web pentester: missing security headers, injection, information leaks | Push to `main`, weekly, on demand |
| **ClusterFuzzLite + Atheris** (fuzzing) | Feeds millions of random and malformed inputs into the code that handles untrusted data: broker specs, plugin manifests, the plugin code inspectors, signed job envelopes, the log sanitizer, and the Identity Vault combination builder. Finds crashes, hangs and broken security checks. | Pull requests touching `backend/` (5 min), weekly (30 min), on demand |
| **OpenSSF Scorecard** | Grades the project's security habits (branch protection, pinned dependencies, code review) | Push to `main`, weekly |
| **Dependabot** | Opens pull requests to update outdated or vulnerable dependencies | Weekly, plus immediately for security fixes |

**Report-only by default.** Findings appear in the Security tab and as comments
on pull requests. They do not block merging. The one exception is a
**verified, live credential**: that fails the run, because it needs action right away.

### OpenOptOut's own Semgrep rules (`.semgrep/openoptout.yml`)

| Rule | Why it matters here |
|---|---|
| `pii-in-log-call`, `pii-variable-in-log-call`, `identity-vault-value-in-log` | Names, emails, phones and addresses must never reach log files, which are stored unencrypted and shared in bug reports |
| `hardcoded-fallback-secret` | `os.getenv("SECRET_KEY", "change-me…")` means a forgotten setting quietly uses a value anyone can read in this public repo |
| `cors-wildcard-with-credentials` | `allow_origins=["*"]` with credentials lets any website make logged-in requests if a cookie is present |
| `queue-message-signature-not-verified` | Unsigned Redis queue messages would let an attacker inject jobs for workers |
| `httpx-tls-verification-disabled`, `jwt-unverified-claims` | Turning off certificate or signature checks |
| `exception-text-returned-to-client` | Raw error text can leak paths, SQL or personal data to the browser |
| `non-constant-time-secret-compare` | Comparing secrets with `==` can leak them through response timing |

### Why the dynamic scan is safe

The API fuzzers log in as an administrator and send random input to *every*
endpoint, including ones that start opt-outs, send email or fetch URLs. So during
the scan, the API runs on an **internal-only Docker network with no internet
access** (`.github/security/docker-compose.dast.yml`). It cannot contact real data
brokers, mail servers or anything else. It uses a throwaway database with a
random admin account, and everything is deleted when the job ends.

---

## One-time setup (about 10 minutes)

### Step 1 — Add the files to the repository

Copy these into the repo (or merge the pull request that adds them):

```
.github/workflows/security.yml          main scanning workflow
.github/workflows/scorecard.yml         OpenSSF Scorecard (must be its own file)
.github/dependabot.yml                  weekly dependency + action updates
.github/security/                       helper scripts and the isolated DAST setup
.semgrep/openoptout.yml                 project-specific rules
.gitleaksignore                         reviewed secret-scanner false positives
SECURITY.md                             how to report a vulnerability privately
docs/SECURITY_SCANNING.md               this guide
```

### Step 2 — Turn on GitHub's built-in security features

These are free for public repositories. Go to **Settings → Advanced Security**
(on some accounts it's called **Code security**) and turn on:

| Setting | Why |
|---|---|
| **Dependency graph** | Needed by Dependabot |
| **Dependabot alerts** | Emails you when a dependency has a known vulnerability |
| **Dependabot security updates** | Automatically opens a pull request with the fix |
| **Grouped security updates** | One pull request instead of many |
| **Secret Protection** (secret scanning) | GitHub's own scanner for 200+ token formats |
| **Push protection** | Blocks a push that contains a secret *before* it reaches GitHub |
| **Private vulnerability reporting** | Gives researchers the private "Report a vulnerability" button that `SECURITY.md` points to |

> **CodeQL:** under **Code scanning → CodeQL analysis**, keep **Default setup**
> turned on (it already is for this repo). `security.yml` deliberately does
> *not* run CodeQL, so the two never conflict. If you ever switch CodeQL to
> "Advanced setup", add a CodeQL job to `security.yml` at the same time.

### Step 3 — Check that Actions is allowed to run

Go to **Settings → Actions → General**:

- **Actions permissions:** "Allow all actions and reusable workflows" works.
  For a tighter setting, choose "Allow *rlnunez*, and select non-*rlnunez*,
  actions and reusable workflows". Then tick *Allow actions created by GitHub*
  and add this list:
  ```
  aquasecurity/trivy-action@*, hadolint/hadolint-action@*, ossf/scorecard-action@*
  ```
- **Workflow permissions:** leave at **Read repository contents** (the default).
  Each job asks for exactly the extra permission it needs.

### Step 4 — Run it for the first time

1. Open the **Actions** tab.
2. Choose **Security scans** in the left sidebar.
3. Click **Run workflow** → **Run workflow**.
4. Do the same for **Scorecard**.

The fast scans take about 5 minutes. The dynamic job (image build, fuzzing, ZAP)
takes about 15–25 minutes.

### Step 5 (optional, later) — Make serious new findings block merges

After you've worked through the first batch of findings, you can make **new**
serious findings stop a pull request:

**Settings → Rules → Rulesets → New branch ruleset** → target `main` →
**Require code scanning results** → add **CodeQL**, set *Security alerts* to
**High or higher**. Add other tools (e.g. `semgrep`, `osv-scanner`) the same way
if you want.

### Step 6 (optional) — Add the Scorecard badge to the README

```markdown
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/rlnunez/OpenOptOut/badge)](https://scorecard.dev/viewer/?uri=github.com/rlnunez/OpenOptOut)
```

---

## Reading the results

There are three places to look:

1. **Security → Code scanning.** Every finding from every tool, with the
   affected line of code. Use the **Tool** filter to look at one scanner at a
   time. Start with **Severity: Critical / High / Error**.
2. **Actions → a run → Summary.** Each job writes a short table (counts by
   severity, most common rule). This is the quickest way to see "how bad is it".
3. **Actions → a run → Artifacts → `dast-reports`.** The API fuzzing and ZAP
   results:
   - `zap-report.html`: open in a browser, sorted by risk
   - `schemathesis.txt`: every failing request, with a `curl` command to reproduce it
   - `openapi.json`: the API schema that was tested
   - `api-container.log`: server logs from the scan (look here for stack traces)

**Where to start:** anything in this order —
1. TruffleHog failure (a live credential) — rotate that credential now.
2. Schemathesis `ignored_auth`: an endpoint that answers without a valid login.
3. CodeQL / Semgrep **error** severity, especially the `pii-*` rules.
4. OSV-Scanner / Trivy **critical/high** with a fixed version available.
5. Everything else.

---

## Handling findings

For each finding, do one of three things:

| Situation | What to do |
|---|---|
| **Real problem** | Fix it. The alert closes itself on the next scan of `main`. |
| **Not a real problem** (false positive) | In the Security tab, open the alert → **Dismiss alert** → *False positive*, and write why. |
| **Real, but acceptable** | **Dismiss alert** → *Won't fix*, with the reason. |

You can also silence a finding in the code, **with a comment explaining why**:

| Tool | How |
|---|---|
| Semgrep | `# nosemgrep: <rule-id>` at the end of the line |
| Bandit | `# nosec B603` at the end of the line |
| Gitleaks | add the finding's fingerprint to `.gitleaksignore` |
| Trivy | add the ID (e.g. `CVE-2024-1234`) to a `.trivyignore` file at the repo root |
| Hadolint | `# hadolint ignore=DL3008` on the line above |
| ShellCheck | `# shellcheck disable=SC2086` on the line above |

---

## Running the scanners on your own computer

It's faster to catch problems before pushing. From the repository root:

```bash
pip install semgrep bandit zizmor

# Project rules + public rules
semgrep scan --config .semgrep/ --config p/python --config p/owasp-top-ten backend/

# Python security checks
bandit -r backend -x backend/tests -s B101,B110,B112

# Workflow security
zizmor .github/workflows/
```

Gitleaks, OSV-Scanner, Trivy and ShellCheck are single downloads (or
`brew install gitleaks osv-scanner trivy shellcheck` on a Mac):

```bash
gitleaks git .                         # secrets in the full history
osv-scanner scan source -r .           # vulnerable dependencies
trivy config .                         # Dockerfile / deployment settings
shellcheck install.sh scripts/*.sh     # shell scripts
```

To stop secrets from ever being committed, you can add a
[pre-commit hook for Gitleaks](https://github.com/gitleaks/gitleaks#pre-commit).

---

## Fuzzing

The fuzz targets live in `fuzz/`, one file per area:

| Target | Untrusted input | What counts as a bug |
|---|---|---|
| `fuzz_broker_spec.py` | `spec.json` in broker add-ons and imports | Any exception escaping `validate_broker_spec_file()`; anything but `CompileError` from `compile_job()` |
| `fuzz_plugin_manifest.py` | `manifest.json` in uploaded plugins | Any exception escaping plugin scanning (`layout._inspect`) |
| `fuzz_plugin_code_inspector.py` | Every file in an uploaded plugin | Either inspector crashing instead of reporting a finding |
| `fuzz_job_envelope.py` | Job/result messages in Redis | A **changed or forged envelope being accepted**, or garbage raising anything but `EnvelopeError` |
| `fuzz_log_sanitizer.py` | Every log line | A crash, a hang (regex backtracking), or a **bearer token surviving** sanitizing |
| `fuzz_identity_combos.py` | Identity Vault values typed by users | Any exception while building search/opt-out combinations |

**When it finds something:** the PR check fails, and the crash appears in
**Security → Code scanning** (tool: ClusterFuzzLite). The run's artifacts
include the exact input that triggered it.

**Reproduce a crash or fuzz locally:**

```bash
pip install atheris
bash fuzz/build_pkgroot.sh                      # makes the backend importable as `app`
cd fuzz
python fuzz_broker_spec.py -max_total_time=120  # fuzz for 2 minutes
python fuzz_broker_spec.py crash-<id>           # re-run one saved crashing input
```

**Adding a target:** copy an existing `fuzz/fuzz_*.py`. Import the code under
test inside `with atheris.instrument_imports():`, and decide which exceptions
are acceptable "rejections". Anything else is a bug. The workflow picks up new
`fuzz_*.py` files automatically.

**Corpus:** the interesting inputs found so far are saved as workflow
artifacts and reused by the next run, so fuzzing goes deeper over time.

## Maintenance

- **Dependabot** opens a pull request each Monday to update the pinned GitHub
  Actions and the Python/npm/Docker dependencies. Deliberately pinned packages
  (bcrypt, cryptography/pyopenssl/pysaml2, playwright) are excluded in
  `.github/dependabot.yml`, with the reason next to each. Remove an exclusion
  when its reason goes away.
- **Tool versions** (Semgrep, Gitleaks, OSV-Scanner, etc.) are set in the `env:`
  block at the top of `security.yml`. When you bump a downloaded binary, also
  update its `*_SHA256` value from that release's checksums file.
- **Never** use Trivy **v0.69.4, v0.69.5 or v0.69.6**. Those releases were
  compromised in March 2026
  ([GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)).
  This is why every action is pinned to a full commit SHA instead of a tag.
- **Fuzzing depth:** "Run workflow" has a *Schemathesis examples per API
  operation* box. The default is 50; 200+ gives a much deeper (slower) run.

### What automated scanning does *not* cover

Scanners are good at known patterns. They are weak at design-level questions:

- whether a plugin can escape the bubblewrap/seccomp sandbox
- whether the gRPC capability broker can be tricked into granting extra access
- whether Fernet/SQLCipher keys are handled correctly end to end
- whether one family or library branch can ever see another's data

Those still need a human reviewer. A clean scan report is useful evidence when
applying for a free professional audit (for example, the OTF Security Lab).
