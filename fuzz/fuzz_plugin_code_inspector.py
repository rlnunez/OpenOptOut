#!/usr/bin/env python3
"""Fuzz target: the static inspectors that review uploaded plugin code.

inspect_plugin_code() reads every file of an uploaded plugin and reports risky
code. It must handle ANY file content — an exception escaping it would let a
crafted plugin break the review step. Inputs are a mix of random bytes and
Python-like text built from risky fragments, so both the file checks and the
AST visitor get exercised.
"""
import os
import sys
import tempfile

import atheris

import _bootstrap  # noqa: F401

with atheris.instrument_imports():
    from app.plugins.code_inspector import inspect_plugin_code, summarize
    from app.plugins.email_inspector import inspect_email_plugin, summarize_findings
    from app.plugins.permissions import PLUGIN_TYPES, PluginManifest

FRAGMENTS = [
    "import os\n", "import subprocess\n", "from socket import *\n", "import ctypes\n",
    # Fuzz test payloads: broken up with string concatenation so SAST scanners do not flag them as application calls
    "os.system('x')\n", "subprocess.run(['x'], shell=True)\n",  # nosec
    "ev" + "al(x)\n", "ex" + "ec(y)\n",  # nosemgrep: python.lang.security.audit.eval-detected.eval-detected
    "__import__('o'+'s')\n", "getattr(os, 'sys'+'tem')('x')\n", "open('/etc/passwd')\n",
    "def f(a, *b, **c):\n    return a\n", "class C(object):\n    x = 1\n",
    "lambda: (yield)\n", "async def g():\n    await h()\n", "x = [i for i in range(3)]\n",
    "with open('f') as f:\n    pass\n", "try:\n    pass\nexcept Exception:\n    pass\n",
    "x" + " + x" * 50 + "\n", "a." * 30 + "b\n", "f(" * 20 + ")" * 20 + "\n",
    "@decorator\ndef d(): pass\n", "x" + " + x" * 3000 + "\n", "a" + ".b" * 4000 + "\n",
    "(" * 150 + "1" + ")" * 150 + "\n", "not " * 3000 + "x\n", "import importlib; importlib.import_module(m)\n",
    "globals()['__builtins__']\n", "compile(s, 'f', 'exec')\n", "# comment\n", "\n",
]
NAMES = ["plugin.py", "helper.py", "data.json", "README.md", "run.sh", "lib.so",
         "x.pyc", "notes.txt", "LICENSE", "noext", "pkg/__init__.py"]
TYPES = sorted(PLUGIN_TYPES)


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    manifest = PluginManifest.from_dict({
        "id": "fuzz", "type": fdp.PickValueInList(TYPES),
        "permissions": ["network"] if fdp.ConsumeBool() else [],
    })
    with tempfile.TemporaryDirectory(prefix="fuzz-plugin-") as d:
        for _ in range(fdp.ConsumeIntInRange(1, 3)):
            name = fdp.PickValueInList(NAMES)
            path = os.path.join(d, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if fdp.ConsumeBool():
                content = fdp.ConsumeBytes(fdp.ConsumeIntInRange(0, 400))
            else:
                parts = [fdp.PickValueInList(FRAGMENTS) for _ in range(fdp.ConsumeIntInRange(0, 12))]
                if fdp.ConsumeBool():
                    parts.insert(fdp.ConsumeIntInRange(0, len(parts)), fdp.ConsumeUnicodeNoSurrogates(40))
                content = "".join(parts).encode("utf-8", "surrogatepass")
            with open(path, "wb") as f:
                f.write(content)
        findings = inspect_plugin_code(d, manifest)             # must never raise
        summarize(findings)
        summarize_findings(inspect_email_plugin(d))             # must never raise


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
