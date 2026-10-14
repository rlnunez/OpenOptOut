#!/usr/bin/env python3
"""
Validate every built-in broker plugin (backend/plugins/bundled/brokers/).

Runs the app's own manifest and spec validators (the same checks an upload
goes through), then the repo rules from broker-plugins/README.md. Folders
starting with "_" (the template) are skipped. Exits non-zero on any error.

    python broker-plugins/tools/validate.py [plugin-folder ...]

Every plugin is also compiled for a made-up member and walked by the
dry-run executor, so a step that can't run is caught before it reaches a
live site.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT_DIR = os.path.dirname(HERE)                      # broker-plugins/ (template, tools, dist)
REPO_ROOT = os.path.dirname(KIT_DIR)
# The plugins themselves ship inside the app image, so they live with the
# other built-in plugins and are installed automatically at startup.
PLUGINS_DIR = os.path.join(REPO_ROOT, "backend", "plugins", "bundled", "brokers")
sys.path.insert(0, REPO_ROOT)

from backend.plugins.permissions import PluginManifest          # noqa: E402
from backend.plugins.broker_addon import validate_broker_spec_file  # noqa: E402


def check(folder: str) -> list:
    errs = []
    path = os.path.join(PLUGINS_DIR, folder)
    for f in ("manifest.json", "spec.json", "README.md"):
        if not os.path.isfile(os.path.join(path, f)):
            errs.append(f"missing {f}")
    if errs:
        return errs

    with open(os.path.join(path, "manifest.json"), encoding="utf-8") as fh:
        mdata = json.load(fh)
    manifest = PluginManifest.from_dict(mdata)
    errs += [f"manifest: {e}" for e in manifest.validate()]
    if manifest.effective_type != "brokers":
        errs.append(f"manifest: type must be 'brokers', not '{manifest.effective_type}'")

    spec, spec_errs = validate_broker_spec_file(path, manifest.spec_file or "spec.json")
    errs += [f"spec: {e}" for e in spec_errs]
    if not spec:
        return errs

    if not (folder == manifest.id == manifest.broker_id == spec.broker_id):
        errs.append(f"folder, manifest.id, manifest.broker_id and spec.broker_id must all be "
                    f"'{folder}' (got {manifest.id!r}, {manifest.broker_id!r}, {spec.broker_id!r})")
    if not spec.source.strip():
        errs.append("spec.source is required: say where the opt-out details came from")
    for i, s in enumerate(spec.steps):
        if s.kind == "pause_for_human" and len(s.text.strip()) < 20:
            errs.append(f"step[{i}] pause_for_human text is too short to tell a person what to do")
    from backend.core.interpreter.compiler import uses_field
    mentions = lambda f: uses_field(spec, f) or ("{" + f + "}") in spec.instructions
    if "email_confirmation" in spec.requires and not mentions("contact_email"):
        errs.append("requires email_confirmation, so the form's email box (or the instructions) must "
                    "use contact_email: that's how the confirmation is matched and clicked")
    if spec.method == "manual" and len(spec.instructions.strip()) < 40:
        errs.append("a manual broker needs instructions that tell a person exactly what to do")
    if mentions("listing_url") and "listing_url" not in spec.requires:
        errs.append("a step uses listing_url: add \"listing_url\" to requires")
    errs += [f"dry run: {e}" for e in dry_run(spec)]
    return errs


SAMPLE_MEMBER = {
    "first_name": "Jane", "last_name": "Sample", "full_name": "Jane Sample", "formal_name": "Jane Q Sample",
    "email": "jane@example.org", "contact_email": "jane+oosample01@example.org",
    "phone": "(512) 555-0100", "phone_digits": "5125550100", "address": "12 Oak St", "street": "12 Oak St",
    "city": "Austin", "state": "TX", "state_name": "Texas", "zip": "78701", "age": "40",
    "birth_year": "1986", "dob": "1986-01-02", "relatives": "John Sample",
    "listing_url": "https://www.example.com/listing/jane-sample",
}


def dry_run(spec) -> list:
    from backend.core.interpreter import compile_job, DryRunExecutor
    try:
        job = compile_job(spec, dict(SAMPLE_MEMBER), member_id="0")
    except Exception as e:
        return [f"doesn't compile: {e}"]
    res = DryRunExecutor().run(job)
    if not (res.ok or res.needs_manual or res.needs_captcha):
        return [res.detail]
    return []


def main(argv):
    folders = argv or sorted(
        d for d in os.listdir(PLUGINS_DIR)
        if os.path.isdir(os.path.join(PLUGINS_DIR, d))
        and not d.startswith(("_", ".")) and d not in ("tools", "dist"))
    failed = 0
    for folder in folders:
        errs = check(folder)
        if errs:
            failed += 1
            print(f"FAIL  {folder}")
            for e in errs:
                print(f"      - {e}")
        else:
            print(f"ok    {folder}")
    print(f"\n{len(folders) - failed} of {len(folders)} plugin(s) valid")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
