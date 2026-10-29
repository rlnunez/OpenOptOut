#!/usr/bin/env python3
"""
Export bundled OpenOptOut plugins into dedicated category repositories:
  1. openoptout-brokers   (80 brokers)
  2. openoptout-languages (17 language packs)
  3. openoptout-email     (4 email providers)
  4. openoptout-captcha   (1 captcha solving service)
  5. openoptout-letters   (7 legal opt-out templates)

Also generates release package zips under dist/openoptout-market/packages/
and compiles the canonical marketplace index.json with SHA-256 checksums.

NO EMOTICONS OR EMOJIS in any generated markdown documentation.
"""

import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLED_DIR = os.path.join(ROOT, "backend", "plugins", "bundled")
MARKET_DIR = os.path.join(ROOT, "dist", "openoptout-market")
REPOS_DIR = os.path.join(ROOT, "dist", "repos")

BASE_DOWNLOAD_URL = "https://rlnunez.github.io/openoptout-market"

AGPL_LICENSE = """                    GNU AFFERO GENERAL PUBLIC LICENSE
                       Version 3, 19 November 2007

 Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
 Everyone is permitted to copy and distribute verbatim copies
 of this license document, but changing it is not allowed.

                            Preamble

  The GNU Affero General Public License is a free, copyleft license for
software and other kinds of works, specifically designed to ensure
cooperation with the community in the case of network server software.
...
"""

VALIDATOR_SCRIPTS = {
    "brokers": """#!/usr/bin/env python3
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
PLUGINS_DIR = os.path.join(REPO_ROOT, "plugins")

KNOWN_STEPS = {
    "navigate", "fill", "type", "select", "check", "click", "click_matching",
    "press", "frame", "scroll", "wait_for", "wait", "submit", "expect_success",
    "solve_captcha", "autofill", "pick_listing", "pause_for_human"
}

def validate_broker(folder):
    errs = []
    p_path = os.path.join(PLUGINS_DIR, folder)
    for req in ("manifest.json", "spec.json", "README.md"):
        if not os.path.isfile(os.path.join(p_path, req)):
            errs.append(f"missing {req}")
    if errs:
        return errs

    for root, _, files in os.walk(p_path):
        for f in files:
            if f.endswith((".py", ".sh", ".exe", ".bin", ".bat", ".so", ".dylib")):
                errs.append(f"Invariant 1 violation: executable file '{f}' found")

    with open(os.path.join(p_path, "manifest.json"), "r", encoding="utf-8") as fh:
        try:
            m = json.load(fh)
            if m.get("type") != "brokers":
                errs.append(f"manifest: type must be 'brokers', got '{m.get('type')}'")
            if not m.get("id"):
                errs.append("manifest: missing id")
        except Exception as e:
            errs.append(f"manifest.json invalid JSON: {e}")

    with open(os.path.join(p_path, "spec.json"), "r", encoding="utf-8") as fh:
        try:
            s = json.load(fh)
            if not s.get("broker_id"):
                errs.append("spec: missing broker_id")
            for idx, step in enumerate(s.get("steps", [])):
                kind = step.get("kind")
                if kind not in KNOWN_STEPS:
                    errs.append(f"step {idx}: unknown kind '{kind}'")
        except Exception as e:
            errs.append(f"spec.json invalid JSON: {e}")

    return errs

def main():
    plugin_folders = sorted([d for d in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, d)) and not d.startswith(".")])
    failed = False
    for f in plugin_folders:
        errs = validate_broker(f)
        if errs:
            print(f"FAIL  {f}: {', '.join(errs)}")
            failed = True
        else:
            print(f"ok    {f}")
    if failed:
        sys.exit(1)
    print(f"\\nAll {len(plugin_folders)} broker plugin(s) valid.")

if __name__ == "__main__":
    main()
""",
    "languages": """#!/usr/bin/env python3
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
PLUGINS_DIR = os.path.join(REPO_ROOT, "plugins")

def validate_lang(folder):
    errs = []
    p_path = os.path.join(PLUGINS_DIR, folder)
    for req in ("manifest.json", "texts.json"):
        if not os.path.isfile(os.path.join(p_path, req)):
            errs.append(f"missing {req}")
    if errs:
        return errs

    with open(os.path.join(p_path, "manifest.json"), "r", encoding="utf-8") as fh:
        try:
            m = json.load(fh)
            if m.get("type") != "languages":
                errs.append("manifest: type must be 'languages'")
            if not m.get("language_code"):
                errs.append("manifest: missing language_code")
        except Exception as e:
            errs.append(f"manifest.json invalid JSON: {e}")

    with open(os.path.join(p_path, "texts.json"), "r", encoding="utf-8") as fh:
        try:
            t = json.load(fh)
            if not isinstance(t, dict):
                errs.append("texts.json must be a JSON object mapping phrases to translations")
        except Exception as e:
            errs.append(f"texts.json invalid JSON: {e}")

    return errs

def main():
    plugin_folders = sorted([d for d in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, d)) and not d.startswith(".")])
    failed = False
    for f in plugin_folders:
        errs = validate_lang(f)
        if errs:
            print(f"FAIL  {f}: {', '.join(errs)}")
            failed = True
        else:
            print(f"ok    {f}")
    if failed:
        sys.exit(1)
    print(f"\\nAll {len(plugin_folders)} language pack(s) valid.")

if __name__ == "__main__":
    main()
""",
    "email": """#!/usr/bin/env python3
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
PLUGINS_DIR = os.path.join(REPO_ROOT, "plugins")

def validate_email(folder):
    errs = []
    p_path = os.path.join(PLUGINS_DIR, folder)
    for req in ("manifest.json", "plugin.py"):
        if not os.path.isfile(os.path.join(p_path, req)):
            errs.append(f"missing {req}")
    if errs:
        return errs

    with open(os.path.join(p_path, "manifest.json"), "r", encoding="utf-8") as fh:
        try:
            m = json.load(fh)
            if m.get("type") != "email":
                errs.append("manifest: type must be 'email'")
            if "email_provider" not in m.get("hooks", []):
                errs.append("manifest: missing required 'email_provider' hook")
        except Exception as e:
            errs.append(f"manifest.json invalid JSON: {e}")

    return errs

def main():
    plugin_folders = sorted([d for d in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, d)) and not d.startswith(".")])
    failed = False
    for f in plugin_folders:
        errs = validate_email(f)
        if errs:
            print(f"FAIL  {f}: {', '.join(errs)}")
            failed = True
        else:
            print(f"ok    {f}")
    if failed:
        sys.exit(1)
    print(f"\\nAll {len(plugin_folders)} email provider plugin(s) valid.")

if __name__ == "__main__":
    main()
""",
    "captcha": """#!/usr/bin/env python3
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
PLUGINS_DIR = os.path.join(REPO_ROOT, "plugins")

def validate_captcha(folder):
    errs = []
    p_path = os.path.join(PLUGINS_DIR, folder)
    for req in ("manifest.json", "plugin.py"):
        if not os.path.isfile(os.path.join(p_path, req)):
            errs.append(f"missing {req}")
    if errs:
        return errs

    with open(os.path.join(p_path, "manifest.json"), "r", encoding="utf-8") as fh:
        try:
            m = json.load(fh)
            if m.get("type") != "captcha":
                errs.append("manifest: type must be 'captcha'")
            if "solve_captcha" not in m.get("hooks", []):
                errs.append("manifest: missing required 'solve_captcha' hook")
        except Exception as e:
            errs.append(f"manifest.json invalid JSON: {e}")

    return errs

def main():
    plugin_folders = sorted([d for d in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, d)) and not d.startswith(".")])
    failed = False
    for f in plugin_folders:
        errs = validate_captcha(f)
        if errs:
            print(f"FAIL  {f}: {', '.join(errs)}")
            failed = True
        else:
            print(f"ok    {f}")
    if failed:
        sys.exit(1)
    print(f"\\nAll {len(plugin_folders)} captcha plugin(s) valid.")

if __name__ == "__main__":
    main()
""",
    "letters": """#!/usr/bin/env python3
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
PLUGINS_DIR = os.path.join(REPO_ROOT, "plugins")

def validate_letter(folder):
    errs = []
    p_path = os.path.join(PLUGINS_DIR, folder)
    for req in ("manifest.json", "letter.json"):
        if not os.path.isfile(os.path.join(p_path, req)):
            errs.append(f"missing {req}")
    if errs:
        return errs

    with open(os.path.join(p_path, "manifest.json"), "r", encoding="utf-8") as fh:
        try:
            m = json.load(fh)
            if m.get("type") != "letters":
                errs.append("manifest: type must be 'letters'")
        except Exception as e:
            errs.append(f"manifest.json invalid JSON: {e}")

    with open(os.path.join(p_path, "letter.json"), "r", encoding="utf-8") as fh:
        try:
            l = json.load(fh)
            langs = l.get("languages", {})
            if not langs:
                errs.append("letter.json must contain 'languages'")
            for lang_code, tmpl in langs.items():
                if not tmpl.get("subject") or not tmpl.get("body"):
                    errs.append(f"letter.json languages['{lang_code}'] must contain 'subject' and 'body'")
        except Exception as e:
            errs.append(f"letter.json invalid JSON: {e}")

    return errs

def main():
    plugin_folders = sorted([d for d in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, d)) and not d.startswith(".")])
    failed = False
    for f in plugin_folders:
        errs = validate_letter(f)
        if errs:
            print(f"FAIL  {f}: {', '.join(errs)}")
            failed = True
        else:
            print(f"ok    {f}")
    if failed:
        sys.exit(1)
    print(f"\\nAll {len(plugin_folders)} letter template(s) valid.")

if __name__ == "__main__":
    main()
"""
}

PACKAGE_SCRIPT = """#!/usr/bin/env python3
\"\"\"Package plugins in plugins/ into distribution .zip files.\"\"\"
import os, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
PLUGINS_DIR = os.path.join(REPO_ROOT, "plugins")
DIST_DIR = os.path.join(REPO_ROOT, "dist")

def package_all():
    os.makedirs(DIST_DIR, exist_ok=True)
    plugin_folders = sorted([d for d in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, d)) and not d.startswith(".")])
    for f in plugin_folders:
        src = os.path.join(PLUGINS_DIR, f)
        out = os.path.join(DIST_DIR, f"{f}.zip")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(src):
                dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
                for file in files:
                    if file.endswith((".pyc", ".DS_Store")): continue
                    fp = os.path.join(root, file)
                    zf.write(fp, os.path.relpath(fp, src))
        print(f"Packaged: {out}")
    print(f"Successfully packaged {len(plugin_folders)} plugin(s) into {DIST_DIR}/")

if __name__ == "__main__":
    package_all()
"""

CATEGORIES = [
    {
        "id": "brokers",
        "repo_name": "openoptout-brokers",
        "title": "OpenOptOut Data Broker Plugins",
        "description": "Official community-curated data broker opt-out plugins for OpenOptOut.",
        "source_dir": os.path.join(BUNDLED_DIR, "brokers"),
        "type": "brokers",
        "tier": 1,
        "author": "OpenOptOut Core Team",
        "readme_notes": "All broker plugins are declarative pure-data specifications adhering to the OpenOptOut spec schema. No executable scripts, network sockets outside declared outbound domains, or arbitrary binaries are permitted."
    },
    {
        "id": "languages",
        "repo_name": "openoptout-languages",
        "title": "OpenOptOut Language Packs",
        "description": "Official translations and language packs for OpenOptOut interface screens and plugins.",
        "source_dir": os.path.join(BUNDLED_DIR, "languages"),
        "type": "languages",
        "tier": 1,
        "author": "OpenOptOut Contributors",
        "readme_notes": "Language packs contain texts.json translating core UI phrases and plugins/<id>.json translating individual plugins. RTL formatting conforms to logical Tailwind start/end classes."
    },
    {
        "id": "email",
        "repo_name": "openoptout-email",
        "title": "OpenOptOut Email Provider Plugins",
        "description": "Official email provider integrations for sending opt-out emails and receiving confirmation tokens.",
        "source_dir": os.path.join(BUNDLED_DIR, "email"),
        "type": "email",
        "tier": 1,
        "author": "OpenOptOut Core Team",
        "readme_notes": "Email provider plugins run inside hardened bubblewrap/seccomp sandboxes. Credentials and OAuth refresh tokens are encrypted at rest with AES-256-GCM."
    },
    {
        "id": "captcha",
        "repo_name": "openoptout-captcha",
        "title": "OpenOptOut CAPTCHA Solver Plugins",
        "description": "Official CAPTCHA solving integration plugins for automated opt-out execution.",
        "source_dir": os.path.join(BUNDLED_DIR, "captcha"),
        "type": "captcha",
        "tier": 1,
        "author": "OpenOptOut Core Team",
        "readme_notes": "All puzzle challenges transmitted to remote solvers have personal details strictly blacked out via captcha_privacy.py prior to transmission."
    },
    {
        "id": "letters",
        "repo_name": "openoptout-letters",
        "title": "OpenOptOut Legal Opt-Out Letter Templates",
        "description": "Official statutory opt-out letter templates (CCPA, GDPR, LGPD, PIPEDA, and US State Laws).",
        "source_dir": os.path.join(BUNDLED_DIR, "letters"),
        "type": "letters",
        "tier": 1,
        "author": "OpenOptOut Legal WG",
        "readme_notes": "Every built-in letter is a draft awaiting attorney review. These templates do not constitute legal advice."
    }
]


def make_clean_zip(source_dir: str, output_zip_path: str):
    """Bundle directory into zip excluding __pycache__, .DS_Store, and git files."""
    os.makedirs(os.path.dirname(output_zip_path), exist_ok=True)
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".pytest_cache")]
            for file in files:
                if file in (".DS_Store", "thumbs.db") or file.endswith(".pyc"):
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zf.write(file_path, arcname)


def compute_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_repo_ci_workflow() -> str:
    return """name: Plugin Quality & Validation CI

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]
  pull_request:
    branches: [ main ]

jobs:
  validate:
    name: Validate Plugins
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Validate Plugin Specs & Manifests
        run: |
          if [ -f tools/validate.py ]; then
            python3 tools/validate.py
          fi
"""


def main():
    os.makedirs(REPOS_DIR, exist_ok=True)
    os.makedirs(os.path.join(MARKET_DIR, "packages"), exist_ok=True)
    os.makedirs(os.path.join(MARKET_DIR, "public", "packages"), exist_ok=True)

    all_catalog_entries = []

    # Preserve any existing examples (like mock broker or high contrast theme)
    existing_examples = [
        {
            "id": "mock_broker",
            "type": "brokers",
            "name": "Mock People Directory",
            "version": "1.0.0",
            "description": "Reference opt-out plugin demonstrating safe form automation, alias emails, and human-in-the-loop CAPTCHA escalation.",
            "author": "OpenOptOut Community",
            "repo": "rlnunez/openoptout-market",
            "tier": 2,
            "archive_url": f"{BASE_DOWNLOAD_URL}/packages/brokers/mock_broker.zip",
            "min_core_version": "0.11.0",
            "recommended_bundle": False,
            "readme": "Reference opt-out plugin for local verification.",
            "readme_url": "https://github.com/rlnunez/openoptout-market/tree/main/examples/broker-mock-directory#readme"
        },
        {
            "id": "theme-high-contrast-aaa",
            "type": "themes",
            "name": "High Contrast Accessible (AAA)",
            "version": "1.0.0",
            "description": "Ultra-accessible high contrast theme meeting WCAG 2.2 Level AAA standards with minimum 7:1 contrast on all surfaces.",
            "author": "OpenOptOut Core",
            "repo": "rlnunez/openoptout-market",
            "tier": 1,
            "archive_url": f"{BASE_DOWNLOAD_URL}/packages/themes/theme-high-contrast-aaa.zip",
            "min_core_version": "0.11.0",
            "recommended_bundle": True,
            "readme": "WCAG 2.2 Level AAA compliant theme with high contrast tokens.",
            "readme_url": "https://github.com/rlnunez/openoptout-market/tree/main/examples/theme-high-contrast-aaa#readme"
        }
    ]

    # Package existing examples
    mock_src = os.path.join(MARKET_DIR, "examples", "broker-mock-directory")
    if os.path.isdir(mock_src):
        os.makedirs(os.path.join(MARKET_DIR, "packages", "brokers"), exist_ok=True)
        os.makedirs(os.path.join(MARKET_DIR, "public", "packages", "brokers"), exist_ok=True)
        pkg_path = os.path.join(MARKET_DIR, "packages", "brokers", "mock_broker.zip")
        make_clean_zip(mock_src, pkg_path)
        shutil.copy2(pkg_path, os.path.join(MARKET_DIR, "public", "packages", "brokers", "mock_broker.zip"))
        existing_examples[0]["sha256"] = compute_sha256(pkg_path)

    theme_src = os.path.join(MARKET_DIR, "examples", "theme-high-contrast-aaa")
    if os.path.isdir(theme_src):
        os.makedirs(os.path.join(MARKET_DIR, "packages", "themes"), exist_ok=True)
        os.makedirs(os.path.join(MARKET_DIR, "public", "packages", "themes"), exist_ok=True)
        pkg_path = os.path.join(MARKET_DIR, "packages", "themes", "theme-high-contrast-aaa.zip")
        make_clean_zip(theme_src, pkg_path)
        shutil.copy2(pkg_path, os.path.join(MARKET_DIR, "public", "packages", "themes", "theme-high-contrast-aaa.zip"))
        existing_examples[1]["sha256"] = compute_sha256(pkg_path)

    all_catalog_entries.extend(existing_examples)

    # Process each category
    for cat in CATEGORIES:
        cat_id = cat["id"]
        repo_name = cat["repo_name"]
        cat_src = cat["source_dir"]
        repo_target = os.path.join(REPOS_DIR, repo_name)

        print(f"[*] Processing category: {cat_id} -> {repo_name}...")
        os.makedirs(repo_target, exist_ok=True)
        os.makedirs(os.path.join(repo_target, "plugins"), exist_ok=True)
        os.makedirs(os.path.join(repo_target, ".github", "workflows"), exist_ok=True)
        os.makedirs(os.path.join(repo_target, "tools"), exist_ok=True)

        # Write CI workflow
        with open(os.path.join(repo_target, ".github", "workflows", "ci.yml"), "w", encoding="utf-8") as f:
            f.write(generate_repo_ci_workflow())

        # Write LICENSE
        with open(os.path.join(repo_target, "LICENSE"), "w", encoding="utf-8") as f:
            f.write(AGPL_LICENSE)

        # Write repository README.md (ZERO EMOJIS)
        readme_content = f"""# {cat['title']}

{cat['description']}

This repository houses official Tier 1 {cat['id']} plugins maintained by the OpenOptOut project and published to the OpenOptOut Community Marketplace.

## Quality Standards

- OpenOptOut is designed to be deployed in homes, public libraries, universities, schools, municipal offices, and consortiums.
- All plugins adhere strictly to OpenOptOut security invariants: no arbitrary binaries, zero tracking telemetry, and complete sandboxing.
- Accessibility target: WCAG 2.2 Level AA baseline / Level AAA target.

## Plugin Guidelines

{cat['readme_notes']}

## Architecture & Directory Layout

```
plugins/
  <plugin-id>/
    manifest.json
    ...
tools/
  validate.py
  package.py
```

## Validation & Packaging

To validate all plugins in this repository:
```bash
python3 tools/validate.py
```

To build distribution .zip packages:
```bash
python3 tools/package.py
```

## License

GNU Affero General Public License v3.0 (AGPL-3.0).
"""
        with open(os.path.join(repo_target, "README.md"), "w", encoding="utf-8") as f:
            f.write(readme_content)

        # Write validator tool
        validator_script = VALIDATOR_SCRIPTS.get(cat_id)
        if validator_script:
            val_path = os.path.join(repo_target, "tools", "validate.py")
            with open(val_path, "w", encoding="utf-8") as vf:
                vf.write(validator_script)
            os.chmod(val_path, 0o755)

        # Write packaging tool
        pkg_tool_path = os.path.join(repo_target, "tools", "package.py")
        with open(pkg_tool_path, "w", encoding="utf-8") as pf:
            pf.write(PACKAGE_SCRIPT)
        os.chmod(pkg_tool_path, 0o755)

        # Process each plugin in this category
        plugin_dirs = [d for d in os.listdir(cat_src) if os.path.isdir(os.path.join(cat_src, d)) and not d.startswith(".")]
        plugin_dirs.sort()

        os.makedirs(os.path.join(MARKET_DIR, "packages", cat_id), exist_ok=True)
        os.makedirs(os.path.join(MARKET_DIR, "public", "packages", cat_id), exist_ok=True)

        for p_dir in plugin_dirs:
            full_plugin_src = os.path.join(cat_src, p_dir)
            target_plugin_dest = os.path.join(repo_target, "plugins", p_dir)

            # Copy plugin folder to category repo
            if os.path.exists(target_plugin_dest):
                shutil.rmtree(target_plugin_dest)
            shutil.copytree(full_plugin_src, target_plugin_dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))

            # Read manifest.json
            manifest_file = os.path.join(full_plugin_src, "manifest.json")
            if not os.path.isfile(manifest_file):
                continue

            with open(manifest_file, "r", encoding="utf-8") as mf:
                try:
                    manifest = json.load(mf)
                except Exception as e:
                    print(f"    Error reading {manifest_file}: {e}")
                    continue

            p_id = manifest.get("id", p_dir)
            name = manifest.get("name", p_dir.capitalize())
            version = manifest.get("version", "1.0.0")
            description = manifest.get("description", f"Official OpenOptOut {cat_id} plugin.")
            author = manifest.get("author", cat["author"])

            # Read README.md if present
            readme_text = ""
            for r_name in ("README.md", "readme.md", "README"):
                r_path = os.path.join(full_plugin_src, r_name)
                if os.path.isfile(r_path):
                    with open(r_path, "r", encoding="utf-8", errors="replace") as rf:
                        readme_text = rf.read()
                    break

            # Build package zip
            pkg_zip_path = os.path.join(MARKET_DIR, "packages", cat_id, f"{p_id}.zip")
            make_clean_zip(full_plugin_src, pkg_zip_path)
            shutil.copy2(pkg_zip_path, os.path.join(MARKET_DIR, "public", "packages", cat_id, f"{p_id}.zip"))

            sha256_hash = compute_sha256(pkg_zip_path)
            archive_url = f"{BASE_DOWNLOAD_URL}/packages/{cat_id}/{p_id}.zip"

            entry = {
                "id": p_id,
                "type": cat["type"],
                "name": name,
                "version": version,
                "description": description,
                "author": author,
                "repo": f"rlnunez/{repo_name}",
                "tier": cat["tier"],
                "archive_url": archive_url,
                "sha256": sha256_hash,
                "min_core_version": "0.11.0",
                "recommended_bundle": True,
                "readme": readme_text,
                "readme_url": f"https://github.com/rlnunez/{repo_name}/tree/main/plugins/{p_dir}#readme"
            }
            all_catalog_entries.append(entry)

    # Sort catalog entries by category and name
    all_catalog_entries.sort(key=lambda x: (x["type"], x["name"].lower()))

    # Compile canonical index.json
    catalog_data = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_available": len(all_catalog_entries),
        "plugins": all_catalog_entries
    }

    # Write index.json to openoptout-market
    with open(os.path.join(MARKET_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, indent=2)

    with open(os.path.join(MARKET_DIR, "public", "index.json"), "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, indent=2)

    # Update plugins.json registry summary
    registry_summary = []
    for p in all_catalog_entries:
        registry_summary.append({
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "category": p["type"],
            "tier": p["tier"],
            "author": p["author"],
            "repo": p["repo"],
            "version": p["version"],
            "archive_url": p["archive_url"],
            "sha256": p["sha256"]
        })

    with open(os.path.join(MARKET_DIR, "plugins.json"), "w", encoding="utf-8") as f:
        json.dump(registry_summary, f, indent=2)

    print(f"[+] Complete: staged 5 category repositories under {REPOS_DIR}")
    print(f"[+] Total catalog plugins compiled: {len(all_catalog_entries)}")


if __name__ == "__main__":
    main()
