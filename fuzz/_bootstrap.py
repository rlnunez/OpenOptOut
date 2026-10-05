"""Shared setup for the fuzz targets in this folder.

Puts the backend package (built by fuzz/build_pkgroot.sh, or by
.clusterfuzzlite/build.sh in CI) on sys.path so targets can
`import app.<module>` the same way the running server does.
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.environ.get("OPENOPTOUT_PKGROOT", os.path.join(_here, ".pkgroot"))
if os.path.isdir(_root) and _root not in sys.path:
    sys.path.insert(0, _root)

# Keep the code under test away from any real settings / data on this machine.
os.environ.setdefault("SETTINGS_FILE", os.path.join(_here, ".nonexistent-settings.json"))
os.environ.setdefault("SECRET_KEY", "fuzzing-only-not-a-secret")


def json_value(fdp, depth=0):
    """Build a random JSON-like value (dict/list/str/int/float/bool/None).

    Structured input reaches much deeper into parsers than random bytes do,
    because it gets past the "is this valid JSON / a dict" checks.
    """
    kind = fdp.ConsumeIntInRange(0, 7 if depth < 4 else 4)
    if kind == 0:
        return None
    if kind == 1:
        return fdp.ConsumeBool()
    if kind == 2:
        return fdp.ConsumeInt(4)
    if kind == 3:
        return fdp.ConsumeRegularFloat()
    if kind == 4:
        return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 40))
    if kind == 5:
        return [json_value(fdp, depth + 1) for _ in range(fdp.ConsumeIntInRange(0, 4))]
    # 6, 7: dicts — the common case for configs
    return {fdp.ConsumeUnicodeNoSurrogates(12): json_value(fdp, depth + 1)
            for _ in range(fdp.ConsumeIntInRange(0, 5))}


def keyed_dict(fdp, keys, depth=0):
    """A dict that uses real field names (so the parser actually reads them)
    with random values of random types."""
    out = {}
    for k in keys:
        if fdp.ConsumeBool():
            out[k] = json_value(fdp, depth + 1)
    return out
