#!/usr/bin/env python3
"""Fuzz target: the name cleaner every sign-up and family-member name passes through.

clean_name() / clean_name_lenient() (backend/core/text_input.py) take whatever
a person types, or whatever a sign-in provider sends. Checked properties:
  - neither ever crashes with anything but the documented ValueError
  - the result is always storable: encodes as UTF-8, contains no NUL or other
    control character and no text-reordering mark (PostgreSQL rejects NUL, and
    reordering marks let a name display as something it isn't)
  - the result never exceeds MAX_NAME_CHARS and has no leading/trailing space
  - cleaning is idempotent: cleaning a cleaned name changes nothing
"""
import sys
import unicodedata

import atheris

import _bootstrap  # noqa: F401

with atheris.instrument_imports():
    from app.core.text_input import (
        MAX_NAME_CHARS, _BIDI_CONTROLS, clean_name, clean_name_lenient,
    )


def _assert_storable(out: str):
    out.encode("utf-8")                                      # no lone surrogates
    assert len(out) <= MAX_NAME_CHARS, len(out)
    assert out == out.strip(), repr(out)
    for ch in out:
        assert unicodedata.category(ch) not in ("Cc", "Cs"), f"control char {ch!r} in {out!r}"
        assert ch not in _BIDI_CONTROLS and ch != "\ufeff", f"reordering mark {ch!r} in {out!r}"


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    raw = fdp.ConsumeUnicode(fdp.ConsumeIntInRange(0, MAX_NAME_CHARS * 2))

    try:
        out = clean_name(raw)
    except ValueError:
        out = None                                           # empty or too long: documented
    if out is not None:
        _assert_storable(out)
        assert clean_name(out) == out, "clean_name is not idempotent"

    lenient = clean_name_lenient(raw, fallback="fallback@example.invalid")
    _assert_storable(lenient)
    assert lenient, "lenient cleaning returned nothing despite a fallback"


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
