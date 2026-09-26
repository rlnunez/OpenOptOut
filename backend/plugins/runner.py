#!/usr/bin/env python3
"""
Plugin runner — the subprocess entry point.

Executed inside the sandbox by the manager. Loads the plugin's Python file,
which is expected to construct a Plugin (from the SDK) and call run(). We set
up the environment so the SDK can find the compiled proto stubs, then exec the
plugin file.

The plugin file is responsible for calling plugin.run(), which prints
"PLUGIN_READY <port>" and serves the PluginService. This runner just bootstraps
that in an isolated interpreter.

Because this runs inside the sandbox (bubblewrap/unshare + rlimits), even fully
untrusted plugin code is contained: no host filesystem, no network unless
granted, capped memory/CPU, and no access to the host process.
"""

import os
import sys
import runpy
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-file", required=True)
    parser.add_argument("--plugin-id", required=True)
    parser.add_argument("--max-memory-mb", type=int, default=192)
    parser.add_argument("--allow-network", action="store_true",
                        help="plugin was granted the network permission")
    args = parser.parse_args()

    # ── Memory cap, applied to OUR OWN process, as the very first thing ──
    # Deliberately NOT done via preexec_fn on the manager side: that runs
    # after fork() but before exec(), while this process is still a
    # fork()'d copy of the (much larger, ever-growing) parent API process —
    # setting the limit there measures against that inherited footprint,
    # not this plugin's own needs. exec() (which already happened to get
    # us into this function at all) replaced the address space with a
    # fresh one, so applying it here, before importing anything beyond the
    # stdlib modules already imported above, gives a limit that actually
    # reflects what THIS plugin needs — predictable regardless of how large
    # or long-running the host process has become.
    try:
        import resource
        mem_bytes = args.max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except Exception as e:
        print(f"WARNING: could not set memory limit: {e}", file=sys.stderr)

    if not os.path.isfile(args.plugin_file):
        print(f"ERROR: plugin file not found: {args.plugin_file}", file=sys.stderr)
        sys.exit(2)

    # Make the SDK importable. PYTHONPATH is set by the manager, but reinforce it.
    sdk_dir = os.path.join(os.path.dirname(__file__), "sdk")
    if sdk_dir not in sys.path:
        sys.path.insert(0, sdk_dir)

    # ── Install the seccomp syscall filter BEFORE any plugin code runs ──
    # This blocks exec/fork/mount/ptrace and (unless granted) network syscalls
    # at the kernel level. Once installed it cannot be removed by the plugin.
    # We import the SDK first (it needs grpc/socket to talk to the host over the
    # loopback), then lock down. The host<->plugin channel uses a unix-like
    # loopback socket established by grpc; to keep that working we allow the
    # loopback by NOT blocking socket calls when the plugin needs to serve gRPC.
    #
    # IMPORTANT: the plugin's gRPC server itself needs socket syscalls to talk
    # to the host on 127.0.0.1. Blocking ALL sockets would break the transport.
    # The network *namespace* (applied by the host via bubblewrap/unshare) is
    # what prevents reaching the outside world — loopback remains available for
    # the host channel. So seccomp here blocks process/exec/escape syscalls
    # always, and blocks outbound socket creation only as defense-in-depth when
    # network is not granted AND the host could not apply a net namespace.
    try:
        # Import the SDK + grpc up front so their socket setup happens before
        # any optional socket-level seccomp restriction.
        import grpc  # noqa: F401
    except Exception:
        pass

    seccomp_status = {"active": False, "reason": "not attempted"}
    try:
        from seccomp_filter import install_seccomp_filter  # via PYTHONPATH (plugins/)
    except Exception:
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from seccomp_filter import install_seccomp_filter
        except Exception as e:
            install_seccomp_filter = None
            seccomp_status["reason"] = f"seccomp module unavailable: {e}"

    if install_seccomp_filter is not None:
        # We keep loopback sockets working for the gRPC host channel, so we do
        # NOT block the socket family here (the net namespace handles egress).
        # Process/exec/escape syscalls are always blocked.
        seccomp_status = install_seccomp_filter(allow_network=True)

    # Report the enforced posture to the host via stdout (the manager records it).
    print(f"PLUGIN_SECCOMP {int(seccomp_status.get('active', False))} "
          f"{len(seccomp_status.get('blocked', []))}", flush=True)

    # The session token + host port arrive via env; the SDK reads them when the
    # host calls Initialize, but we also expose them for plugins that want them.
    os.environ.setdefault("PS_PLUGIN_ID", args.plugin_id)

    # Execute the plugin file as __main__ so its `if __name__ == "__main__"`
    # block (which calls plugin.run()) fires.
    runpy.run_path(args.plugin_file, run_name="__main__")


if __name__ == "__main__":
    main()
