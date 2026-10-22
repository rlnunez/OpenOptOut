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
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
    subprocess.run(pip_cmd + ["-r", str(req_file)], check=True)

    sync_pip_certifi()

    with_encryption = os.getenv("WITH_ENCRYPTION", "true").lower()
    if with_encryption != "false" and enc_file.exists():
        # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
        res = subprocess.run(pip_cmd + ["-r", str(enc_file)])
        if res.returncode != 0:
            print("WARN: sqlcipher3 install failed for this platform — continuing without file-level encryption")
        else:
            print("SQLCipher installed successfully — whole-database encryption enabled by default")
    else:
        print("SQLCipher disabled (WITH_ENCRYPTION=false) — file-level encryption disabled")


def sync_pip_certifi() -> None:
    """
    Ensure pip's internal vendored certifi copy matches the patched certifi
    package (2026.10.19+) to prevent container scanners (Trivy, etc.) from
    flagging pip's internal build-time certifi bundle with GHSA-6q48-6c7w-9gw2.
    """
    try:
        import re
        import certifi
        import pip._vendor.certifi as pip_certifi

        certifi_dir = Path(certifi.__file__).resolve().parent
        vendor_dir = Path(pip_certifi.__file__).resolve().parent

        for fname in ["cacert.pem", "__init__.py"]:
            src = certifi_dir / fname
            dst = vendor_dir / fname
            if src.exists() and dst.exists():
                dst.write_bytes(src.read_bytes())

        vendor_txt = vendor_dir.parent / "vendor.txt"
        if vendor_txt.exists():
            content = vendor_txt.read_text(encoding="utf-8")
            target_version = getattr(certifi, "__version__", "2026.10.19")
            content = re.sub(r"certifi==[^\s]+", f"certifi=={target_version}", content)
            vendor_txt.write_text(content, encoding="utf-8")
    except Exception as exc:
        print(f"Note: pip certifi sync skipped: {exc}")


if __name__ == "__main__":
    main()
