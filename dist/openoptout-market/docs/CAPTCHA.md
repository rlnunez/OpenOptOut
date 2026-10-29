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

---

## 4. Plugin-Bundled Translations (`locales/`)

CAPTCHA plugins that present instructional prompts or status notices in the OpenOptOut interface should include localized strings inside a `locales/` directory:

```text
my-captcha-solver/
├── manifest.json
├── plugin.py
├── README.md
└── locales/
    ├── es.json
    ├── fr.json
    └── de.json
```

Example `locales/es.json`:
```json
{
  "description": "Resuelve desafíos visuales utilizando un servicio externo.",
  "prompt_solving": "Resolviendo desafío de seguridad, por favor espere...",
  "prompt_manual_fallback": "No se pudo resolver automáticamente. Por favor resuelva el desafío en pantalla.",
  "status_timeout": "El intento de resolución agotó el tiempo de espera."
}
```
All keys must be strings and map to clear localized phrases.


