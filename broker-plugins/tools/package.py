#!/usr/bin/env python3
"""
Build one upload-ready zip per valid built-in broker plugin into
broker-plugins/dist/ (for installing a newer version on an existing server).

    python broker-plugins/tools/package.py [plugin-folder ...]
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

from validate import check, main as validate_all, PLUGINS_DIR, KIT_DIR  # noqa: E402
from backend.plugins.broker_addon import package_broker_addon  # noqa: E402


def main(argv):
    if validate_all(argv) != 0:
        print("Fix the errors above before packaging.")
        return 1
    folders = argv or sorted(
        d for d in os.listdir(PLUGINS_DIR)
        if os.path.isdir(os.path.join(PLUGINS_DIR, d))
        and not d.startswith(("_", ".")) and d not in ("tools", "dist"))
    dist = os.path.join(KIT_DIR, "dist")
    for folder in folders:
        path = os.path.join(PLUGINS_DIR, folder)
        with open(os.path.join(path, "manifest.json"), encoding="utf-8") as fh:
            version = json.load(fh).get("version", "0")
        out = package_broker_addon(path, os.path.join(dist, f"{folder}-{version}.zip"))
        print(f"built {os.path.relpath(out, KIT_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
