#!/usr/bin/env python3
"""
Install backend Python dependencies and optional SQLCipher encryption.
"""
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    req_file = base_dir / "requirements.txt"
    enc_file = base_dir / "requirements-encryption.txt"

    pip_cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir"]
    subprocess.run(pip_cmd + ["-r", str(req_file)], check=True)

    with_encryption = os.getenv("WITH_ENCRYPTION", "false").lower()
    if with_encryption == "true" and enc_file.exists():
        res = subprocess.run(pip_cmd + ["-r", str(enc_file)])
        if res.returncode != 0:
            print("WARN: sqlcipher3 install failed for this platform — continuing without file-level encryption")
    else:
        print("SQLCipher not requested (WITH_ENCRYPTION=false) — file-level encryption disabled")


if __name__ == "__main__":
    main()
