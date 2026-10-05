#!/usr/bin/env python3
"""Fuzz target: building opt-out / discovery combinations from Identity Vault data.

Names, addresses, phones and emails are typed in by users (or imported), so they
can contain anything. Every combination builder must cope with any values —
an exception here would stop discovery and opt-outs for that family member.
"""
import sys
from types import SimpleNamespace

import atheris

import _bootstrap  # noqa: F401

with atheris.instrument_imports():
    from app.core import combinations as C

KINDS = ["name", "address", "phone", "email", "other", ""]
ADDRESS_SHAPES = [
    "{a}", "{a}, {b}", "{a}, {b}, {c}", "{a}, {b}, {c} {d}", "{a},,{b},", ", , ,",
    "{a}, {b}, ZZ 00000", "{a}, {b}, ZZ 00000-1234", "{a}\n{b}, {c}",
]
BUILDERS = [C.build_discovery_combos, C.build_optout_combos,
            C.build_email_optout_combos, C.build_property_discovery_combos]


def text(fdp, n=40):
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, n))


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    identities = []
    for _ in range(fdp.ConsumeIntInRange(0, 10)):
        kind = fdp.PickValueInList(KINDS)
        if kind == "address" and fdp.ConsumeBool():
            value = fdp.PickValueInList(ADDRESS_SHAPES).format(
                a=text(fdp, 20), b=text(fdp, 15), c=text(fdp, 10), d=text(fdp, 10))
        else:
            value = text(fdp)
        identities.append(SimpleNamespace(
            kind=kind, value=value, is_primary=fdp.ConsumeBool(),
            is_deed=fdp.ConsumeBool(), is_mortgage=fdp.ConsumeBool()))
    member = SimpleNamespace(
        id=1, full_name=text(fdp, 30),
        formal_name=text(fdp, 30) if fdp.ConsumeBool() else None,
        identities=identities)

    C._parse_address(text(fdp, 80))
    for build in BUILDERS:
        for combo in build(member):                           # must never raise
            combo.label()
            combo.as_dict()


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
