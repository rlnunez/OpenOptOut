#!/usr/bin/env python3
"""Fuzz target: declarative broker specs (broker add-on plugins).

A broker add-on's spec.json is untrusted input: it arrives inside an uploaded
plugin or an imported broker catalogue. validate_broker_spec_file() is the
boundary and is supposed to turn ANY bad file into a list of errors. An
exception escaping it is a bug (the upload fails with a 500 instead of a clear
message). A spec that passes validation must then compile into a job, or be
rejected with CompileError — nothing else.
"""
import json
import os
import sys
import tempfile

import atheris

import _bootstrap  # noqa: F401  (sets up sys.path)
from _bootstrap import json_value, keyed_dict

with atheris.instrument_imports():
    from app.core.interpreter.broker_spec import KNOWN_FIELDS, STEP_KINDS
    from app.core.interpreter.compiler import CompileError, compile_job
    from app.plugins.broker_addon import validate_broker_spec_file

TOP_KEYS = ["broker_id", "name", "method", "spec_version", "opt_out_url", "steps",
            "email", "success_selector", "success_text", "notes"]
STEP_KEYS = ["kind", "selector", "field", "value", "url", "text", "timeout_ms", "optional"]
EMAIL_KEYS = ["to_address", "subject_template", "body_template", "locale", "require_fields"]
METHODS = ["form", "email", "manual", "phone", "mail", ""]

_dir = tempfile.mkdtemp(prefix="fuzz-spec-")
_path = os.path.join(_dir, "spec.json")


def make_spec(fdp):
    """Mostly well-formed specs with random values, so validation code is reached."""
    if fdp.ConsumeIntInRange(0, 9) == 0:
        return json_value(fdp)                                 # anything at all
    spec = keyed_dict(fdp, TOP_KEYS)
    if fdp.ConsumeBool():
        spec["method"] = fdp.PickValueInList(METHODS)
    if fdp.ConsumeBool():
        steps = []
        for _ in range(fdp.ConsumeIntInRange(0, 6)):
            st = keyed_dict(fdp, STEP_KEYS)
            if fdp.ConsumeBool():
                st["kind"] = fdp.PickValueInList(sorted(STEP_KINDS))
            if fdp.ConsumeBool():
                st["field"] = fdp.PickValueInList(sorted(KNOWN_FIELDS))
            steps.append(st)
        spec["steps"] = steps
    if fdp.ConsumeBool():
        spec["email"] = keyed_dict(fdp, EMAIL_KEYS)
    return spec


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    spec = make_spec(fdp)
    member_fields = {k: fdp.ConsumeUnicodeNoSurrogates(30) for k in KNOWN_FIELDS if fdp.ConsumeBool()}
    try:
        text = json.dumps(spec)
    except (TypeError, ValueError):
        return
    with open(_path, "w", encoding="utf-8") as f:
        f.write(text)

    parsed, errors = validate_broker_spec_file(_dir)          # must never raise
    if parsed is None:
        assert errors, "rejected spec must say why"
        return
    parsed.to_dict()
    try:
        compile_job(parsed, member_fields, "member-1")
    except CompileError:
        pass


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
