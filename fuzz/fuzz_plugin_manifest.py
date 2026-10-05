#!/usr/bin/env python3
"""Fuzz target: plugin manifest.json files.

Every uploaded or installed plugin carries a manifest.json, which is untrusted.
plugins.layout._inspect() reads and validates it and is supposed to return a
FoundPlugin with errors for anything malformed. An exception escaping it is a
bug: it would break plugin scanning (and the Plugins page) for every plugin.
"""
import json
import os
import sys
import tempfile

import atheris

import _bootstrap  # noqa: F401
from _bootstrap import json_value, keyed_dict

with atheris.instrument_imports():
    from app.plugins.permissions import PLUGIN_TYPES
    from app.plugins import layout

KEYS = ["id", "name", "version", "author", "description", "api_version", "type",
        "permissions", "hooks", "methods", "events", "outbound_domains", "entrypoint",
        "max_memory_mb", "max_cpu_seconds", "timeout_seconds",
        "requires_pii_network_exception", "pii_network_justification", "spec_file",
        "broker_id", "captcha_plugin_id", "is_property_broker", "difficulty"]
TYPES = sorted(PLUGIN_TYPES) + [""]

_dir = tempfile.mkdtemp(prefix="fuzz-manifest-")
_path = os.path.join(_dir, "manifest.json")


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    if fdp.ConsumeIntInRange(0, 9) == 0:
        manifest = json_value(fdp)
    else:
        manifest = keyed_dict(fdp, KEYS)
        if fdp.ConsumeBool():
            manifest["type"] = fdp.PickValueInList(TYPES)
    folder_type = fdp.PickValueInList(TYPES[:-1] + [None])
    try:
        text = json.dumps(manifest)
    except (TypeError, ValueError):
        return
    with open(_path, "w", encoding="utf-8") as f:
        f.write(text)

    found = layout._inspect(_dir, folder_type)                # must never raise
    if found.manifest is not None:
        found.manifest.to_dict()
        _ = found.manifest.effective_type, found.manifest.is_data_only, found.valid


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
