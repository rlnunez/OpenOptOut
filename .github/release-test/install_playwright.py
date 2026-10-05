#!/usr/bin/env python3
"""Install Playwright and browser binaries for test run."""
import os
import subprocess
import sys


def main() -> None:
    playwright_version = os.environ.get("PLAYWRIGHT_VERSION", "")
    pkg = f"playwright=={playwright_version}" if playwright_version else "playwright"

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
