# OpenOptOut Community Marketplace (`openoptout-market`)

> **Official community catalog, plugin registry, and authoring guidelines for OpenOptOut privacy automation, broker removal specs, accessibility themes, and language packs.**

This repository hosts the official declarative registry (`plugins.json`) and automated catalog index (`index.json`) consumed by OpenOptOut instances worldwide.

---

## Plugin Categories and Developer Documentation

Every plugin submitted to OpenOptOut must follow standardized conventions based on its functional type. Detailed guides and reference schemas are provided below:

| Type | Description | Authoring Guide | Reference Example |
|---|---|---|---|
| `brokers` | Declarative opt-out removal specs for people-search sites and directories. | [Broker Guide](docs/BROKERS.md) | [Mock Directory Example](examples/broker-mock-directory) |
| `themes` | Accessible visual themes, high-contrast palettes, and institutional branding. | [Theme & CSS Guide](docs/THEMES.md) | [WCAG AAA Theme Example](examples/theme-high-contrast-aaa) |
| `languages` | Regional UI translations and Right-to-Left (RTL) layout dictionaries. | [Language Pack Guide](docs/LANGUAGES.md) | [Language Example](docs/LANGUAGES.md#1-directory-structure) |
| `captcha` | Sandboxed human-in-the-loop and external CAPTCHA solver bridges. | [CAPTCHA Solver Guide](docs/CAPTCHA.md) | [CAPTCHA Example](docs/CAPTCHA.md#1-directory-structure) |
| `email` | Outbound opt-out delivery relays and confirmation parsers. | [Email Provider Guide](docs/EMAIL.md) | [Email Example](docs/EMAIL.md#1-directory-structure) |

---

## Accessibility and ADA Standards (WCAG 2.2 AA / AAA)

OpenOptOut is deployed in public libraries, schools, municipal offices, and consortium networks. Accessibility is a first-class requirement across all plugins and themes:

1. **Baseline Compliance:** All user interface extensions and themes must achieve **WCAG 2.2 Level AA** compliance at a minimum.
2. **Target Compliance:** Authors are strongly encouraged to target **WCAG 2.2 Level AAA** for high-contrast and civic themes.
3. **Contrast Ratios:**
   - Normal text: At least 4.5:1 (AA) or 7.0:1 (AAA) against background surfaces.
   - Large text (18pt+ or 14pt+ bold): At least 3.0:1 (AA) or 4.5:1 (AAA).
   - Component boundaries and focus indicators: At least 3.0:1 (AA) or 4.5:1 (AAA).
4. **Focus Rings:** Themes must never hide keyboard focus (`outline: none` without replacement is prohibited). Provide at least a 2px outline with 3:1 contrast against surrounding pixels.
5. **Reduced Motion:** Honor `@media (prefers-reduced-motion: reduce)` by clamping transition and animation durations.

---

## Bundled Translations for UI-Modifying Plugins (`locales/`)

Plugins that present text, notifications, or manual checkpoints in the OpenOptOut interface (such as `brokers`, `captcha`, and `email` providers) can bundle their own localized phrase packs directly inside a `locales/` directory:

```text
my-plugin/
├── manifest.json
├── spec.json (or plugin.py)
├── README.md
└── locales/
    ├── es.json
    ├── fr.json
    └── de.json
```

- In `manifest.json`, declare available languages: `"locales": ["es", "fr", "de"]`.
- Files map keys (e.g. `"description"`, `"instructions"`, `"steps.4.text"`, or custom UI notification keys) to localized strings.
- Translations preserve variable placeholders such as `{contact_email}` and `{listing_url}`.
- Our automated CI workflow validates all JSON files in `locales/` on every pull request.


---

## Automated CI and Release Tasks for Your Repository

To maintain quality and avoid broken releases, plugin authors should enable automated testing and packaging in their own repositories.

We provide a turnkey GitHub Actions workflow file that you can copy directly into your repository:

- **Workflow File:** [`templates/workflows/plugin-ci.yml`](templates/workflows/plugin-ci.yml)

### What the Automated Workflow Does
1. **Schema Validation:** Verifies `manifest.json` fields, types, and permissions.
2. **Automated Testing:**
   - For `brokers`: Validates `spec.json` syntax and confirms absence of prohibited credentials (SSNs, passwords, government IDs).
   - For `themes`: Calculates exact mathematical color contrast ratios against WCAG 2.2 standards and validates CSS selectors.
   - For `languages`: Validates JSON dictionary structure and RTL directives.
3. **Automated Release Packaging:** When you push a git release tag (e.g. `git tag v1.0.0 && git push origin v1.0.0`), the workflow automatically bundles your plugin into `<plugin-id>-<version>.zip` and attaches it directly to the GitHub Release.

---

## How to Submit a Plugin

Submitting a plugin is a one-time process. Once your repository is registered in `plugins.json`, all future releases and updates are indexed automatically without requiring new pull requests.

### Step 1: Create and Verify Your Plugin
Author your plugin according to the relevant guide in `docs/`. Test your plugin locally or with our validation tools:
- For themes: `python3 tools/validate_theme.py <path-to-theme>`
- For broker specs: [Agensii Broker Development Skill](https://www.agensi.io/skills/openoptout-broker-development-and-repair-plugin) or `tools/validate_submission.py`

### Step 2: Publish a Release on Your Repository
1. Commit your files (`manifest.json`, `README.md`, and type-specific files like `spec.json` or `theme.json`) to your GitHub repository.
2. Draft a new release on GitHub with a SemVer tag (e.g., `v1.0.0`).
3. Attach your packaged `.zip` file, or let our automated CI workflow attach it for you.

### Step 3: Open a Pull Request
1. Fork this repository (`openoptout-market`).
2. Add your plugin entry to `plugins.json`:
   ```json
   {
     "id": "my_plugin_id",
     "name": "My Plugin Name",
     "description": "Clear explanation of what this plugin provides.",
     "repo": "your-username/openoptout-my-plugin",
     "category": "themes",
     "author": "Your Name / Organization",
     "tier": 2
   }
   ```
3. Open a Pull Request.
4. Our automated CI verifies repository availability, archive structure, and checksum compatibility.
5. Once merged, your plugin is indexed and live across OpenOptOut instances within 6 hours.

---

## How Updates Work

Whenever you repair a flow, improve contrast, or add translations:
1. Commit the changes to your own repository.
2. Bump `version` in your `manifest.json`.
3. Publish a new GitHub Release (e.g., `v1.1.0`).
4. Our automated indexing action runs every 6 hours, detects the new release, calculates SHA-256 integrity checksums, and updates `index.json`.

---

## Security & Quality Guidelines

- **Declarative Logic:** Broker plugins must be pure JSON specs (`spec.json`). Executable Python/Bash scripts are prohibited in broker add-on paths.
- **Data-Only Types:** Themes, language packs, and letter templates must contain zero executable scripts.
- **Sandbox Isolation:** Executable plugins (`captcha`, `email`) execute inside OS-level namespaces (bubblewrap/seccomp) with strict egress allowlists.
- **Zero Real PII in Fixtures:** Never commit personal details, real emails, or live credentials.

---

## License

The marketplace registry, submission tools, and catalog index are licensed under the [MIT License](LICENSE). Individual plugins retain their authors declared open-source licenses.
