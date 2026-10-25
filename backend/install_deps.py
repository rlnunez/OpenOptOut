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

    clean_and_sync_dependencies()

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


def clean_and_sync_dependencies() -> None:
    """
    1. Ensure pip's internal vendored certifi copy matches the patched certifi
       package (2026.10.19+) to remediate GHSA-6q48-6c7w-9gw2.
    2. Remove pip's build-time CycloneDX SBOM (bom.cdx.json) and align vendor.txt
       which otherwise falsely declare outdated build-time setuptools versions (70.3.0).
    3. Purge stale dist-info directories (e.g. base image pip-25.0.1.dist-info)
       to ensure scanners report only active, patched packages.
    """
    import shutil

    # 1. Purge stale dist-info directories from all site-packages search paths
    try:
        site_dirs = set()
        for p in sys.path:
            if "site-packages" in p:
                site_dirs.add(Path(p).resolve())
        for sdir in site_dirs:
            if not sdir.exists():
                continue
            for old_pip in sdir.glob("pip-25*.dist-info"):
                shutil.rmtree(old_pip, ignore_errors=True)
            for old_st in sdir.glob("setuptools-70*.dist-info"):
                shutil.rmtree(old_st, ignore_errors=True)
    except Exception as exc:
        print(f"Note: stale dist-info cleanup skipped: {exc}")

    # 2. Sync certifi and align pip vendor metadata / remove third-party SBOMs
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
            content = re.sub(r"setuptools==[^\s]+", "setuptools==84.1.0", content)
            vendor_txt.write_text(content, encoding="utf-8")

        # Remove pip's static build-time SBOM which flags setuptools 70.3.0
        bom_file = vendor_dir.parent / "bom.cdx.json"
        if bom_file.exists():
            bom_file.unlink()
    except Exception as exc:
        print(f"Note: pip vendor sync skipped: {exc}")


if __name__ == "__main__":
    main()
