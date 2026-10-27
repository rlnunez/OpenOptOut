#!/usr/bin/env python3
"""
Standalone Data Broker Plugin Validator.

Verifies plugin manifest and declarative spec JSON files against schema,
consistency, security invariants, and anti-brittle guidelines.
Works completely standalone with Python standard library (no external packages).

Usage:
    python3 validate.py <path-to-plugin-folder>
"""

import json
import os
import sys

KNOWN_FIELDS = {
    "first_name", "last_name", "full_name", "formal_name",
    "email", "phone", "address", "city", "state", "zip",
    "age", "dob", "relatives", "dob_iso", "birth_month", "birth_day",
    "age_range", "contact_email", "listing_url", "street", "state_name",
    "birth_year", "phone_digits", "phone_e164", "phone_dashed",
    "all_phones", "all_emails",
}

PROHIBITED_FIELDS = {
    "ssn", "social_security_number", "passport", "driver_license",
    "id_card", "government_id", "password", "upload", "file_upload"
}

STEP_KINDS = {
    "navigate", "fill", "type", "select", "check", "click",
    "click_matching", "press", "frame", "scroll", "wait_for",
    "wait", "submit", "expect_success", "solve_captcha",
    "autofill", "pick_listing", "pause_for_human",
}

VALID_METHODS = {"form", "email", "manual"}


def validate_plugin(plugin_dir: str) -> list[str]:
    errors = []
    plugin_dir = os.path.abspath(plugin_dir)
    folder_name = os.path.basename(plugin_dir)

    # 1. Required files
    manifest_path = os.path.join(plugin_dir, "manifest.json")
    spec_path = os.path.join(plugin_dir, "spec.json")
    readme_path = os.path.join(plugin_dir, "README.md")

    for f, p in [("manifest.json", manifest_path), ("spec.json", spec_path), ("README.md", readme_path)]:
        if not os.path.isfile(p):
            errors.append(f"Missing required file: {f}")

    if errors:
        return errors

    # 2. Parse manifest.json
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except Exception as e:
        return [f"Failed to parse manifest.json: {e}"]

    # 3. Parse spec.json
    try:
        with open(spec_path, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
    except Exception as e:
        return [f"Failed to parse spec.json: {e}"]

    # 4. Identifier consistency
    manifest_id = manifest.get("id")
    broker_id = manifest.get("broker_id")
    spec_broker_id = spec.get("broker_id")

    if not manifest_id:
        errors.append("manifest.json missing 'id'")
    if not broker_id:
        errors.append("manifest.json missing 'broker_id'")
    if not spec_broker_id:
        errors.append("spec.json missing 'broker_id'")

    if manifest_id and broker_id and spec_broker_id:
        if not (manifest_id == broker_id == spec_broker_id):
            errors.append(
                f"ID mismatch: manifest.id='{manifest_id}', manifest.broker_id='{broker_id}', "
                f"spec.broker_id='{spec_broker_id}' must all match"
            )

    if manifest.get("type") != "brokers":
        errors.append(f"manifest.type must be 'brokers', got '{manifest.get('type')}'")

    if not manifest.get("version"):
        errors.append("manifest.json missing 'version'")

    # 5. Spec Validation
    method = spec.get("method")
    if method not in VALID_METHODS:
        errors.append(f"spec.method must be one of {sorted(VALID_METHODS)}, got '{method}'")

    source = str(spec.get("source", "")).strip()
    if not source:
        errors.append("spec.source is required: document the origin/research citation for this opt-out flow")

    requires = spec.get("requires", [])
    if not isinstance(requires, list):
        errors.append("spec.requires must be an array of strings")
        requires = []

    steps = spec.get("steps", [])
    if method == "form" and not steps:
        errors.append("spec with method='form' must define at least one step in 'steps'")

    instructions = str(spec.get("instructions", "")).strip()
    if method == "manual" and len(instructions) < 40:
        errors.append("manual broker plugin requires detailed 'instructions' (minimum 40 characters)")

    # 6. Step inspections
    uses_fields = set()
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"step[{idx}] must be an object")
            continue

        kind = step.get("kind")
        if kind not in STEP_KINDS:
            errors.append(f"step[{idx}] kind '{kind}' is unknown. Allowed kinds: {sorted(STEP_KINDS)}")

        field = step.get("field")
        if field:
            uses_fields.add(field)
            if field in PROHIBITED_FIELDS:
                errors.append(
                    f"step[{idx}] references prohibited sensitive credential '{field}'. "
                    f"SSNs, government IDs, and passwords must never be automated."
                )
            elif field not in KNOWN_FIELDS:
                errors.append(f"step[{idx}] field '{field}' is unknown. Allowed fields: {sorted(KNOWN_FIELDS)}")

        if kind == "pause_for_human":
            text = str(step.get("text", "")).strip()
            if len(text) < 20:
                errors.append(
                    f"step[{idx}] pause_for_human text '{text}' is too short (min 20 chars). "
                    f"Explain plainly what the user needs to do."
                )

        # Check for overly brittle selectors
        selector = step.get("selector", "")
        if selector and isinstance(selector, str):
            if ":nth-child(" in selector and selector.count(">") > 2:
                errors.append(
                    f"step[{idx}] selector '{selector}' looks brittle. "
                    f"Use semantic attributes like [name=...], [aria-label=...], or button text."
                )

    # 7. Requirement synchronization
    if "listing_url" in uses_fields and "listing_url" not in requires:
        errors.append("A step references 'listing_url'; 'listing_url' must be listed in spec.requires")

    if "email_confirmation" in requires and "contact_email" not in uses_fields and "{contact_email}" not in instructions:
        errors.append(
            "spec.requires includes 'email_confirmation', but 'contact_email' is never used in steps or instructions. "
            "contact_email is required so confirmations can be matched."
        )

    return errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate.py <path-to-plugin-folder>", file=sys.stderr)
        sys.exit(1)

    target_dir = sys.argv[1]
    if not os.path.isdir(target_dir):
        print(f"Error: '{target_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    errors = validate_plugin(target_dir)
    if errors:
        print(f"❌ Validation failed for '{target_dir}':")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print(f"✅ Plugin '{target_dir}' passed all validation and safety checks.")
        sys.exit(0)


if __name__ == "__main__":
    main()

