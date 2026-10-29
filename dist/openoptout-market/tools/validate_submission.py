#!/usr/bin/env python3
"""
Validates community plugin submissions in plugins.json.
Runs in GitHub Actions when contributors open a Pull Request.
Zero external dependencies (Python standard library only).
"""

import json
import os
import re
import sys

ALLOWED_CATEGORIES = {"brokers", "captcha", "email", "languages", "themes"}
ID_REGEX = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
REPO_REGEX = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def validate_plugins_json(file_path: str) -> list[str]:
    errors = []
    if not os.path.isfile(file_path):
        return [f"File not found: {file_path}"]

    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        return [f"Invalid JSON syntax in {file_path}: {e}"]

    if not isinstance(data, list):
        return ["Root of plugins.json must be a JSON array of plugin objects."]

    seen_ids = set()

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"Entry [{idx}] must be a JSON object.")
            continue

        p_id = item.get("id")
        name = item.get("name")
        desc = item.get("description")
        repo = item.get("repo")
        category = item.get("category")
        tier = item.get("tier", 2)

        # Check required fields
        for field, val in [("id", p_id), ("name", name), ("description", desc), ("repo", repo), ("category", category)]:
            if not val or not str(val).strip():
                errors.append(f"Entry [{idx}] is missing required field '{field}'.")

        if p_id:
            if not ID_REGEX.match(p_id):
                errors.append(
                    f"Entry [{idx}] id '{p_id}' is invalid. "
                    "Must be lowercase alphanumeric, dashes, or underscores (2-64 chars)."
                )
            if p_id in seen_ids:
                errors.append(f"Duplicate plugin id '{p_id}' found at index {idx}.")
            seen_ids.add(p_id)

        if repo and not REPO_REGEX.match(repo):
            errors.append(f"Entry [{idx}] repo '{repo}' is invalid. Must be in 'owner/repository' format.")

        if category and category not in ALLOWED_CATEGORIES:
            errors.append(
                f"Entry [{idx}] category '{category}' is invalid. Allowed: {sorted(ALLOWED_CATEGORIES)}"
            )

        if tier not in {1, 2, 3}:
            errors.append(f"Entry [{idx}] tier must be 1, 2, or 3 (got {tier}).")

    return errors


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "plugins.json"
    errors = validate_plugins_json(target)
    if errors:
        print(f"❌ Validation failed for {target}:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"✅ {target} is valid and ready for catalog indexing.")
        sys.exit(0)


if __name__ == "__main__":
    main()

