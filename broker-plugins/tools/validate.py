#!/usr/bin/env python3
"""
Validate every broker plugin in broker-plugins/.

Runs the app's own manifest and spec validators (the same checks an upload
goes through), then the repo rules from broker-plugins/README.md. Folders
starting with "_" (the template) are skipped. Exits non-zero on any error.

    python broker-plugins/tools/validate.py [plugin-folder ...]
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGINS_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(PLUGINS_DIR)
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
    return errs


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
