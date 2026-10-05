#!/usr/bin/env python3
"""Fuzz target: signed job envelopes passed between the control plane and workers.

Envelopes travel through Redis, so anyone who can write to Redis can hand the
control plane or a worker arbitrary bytes. Two properties are checked:

1. Forgery: with a secret key set, from_json() must never accept an envelope
   whose contents differ from what was signed. A signed envelope is built,
   one field is changed, and the result must be rejected (or decode to exactly
   the original data).
2. Robustness: any garbage must be rejected with EnvelopeError (the module's
   own error type), not crash with an unrelated exception.
"""
import json
import sys

import atheris

import _bootstrap  # noqa: F401
from _bootstrap import json_value

with atheris.instrument_imports():
    from app.core.distributed.envelope import (EnvelopeError, JobEnvelope,
                                               JobResultEnvelope)

KEY = "fuzz-shared-secret"
FIELDS = ["envelope_id", "action", "priority", "created_at", "expires_at", "broker_id",
          "broker_name", "member_id", "request_id", "request_key", "payload",
          "encrypted_payload", "meta", "hmac_signature"]


def tamper_check(fdp):
    env = JobEnvelope(broker_id="broker-a", broker_name="Broker A", member_id="7",
                      request_id=42, payload={"full_name": "Example Person"},
                      meta={"attempt": 1}).sign(KEY)
    original = env.to_dict()
    d = dict(original)
    field = fdp.PickValueInList(FIELDS)
    d[field] = json_value(fdp)
    if d[field] == original.get(field):
        return
    try:
        raw = json.dumps(d)
    except (TypeError, ValueError):
        return
    try:
        got = JobEnvelope.from_json(raw, secret_key=KEY, verify_signature=True)
    except EnvelopeError:
        return                                   # rejected: good
    if field == "hmac_signature":
        raise AssertionError("envelope with a changed signature was accepted")
    accepted = got.to_dict()
    if accepted != original:
        raise AssertionError(f"tampered envelope accepted: {field!r} changed to {d[field]!r}")


def garbage_check(fdp):
    raw = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 300)) if fdp.ConsumeBool() \
        else json.dumps(json_value(fdp))
    for cls in (JobEnvelope, JobResultEnvelope):
        try:
            cls.from_json(raw, secret_key=KEY, verify_signature=True)
        except EnvelopeError:
            pass
        else:
            raise AssertionError("unsigned garbage accepted as a valid envelope")


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    if fdp.ConsumeBool():
        tamper_check(fdp)
    else:
        garbage_check(fdp)


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
