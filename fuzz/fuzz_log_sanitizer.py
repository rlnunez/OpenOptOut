#!/usr/bin/env python3
"""Fuzz target: the log sanitizer that scrubs credentials before logs hit disk.

sanitize_log_message() runs on every log line. Checked properties:
  - it never crashes, whatever the text
  - it never takes pathologically long (catastrophic regex backtracking would
    let one crafted log line freeze the server — atheris reports a timeout)
  - a bearer token embedded in surrounding random text never survives
"""
import string
import sys

import atheris

import _bootstrap  # noqa: F401

with atheris.instrument_imports():
    from app.core.logging_config import sanitize_log_message

TOKEN_CHARS = string.ascii_letters + string.digits + "-_."


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    before = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 200))
    after = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 200))

    # 1. arbitrary text
    out = sanitize_log_message(before + after)
    assert isinstance(out, str)

    # 2. a real-looking bearer token must be removed
    n = fdp.ConsumeIntInRange(16, 64)
    token = "".join(TOKEN_CHARS[b % len(TOKEN_CHARS)] for b in fdp.ConsumeBytes(n))
    if len(token) < 16 or not any(c.isalnum() for c in token) or token in before + after:
        return                                   # (token text also in the noise: can't tell)
    sep = fdp.PickValueInList([" ", "\n", ": ", "=", "\t", "\"", "'"])
    line = f"{before}{sep}Authorization: Bearer {token}{sep}{after}"
    out = sanitize_log_message(line)
    assert token not in out, f"bearer token survived sanitizing: {out!r}"


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
