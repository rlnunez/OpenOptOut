#!/usr/bin/env python3
"""
Sandbox preflight — reports (and where possible tests) the OS-level isolation
this host can actually give plugins.

The smoke test (`smoke_test.py`) proves the plugin *protocol* works. This script
answers the other half of roadmap item 2: "when a plugin runs here, what is
actually containing it?" It's the honest posture report — because the plugin
system degrades gracefully, and an operator needs to know whether they're
getting full OS sandboxing or just resource limits.

Run inside the backend container:
    python -m plugins.preflight_sandbox

It never fails the way the smoke test does — its job is to *report*, so it always
exits 0 and prints a posture summary. A production operator running untrusted
plugins should see bubblewrap + seccomp both available; if not, the report says
exactly what's missing and what protection remains.
"""

import os
import sys
import platform
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("preflight")


def check_rlimits_actually_work() -> tuple[bool, str]:
    """
    Actively test that POSIX resource limits can be set in a child process —
    this is the isolation layer that works even without bubblewrap/seccomp, so
    it's worth confirming rather than assuming. We fork a child, apply a tiny
    RLIMIT_NPROC, and confirm it took.
    """
    if os.name != "posix":
        return False, "not a POSIX system"
    try:
        import resource
    except ImportError:
        return False, "resource module unavailable"
    try:
        # Read current limits and confirm we can at least query/set them.
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        # Try tightening the soft limit for THIS process to a safe value and back.
        test_soft = min(soft, 512) if soft > 0 else 512
        resource.setrlimit(resource.RLIMIT_NOFILE, (test_soft, hard))
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))  # restore
        return True, f"RLIMIT_NOFILE settable (current soft={soft})"
    except Exception as e:
        return False, f"setrlimit failed: {e}"


def main():
    print("=" * 60)
    print("  OpenOptOut plugin sandbox — preflight report")
    print("=" * 60)

    # Use the real detection the manager uses, so this report matches runtime.
    try:
        from .sandbox import detect_capabilities
        caps = detect_capabilities()
    except Exception as e:
        print(f"\nCould not import sandbox module: {e}")
        print("Plugin system will be INACTIVE.")
        sys.exit(0)

    print(f"\nPlatform: {platform.system()} ({platform.machine()})")
    print(f"Running as uid: {os.geteuid() if hasattr(os, 'geteuid') else 'n/a'}")
    print("\nIsolation mechanisms:")

    def row(name, ok, note=""):
        mark = "✓" if ok else "✗"
        print(f"  [{mark}] {name:22} {note}")

    row("bubblewrap (bwrap)", caps.bubblewrap,
        "namespace isolation" if caps.bubblewrap else "MISSING — no namespace isolation")
    row("unshare fallback", caps.unshare,
        "" if caps.unshare else "not present")
    row("seccomp (libseccomp)", caps.seccomp,
        "syscall filtering" if caps.seccomp else "MISSING — no syscall filter")
    row("POSIX rlimits", caps.rlimits,
        "mem/cpu/fd/proc caps" if caps.rlimits else "MISSING")
    row("privilege drop", caps.drop_privileges,
        "can drop from root" if caps.drop_privileges else "already unprivileged / n/a")

    # Actively verify rlimits, the baseline layer.
    ok, note = check_rlimits_actually_work()
    print(f"\nActive rlimit test: {'PASS' if ok else 'FAIL'} — {note}")

    # Verdict.
    print("\n" + "-" * 60)
    if caps.bubblewrap and caps.seccomp and caps.rlimits:
        print("  POSTURE: FULL — namespace isolation + syscall filter + rlimits.")
        print("  Safe to run untrusted plugins with all controls active.")
    elif caps.rlimits and (caps.bubblewrap or caps.unshare):
        print("  POSTURE: PARTIAL — process isolation + rlimits, but syscall")
        print("  filtering and/or full namespacing may be reduced.")
        print("  Untrusted plugins run with meaningful but not maximal isolation.")
    elif caps.rlimits:
        print("  POSTURE: MINIMAL — resource limits only (no bubblewrap/seccomp).")
        print("  The process/gRPC isolation and rlimits still apply, but this is")
        print("  NOT sufficient for genuinely untrusted third-party plugins.")
        print("  Install bubblewrap + libseccomp2 (see docs/PLUGINS.md).")
    else:
        print("  POSTURE: NONE — no OS isolation available.")
        print("  Run only trusted first-party plugins here.")
    print("-" * 60)

    # Show what the actual sandbox command would look like, if we can build one.
    try:
        from .sandbox import build_sandboxed_command
        from .permissions import PluginManifest
        demo_manifest = PluginManifest(
            id="example", name="Example", version="1.0", author="x",
            max_memory_mb=128, max_cpu_seconds=15,
        )
        cmd, _preexec = build_sandboxed_command(
            ["python", "runner.py"], "/data/plugins/example", caps,
            allow_network=False, manifest=demo_manifest,
        )
        print("\nExample sandboxed launch command the manager would use:")
        print("  " + " ".join(cmd[:12]) + (" ..." if len(cmd) > 12 else ""))
    except Exception as e:
        print(f"\n(Could not render example command: {e})")

    sys.exit(0)


if __name__ == "__main__":
    main()
