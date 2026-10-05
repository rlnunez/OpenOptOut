#!/usr/bin/env python3
"""Install security scanners (Semgrep, Bandit)."""
import os
import subprocess
import sys


def main() -> None:
    semgrep_version = os.environ.get("SEMGREP_VERSION", "")
    bandit_version = os.environ.get("BANDIT_VERSION", "")

    semgrep_pkg = f"semgrep=={semgrep_version}" if semgrep_version else "semgrep"
    bandit_pkg = f"bandit[sarif]=={bandit_version}" if bandit_version else "bandit[sarif]"

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        semgrep_pkg,
        bandit_pkg,
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
