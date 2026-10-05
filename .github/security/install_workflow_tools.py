#!/usr/bin/env python3
"""Install workflow analysis tools (zizmor, actionlint)."""
import os
import re
import shlex
import subprocess
import sys


def _clean_pkg(name: str, env_var: str, default_ver: str) -> str:
    raw = os.environ.get(env_var, default_ver).strip()
    # Validate strictly alphanumeric with dots/hyphens (semantic version)
    ver = raw if re.match(r"^[0-9A-Za-z_.\-]+$", raw) else default_ver
    return shlex.quote(f"{name}=={ver}")


def main() -> None:
    zizmor_pkg = _clean_pkg("zizmor", "ZIZMOR_VERSION", "1.30.1")
    actionlint_pkg = _clean_pkg("actionlint-py", "ACTIONLINT_PY_VERSION", "1.7.12.25")

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        zizmor_pkg,
        actionlint_pkg,
    ]
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
