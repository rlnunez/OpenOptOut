#!/usr/bin/env python3
"""Install security scanners (Semgrep, Bandit)."""
import os
import re
import shlex
import subprocess
import sys


def _clean_pkg(name: str, env_var: str, default_ver: str) -> str:
    raw = os.environ.get(env_var, default_ver).strip()
    ver = raw if re.match(r"^[0-9A-Za-z_.\-]+$", raw) else default_ver
    return shlex.quote(f"{name}=={ver}")


def main() -> None:
    semgrep_pkg = _clean_pkg("semgrep", "SEMGREP_VERSION", "1.178.0")
    bandit_pkg = _clean_pkg("bandit[sarif]", "BANDIT_VERSION", "1.9.4")

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        semgrep_pkg,
        bandit_pkg,
    ]
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
