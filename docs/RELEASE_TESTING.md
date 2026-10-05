# Automatic release testing

Every time you publish a **release or pre-release** on GitHub, the
**Release test** workflow (`.github/workflows/release-test.yml`) installs it on
a brand-new machine the same way a user would. It then goes through first-run
setup and reports every error it finds. Nothing to install or run on your side.

## What it does

**1. Fresh install** (about 15–20 minutes)

| Step | What's checked |
|---|---|
| Install | Runs the real one-line installer: `install.sh --docker --ref <your tag>` |
| Start-up | Every container starts and stays up; the API answers `/api/health` |
| Browser walk-through | A real Chrome browser opens the site and runs first-time setup like a new user. It checks for the **Create administrator account** screen, fills in the form, clicks through every **setup wizard** step to the dashboard, then opens **all 23 pages**. It records JavaScript crashes, blank pages, error messages on screen, failed requests and server errors, and **takes a screenshot of every screen**. |
| API checks | The version the app reports matches the release tag. You stay logged in, the wizard is marked complete, and data saved to the **Identity Vault** (encrypted) reads back unchanged. **Every GET endpoint** (about 85) answers without a server error. |
| Built-in diagnostics | `tests.run_tests`, `plugins.preflight_sandbox` and `plugins.smoke_test` inside the api container |
| Logs | Every `ERROR`/`CRITICAL` line, Python traceback and nginx error in the container logs, grouped and counted |

**2. Upgrade test** (about 20–25 minutes, runs at the same time as the fresh install)

1. Installs the **previous full release**, sets it up, and saves Identity Vault data.
2. Upgrades to the new release using the README's steps: `git checkout <tag>`,
   `docker compose down`, `docker compose build`, `docker compose up -d`.
3. Checks that the old login still works, setup is still complete, and the saved
   data is still there and readable. This catches migration and encryption-key
   problems. Then it runs the GET-endpoint check and the log scan again.

**3. Report**

- The run's **Summary** page shows a ✅/❌ table for every check, followed by the details.
- **If anything failed**, it opens a GitHub issue titled
  **"Release test failed: \<tag\>"** (label `release-test`) with the same report.
  GitHub notifies you of the new issue by email.
- If you fix something and re-run the test for that tag, the result is added to
  that issue. If the re-run passes, the issue is **closed automatically**.

All test data is fake (`@example.com` addresses, `555-01xx` numbers). The
scheduler is off on a fresh install, so the test never sends opt-out requests.

## Where to find the results

- **Actions → Release test → the run → Summary**: the full report.
- **Artifacts** at the bottom of the run:
  - `release-test-fresh-<tag>`: `screenshots/` (every screen, numbered in
    order), `logs/` (installer output, container logs, test-suite output), and
    the raw results as JSON.
  - `release-test-upgrade-<tag>`: the same for the upgrade test.
- **Issues** filtered by the label `release-test`.

## Running it by hand

**Actions → Release test → Run workflow**. You can set:

- **Release tag to test**: leave blank for the newest release (including pre-releases).
- **Upgrade test: start from this tag**: leave blank for the previous full
  release, or type `none` to skip the upgrade test.

## Things to know

- **The release must be *published*.** Saving a draft doesn't start the test;
  publishing it (or publishing a pre-release) does.
- **Releases created by a GitHub Action with the default `GITHUB_TOKEN` do not
  start other workflows** (a GitHub safety rule). Releases you publish yourself
  on github.com, or with `gh release create` from your own computer, are fine. If
  you later automate releases in a workflow, have it use a personal access token
  or a GitHub App token, or run this test from it directly.
- **Version check:** the test expects `/api/health` to report the same version
  as the tag (e.g. tag `0.7.19` → `VERSION` file `0.7.19`; a leading `v` is
  ignored). For a pre-release tagged `0.8.0-beta.1`, set `VERSION` to
  `0.8.0-beta.1` too, or the check fails on purpose.
- **The test scripts come from `main`**, not from the release being tested
  (`.github/release-test/`). So improving a check improves it for every release,
  including when you re-test an old one.
- **Cost:** free for a public repository (GitHub Actions minutes are unlimited
  for public repos).

## Running the checks on your own machine

With OpenOptOut running locally via Docker on port 80:

```bash
pip install playwright && python -m playwright install --with-deps chromium

# Browser walk-through — only works on a FRESH install (no admin yet)
python3 .github/release-test/ui_check.py --base-url http://localhost \
  --out-dir ./release-report --creds-file ./release-report/creds.json

# API checks (logs in with the account the browser check created)
python3 .github/release-test/setup_check.py --base-url http://localhost \
  --creds-file ./release-report/creds.json --out-dir ./release-report

# Errors in the container logs
docker compose logs --no-color > containers.log
python3 .github/release-test/scan_logs.py "local" containers.log ./release-report/logs.md
```

Open `release-report/ui-report.md` and `release-report/screenshots/` for the results.
