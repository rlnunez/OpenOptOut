# Authoring CAPTCHA Solver Plugins for OpenOptOut

CAPTCHA solver plugins provide automated or assisted challenge resolution for data broker opt-out flows. Solvers execute inside an isolated subprocess sandbox.

---

## 1. Directory Structure

```text
my-captcha-solver/
├── manifest.json
├── plugin.py
└── README.md
```

---

## 2. Manifest Schema (`manifest.json`)

```json
{
  "id": "my-captcha-solver",
  "name": "Custom CAPTCHA Solver",
  "version": "1.0.0",
  "author": "Your Name / Organization",
  "type": "captcha",
  "description": "Solves visual challenges using external API service.",
  "entrypoint": "plugin.py",
  "hooks": ["solve_captcha"],
  "permissions": ["solve_captcha", "network", "settings_read"],
  "outbound_domains": ["api.captchaservice.com"]
}
```

Key manifest rules:
- `type`: Must be `"captcha"`.
- `hooks`: Must include `"solve_captcha"`.
- `permissions`: Allowed permissions are strictly limited to `solve_captcha`, `network`, `http_fetch`, `settings_read`, and `storage`.
- `outbound_domains`: Must declare any third-party API hosts accessed by the solver.

---

## 3. Privacy Preservation Rule

CAPTCHA challenges sent to external services or human reviewers **must never contain personal information**.
- OpenOptOut's core engine automatically scrubs screenshots using `captcha_privacy.py` before passing image payloads to the solver.
- A solver plugin must never attempt to access or extract member names, addresses, or phone numbers from page context.
