#!/usr/bin/env python3
"""Install workflow analysis tools (zizmor, actionlint)."""
import os
import subprocess
import sys


def main() -> None:
    zizmor_version = os.environ.get("ZIZMOR_VERSION", "")
    actionlint_py_version = os.environ.get("ACTIONLINT_PY_VERSION", "")

    zizmor_pkg = f"zizmor=={zizmor_version}" if zizmor_version else "zizmor"
    actionlint_pkg = f"actionlint-py=={actionlint_py_version}" if actionlint_py_version else "actionlint-py"

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        zizmor_pkg,
        actionlint_pkg,
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
