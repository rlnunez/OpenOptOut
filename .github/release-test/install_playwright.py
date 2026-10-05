#!/usr/bin/env python3
"""Install Playwright and browser binaries for test run."""
import os
import re
import shlex
import subprocess
import sys


def main() -> None:
    raw = os.environ.get("PLAYWRIGHT_VERSION", "").strip()
    ver = raw if re.match(r"^[0-9A-Za-z_.\-]+$", raw) else ""
    pkg = shlex.quote(f"playwright=={ver}") if ver else "playwright"

    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", pkg],
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"],
        stdout=subprocess.DEVNULL,
        check=True,
    )


if __name__ == "__main__":
    main()
