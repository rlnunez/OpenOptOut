# Automatic release testing

Publishing a release or pre-release triggers the **Release test** workflow (`.github/workflows/release-test.yml`), verifying installation, setup, API health, and upgrade migrations in fresh runners.

## Test stages

### 1. Fresh install (~15–20 min)

| Step | Scope |
|---|---|
| Install | Runs the real installer: `install.sh --docker --ref <tag>` |
| Start-up | Verifies container availability and `/api/health` response |
| Browser walk-through | Playwright Chrome executes first-run wizard, creates admin account, traverses all pages, verifies lack of console/render errors, and captures screenshots |
| API checks | Verifies reported version matches tag, session persistence, Identity Vault encryption/roundtrip, and returns 200 OK across all GET endpoints |
| Diagnostics | Runs `tests.run_tests`, `plugins.preflight_sandbox`, and `plugins.smoke_test` inside API container |
| Log scan | Counts and aggregates container ERROR/CRITICAL lines, Python tracebacks, and web server errors |

### 2. Upgrade test (~20–25 min)

1. Installs previous release, sets up administrator, and writes Identity Vault test records.
2. Upgrades via `git checkout <tag>`, `docker compose down`, `docker compose build`, `docker compose up -d`.
3. Verifies existing credentials, completed setup state, database schema migrations, and ciphertext decryptions. Re-runs API endpoints and log inspections.

### 3. Reporting

- **Summary tab**: Displays pass/fail status and run diagnostics.
- **Failures**: Automatically opens a GitHub issue titled `Release test failed: <tag>` (label: `release-test`). Passing re-runs close the issue automatically.
- **Artifacts**: Downloadable zip bundles containing full screenshots, installer output, and container logs.

## Manual execution

Go to **Actions → Release test → Run workflow**:
- **Release tag to test**: Target release git tag (leave blank for latest).
- **Upgrade test: start from this tag**: Base tag for upgrade test (or `none` to skip).

## Operational details

- Workflow runs on published releases or pre-releases (drafts do not trigger runs).
- Releases published by default `GITHUB_TOKEN` do not cascade to workflows; manual web or CLI releases (`gh release create`) trigger as expected.
- Version match: `/api/health` must match the release tag (e.g., tag `0.10.0-rc1` matches `VERSION` `0.10.0-rc1`).
- Tests execute scripts from `main` (`.github/release-test/`).

## Local reproduction

With OpenOptOut running locally on port 80:

```bash
pip install playwright && python -m playwright install --with-deps chromium

# Browser walk-through on fresh instance
python3 .github/release-test/ui_check.py --base-url http://localhost --out-dir ./release-report --creds-file ./release-report/creds.json

# API check with credentials created during browser walk-through
python3 .github/release-test/setup_check.py --base-url http://localhost --creds-file ./release-report/creds.json --out-dir ./release-report

# Log scan
docker compose logs --no-color > containers.log
python3 .github/release-test/scan_logs.py "local" containers.log ./release-report/logs.md
```
