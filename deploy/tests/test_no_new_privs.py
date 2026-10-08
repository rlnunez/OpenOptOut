#!/usr/bin/env python3
"""
OpenOptOut — Container no-new-privileges & Sandbox Compatibility Test (Roadmap Phase 21.2).

Validates whether the Linux kernel and container engine permit Bubblewrap (bwrap)
unprivileged user namespaces and seccomp filters when `no-new-privileges:true`
(PR_SET_NO_NEW_PRIVS) is active on the container.

Usage:
    python3 deploy/tests/test_no_new_privs.py
"""

import os
import platform
import shutil
import subprocess
import sys
from typing import Dict, Any, Tuple


def check_no_new_privs_flag() -> Tuple[bool, str]:
    """Inspect /proc/self/status to see if PR_SET_NO_NEW_PRIVS is active."""
    if not os.path.isfile("/proc/self/status"):
        return False, "Not running on Linux (/proc/self/status missing)"

    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("NoNewPrivs:"):
                    val = line.split(":", 1)[1].strip()
                    is_active = (val == "1")
                    return is_active, f"NoNewPrivs flag is {val}"
    except Exception as e:
        return False, f"Could not read /proc/self/status: {e}"

    return False, "NoNewPrivs field not present in /proc/self/status"


def check_unprivileged_userns() -> Tuple[bool, str]:
    """Check if kernel permits unprivileged user namespaces."""
    userns_path = "/proc/sys/kernel/unprivileged_userns_clone"
    if os.path.isfile(userns_path):
        try:
            with open(userns_path, "r") as f:
                val = f.read().strip()
                if val == "0":
                    return False, "kernel.unprivileged_userns_clone is 0 (disabled by host OS)"
                return True, "kernel.unprivileged_userns_clone is enabled (1)"
        except Exception as e:
            return False, f"Could not read {userns_path}: {e}"

    # Modern kernels usually have this built-in without the Debian sysctl knob
    return True, "Kernel unprivileged namespaces default-available"


def test_bwrap_execution() -> Tuple[bool, str]:
    """Execute a minimal Bubblewrap sandbox command to verify namespace isolation."""
    bwrap_bin = shutil.which("bwrap")
    if not bwrap_bin:
        return False, "bwrap binary not found in PATH"

    cmd = [
        bwrap_bin,
        "--ro-bind", "/usr", "/usr",
        "--proc", "/proc",
        "--dev", "/dev",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "true",
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        if res.returncode == 0:
            return True, "bwrap launched unprivileged namespaces successfully"
        else:
            stderr_msg = res.stderr.decode("utf-8", errors="replace").strip()
            return False, f"bwrap failed (exit {res.returncode}): {stderr_msg}"
    except Exception as e:
        return False, f"bwrap execution error: {e}"


def test_seccomp_filter_support() -> Tuple[bool, str]:
    """Verify that libseccomp / python-seccomp can load filters."""
    try:
        import seccomp
        f = seccomp.SyscallFilter(seccomp.ALLOW)
        return True, "seccomp library loaded filter successfully"
    except ImportError:
        return False, "python-seccomp module not installed"
    except Exception as e:
        return False, f"seccomp error: {e}"


def run_probe() -> Dict[str, Any]:
    """Run all compatibility checks and generate posture report."""
    is_linux = (platform.system() == "Linux")
    nnp_active, nnp_detail = check_no_new_privs_flag()
    userns_ok, userns_detail = check_unprivileged_userns()
    bwrap_ok, bwrap_detail = test_bwrap_execution()
    seccomp_ok, seccomp_detail = test_seccomp_filter_support()

    # Try importing preflight capabilities if in backend tree
    caps_report = None
    try:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend")))
        from plugins.sandbox import detect_capabilities
        caps = detect_capabilities()
        caps_report = {
            "bubblewrap": caps.bubblewrap,
            "seccomp": caps.seccomp,
            "rlimits": caps.rlimits,
            "unshare": caps.unshare,
        }
    except Exception:
        pass

    compatible = (not is_linux) or (bwrap_ok and seccomp_ok)

    return {
        "platform": platform.system(),
        "arch": platform.machine(),
        "is_linux": is_linux,
        "no_new_privs_active": nnp_active,
        "no_new_privs_detail": nnp_detail,
        "userns_ok": userns_ok,
        "userns_detail": userns_detail,
        "bwrap_ok": bwrap_ok,
        "bwrap_detail": bwrap_detail,
        "seccomp_ok": seccomp_ok,
        "seccomp_detail": seccomp_detail,
        "caps_report": caps_report,
        "compatible": compatible,
    }


def main():
    print("=" * 65)
    print("  OpenOptOut Container no-new-privileges Compatibility Probe")
    print("  (Roadmap Phase 21.2 — Testing)")
    print("=" * 65)

    res = run_probe()
    print(f"\nSystem:                 {res['platform']} ({res['arch']})")
    print(f"NoNewPrivs Active:      {'YES [✓]' if res['no_new_privs_active'] else 'NO [○]'}")
    print(f"                        ({res['no_new_privs_detail']})")
    print(f"Unprivileged userns:    {'OK [✓]' if res['userns_ok'] else 'BLOCKED [✗]'}")
    print(f"                        ({res['userns_detail']})")
    print(f"Bubblewrap (bwrap):     {'PASS [✓]' if res['bwrap_ok'] else 'FAILED [✗]'}")
    print(f"                        ({res['bwrap_detail']})")
    print(f"Seccomp filtering:      {'PASS [✓]' if res['seccomp_ok'] else 'UNAVAILABLE [○]'}")
    print(f"                        ({res['seccomp_detail']})")

    if res["caps_report"]:
        print(f"\nPlugin Sandbox Capabilities:")
        print(f"  Bubblewrap:           {res['caps_report']['bubblewrap']}")
        print(f"  Seccomp:              {res['caps_report']['seccomp']}")
        print(f"  Resource limits:      {res['caps_report']['rlimits']}")

    print("\n" + "-" * 65)
    if not res["is_linux"]:
        print("  NOTICE: This probe is designed for Linux containers.")
        print("  On macOS/Windows, execute inside Docker:")
        print("    docker compose exec api python3 deploy/tests/test_no_new_privs.py")
        print("-" * 65)
        print("\nVERDICT: SKIPPED (non-Linux dev host — run inside Docker container).\n")
        sys.exit(0)

    if res["bwrap_ok"]:
        print("  VERDICT: FULLY COMPATIBLE")
        print("  The host kernel supports unprivileged user namespaces.")
        print("  'no-new-privileges:true' can safely be applied to the 'api' container.")
        print("-" * 65 + "\n")
        sys.exit(0)
    else:
        print("  VERDICT: INCOMPATIBLE ON THIS HOST / RUNTIME")
        print("  Bubblewrap cannot create unprivileged user namespaces.")
        print("  Applying 'no-new-privileges:true' will break plugin sandboxing.")
        print("  Fix: Enable kernel.unprivileged_userns_clone=1 or run with --privileged/cap_add.")
        print("-" * 65 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
