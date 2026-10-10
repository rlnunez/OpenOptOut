# Automated security scanning

OpenOptOut runs automated security scanners on pushes and pull requests, aggregating results in the repository **Security → Code scanning** tab.

## Scanning matrix

| Tool | Focus | Trigger |
|---|---|---|
| **CodeQL** | Injection, traversal, deserialization, authentication vulnerabilities | Pushes and pull requests via GitHub default setup |
| **Semgrep** | OWASP Top 10, FastAPI, React, Dockerfiles, and custom repository rules (`.semgrep/`) | Pushes and pull requests |
| **Bandit** | Python AST security checks (weak crypto, shell exec, temporary files) | Pushes and pull requests |
| **Gitleaks** | Secret and API key detection across git history | Pushes and pull requests |
| **TruffleHog** | Secret detection with active credential verification (live keys fail the build) | Pushes and pull requests |
| **OSV-Scanner** | Direct and transitive dependency CVEs across Python and npm | Pushes and pull requests |
| **Trivy (config)** | Misconfiguration in Dockerfiles and Compose files | Pushes and pull requests |
| **Hadolint** | Dockerfile linting and best practices | Pushes and pull requests |
| **ShellCheck** | Static analysis for shell scripts (`install.sh`, `scripts/`, `deploy/`) | Pushes and pull requests |
| **zizmor + actionlint** | GitHub Actions workflow security linting | Pushes and pull requests |
| **Trivy (images)** | Vulnerabilities in built container images | Push to `main`, weekly, manual trigger |
| **Schemathesis** | Stateful API fuzzing, unauthenticated endpoint detection, state leaks | Push to `main`, weekly, manual trigger |
| **OWASP ZAP** | Dynamic application security testing (DAST) against running staging API | Push to `main`, weekly, manual trigger |
| **ClusterFuzzLite + Atheris** | Coverage-guided fuzzing on untrusted inputs (broker specs, manifests, job envelopes, log sanitizer) | PRs touching `backend/`, weekly, manual trigger |
| **OpenSSF Scorecard** | Supply-chain security posture (branch protection, pinned dependencies, reviews) | Push to `main`, weekly |
| **Dependabot** | Automated PRs for dependency updates | Weekly, immediate on CVEs |

Findings are report-only except for verified live secrets (TruffleHog) which immediately fail the workflow.

### Custom Semgrep rules (`.semgrep/openoptout.yml`)

- `pii-in-log-call`, `pii-variable-in-log-call`, `identity-vault-value-in-log`: Prevents patron PII leaks into log files.
- `hardcoded-fallback-secret`: Flags fallback default secrets in `os.getenv`.
- `cors-wildcard-with-credentials`: Flags wildcard CORS origins paired with credentials.
- `queue-message-signature-not-verified`: Flags unsigned Redis queue ingestion.
- `httpx-tls-verification-disabled`, `jwt-unverified-claims`: Flags disabled TLS or signature checks.
- `exception-text-returned-to-client`: Flags raw exception leaks to API responses.
- `non-constant-time-secret-compare`: Flags timing-attack-vulnerable secret equality checks.

### DAST isolation

Dynamic testing executes within an internal isolated Docker network (`.github/security/docker-compose.dast.yml`) with outbound internet disabled to prevent outbound requests to external brokers or mail servers.

## Repository setup

### 1. Workflow files

- `.github/workflows/security.yml`: Main scanner pipeline.
- `.github/workflows/scorecard.yml`: OpenSSF Scorecard.
- `.github/dependabot.yml`: Automated dependency updates.
- `.github/security/`: Runner scripts and isolated DAST compose environment.
- `.semgrep/openoptout.yml`: Repository Semgrep rules.
- `.gitleaksignore`: Validated secret false positives.
- `SECURITY.md`: Vulnerability reporting process.

### 2. GitHub security settings

Enable in **Settings → Code security**:
- **Dependency graph**, **Dependabot alerts**, and **Dependabot security updates**
- **Secret Protection** and **Push protection**
- **Private vulnerability reporting**
- **CodeQL analysis**: Default setup

## Inspecting results

1. **Security → Code scanning**: Triage alerts by severity (Critical / High / Error).
2. **Actions → Run → Summary**: High-level severity counts and rule breakdowns.
3. **Actions → Run → Artifacts → `dast-reports`**: Contains `zap-report.html`, `schemathesis.txt`, `openapi.json`, and container execution logs.

## Suppressions and triage

Triage findings via GitHub Security UI (Dismiss alert as False positive or Won't fix), or via inline comments with documented rationale:
- Semgrep: `# nosemgrep: <rule-id>`
- Bandit: `# nosec <id>`
- Gitleaks: Add fingerprint to `.gitleaksignore`
- Hadolint: `# hadolint ignore=<rule>`
- ShellCheck: `# shellcheck disable=<rule>`

## Local execution

```bash
pip install semgrep bandit zizmor
semgrep scan --config .semgrep/ --config p/python --config p/owasp-top-ten backend/
bandit -r backend -x backend/tests -s B101,B110,B112
zizmor .github/workflows/

gitleaks git .
osv-scanner scan source -r .
trivy config .
shellcheck install.sh scripts/*.sh
```

## Fuzz targets

Fuzz harnesses are located in `fuzz/`:
- `fuzz_broker_spec.py`: Validates broker spec parsing and compilation safety.
- `fuzz_plugin_manifest.py`: Validates plugin manifest structure and schema parsing.
- `fuzz_plugin_code_inspector.py`: Validates plugin AST analysis safety.
- `fuzz_job_envelope.py`: Validates cryptographic job envelope verification.
- `fuzz_log_sanitizer.py`: Validates log sanitizer regex stability and token stripping.
- `fuzz_identity_combos.py`: Validates identity vault search term combinations.

Local fuzzing command:
```bash
pip install atheris
bash fuzz/build_pkgroot.sh
cd fuzz
python fuzz_broker_spec.py -max_total_time=120
```

## Maintenance

- **Pinned dependencies**: Pinned GitHub Actions use full commit SHAs. Do not downgrade pinned SHAs without verifying integrity.
- **Excluded packages**: Deliberately pinned packages (bcrypt, cryptography, pysaml2, playwright) are configured in `.github/dependabot.yml`.
