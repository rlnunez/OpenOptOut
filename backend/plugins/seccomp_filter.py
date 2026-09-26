"""
Seccomp-bpf syscall filtering for plugin processes.

This runs INSIDE the plugin subprocess, before the plugin's own code executes.
It installs a seccomp filter that blocks entire classes of dangerous syscalls
at the kernel level. Once installed, the filter cannot be removed by the plugin
(NO_NEW_PRIVS is set), so even code that does `import ctypes` and calls raw
syscalls is stopped by the kernel.

This is REAL prevention, not monitoring. It complements the network namespace
(which blocks network) and bubblewrap (which hides the filesystem):

  - blocks exec/fork, and process- (not thread-) creating clone() -> plugin
                                          cannot spawn a new process or run a
                                          binary (clone3()'s struct-based ABI
                                          can't be filtered this way — see the
                                          comment above CLONE_THREAD below)
  - blocks socket family (optional)   -> plugin cannot open sockets even if a
                                          network namespace somehow had an interface
  - blocks ptrace, mount, kexec, etc. -> no sandbox-escape primitives

If libseccomp (via the `seccomp` python package) is unavailable, this degrades:
it logs that syscall filtering is NOT active and relies on the other layers
(namespaces, rlimits, bubblewrap). The host advertises the reduced posture.

Design: allowlist is impractical for a Python interpreter (hundreds of syscalls),
so we use a DENYLIST of the specifically dangerous ones. This is weaker than a
strict allowlist but far more robust than nothing and doesn't break the Python
runtime the plugin needs.
"""

import os
import sys
import logging

log = logging.getLogger(__name__)


# Syscalls we deny outright. Names are matched against libseccomp's resolver;
# unknown names on a given arch are skipped safely.
DENY_SYSCALLS_PROCESS = [
    # process creation / program execution
    "execve", "execveat",
    "fork", "vfork",
    # clone is handled separately, below — plain fork-style process creation is
    # blocked, but thread creation (which also goes through clone()/clone3())
    # is not.
    # loading kernel modules / rebooting / mounting — escape primitives
    "init_module", "finit_module", "delete_module",
    "kexec_load", "kexec_file_load",
    "mount", "umount", "umount2", "pivot_root", "chroot",
    "reboot", "swapon", "swapoff",
    # debugging other processes
    "ptrace", "process_vm_readv", "process_vm_writev",
    # setuid family — privilege changes
    "setuid", "setgid", "setreuid", "setregid",
    "setresuid", "setresgid", "setfsuid", "setfsgid",
    # bpf / perf — powerful kernel interfaces
    "bpf", "perf_event_open",
    # namespace manipulation (prevent re-namespacing tricks)
    "unshare", "setns",
]

# clone() is how Linux creates BOTH new processes (what fork()/vfork() are
# built on) and new threads within the same process (what every pthread —
# including the ones gRPC's C-core always spawns for its event loop — is
# built on). There's no separate "create a thread" syscall to allow instead;
# blocking clone() by name, as this filter originally did, blocks both, which
# breaks any plugin using a threaded library and, in particular, meant the
# plugin's own gRPC server (needed for EVERY plugin to talk back to the host
# at all) could never actually start — pthread_create failed with EPERM
# before any plugin code ran, for every single plugin, unconditionally.
#
# The two cases are distinguishable in principle: thread creation always sets
# the CLONE_THREAD flag; process creation never does. clone()'s first
# argument is the flags word on every Linux architecture (a stable part of
# the syscall ABI), so a conditional rule below denies clone() only when that
# flag is absent — blocking fork-style process creation while letting thread
# creation through.
#
# clone3(), a newer syscall covering the same two cases, can't get the same
# treatment: it takes a pointer to a clone_args struct rather than individual
# register arguments, and seccomp — a kernel-level filter with no ability to
# dereference userspace pointers — cannot inspect flags packed inside it.
# This isn't a hypothetical gap: it's confirmed to matter here. Current
# glibc (as shipped in this project's own Debian-bookworm-based image)
# creates threads via clone3() when the kernel supports it, not plain
# clone() — so blocking clone3() outright, the seemingly-cautious choice,
# reintroduces exactly the same failure as blocking clone() did: every
# plugin's gRPC server fails to start, unconditionally. clone3() is left
# unrestricted at the seccomp layer as a result. The residual exposure this
# leaves — a plugin using clone3() to spawn a full child process rather than
# a thread — is real but narrower than it sounds: execve/execveat stay
# blocked above, so a clone3()'d child still can't exec an external binary;
# it can only keep running the same already-sandboxed plugin code.
CLONE_THREAD = 0x00010000

# Network-related syscalls, denied unless the plugin was granted `network`.
DENY_SYSCALLS_NETWORK = [
    "socket", "socketpair", "connect", "accept", "accept4",
    "bind", "listen", "sendto", "recvfrom", "sendmsg", "recvmsg",
    "getpeername",
]


def install_seccomp_filter(allow_network: bool) -> dict:
    """
    Install the seccomp filter in the current process. Returns a status dict.
    Call this once, early in the plugin runner, before executing plugin code.

    On success the filter is active for the life of the process and inherited
    by any (already-blocked) children. Returns {"active": bool, "reason": str,
    "blocked": [...]}.
    """
    result = {"active": False, "reason": "", "blocked": [], "network_blocked": not allow_network}

    # Set NO_NEW_PRIVS so a seccomp filter can be installed without privilege,
    # and so exec (if it somehow slipped through) can't gain privileges.
    try:
        import ctypes
        PR_SET_NO_NEW_PRIVS = 38
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            log.warning("prctl(NO_NEW_PRIVS) failed; seccomp may be unavailable")
    except Exception as e:
        result["reason"] = f"prctl unavailable: {e}"
        # continue; seccomp lib may still work

    try:
        import seccomp  # python-seccomp / libseccomp bindings
    except Exception as e:
        result["reason"] = f"libseccomp not available ({e}); syscall filtering INACTIVE"
        log.warning(result["reason"])
        return result

    try:
        # Default action ALLOW, then add explicit denies (denylist approach so
        # the Python runtime keeps working). Denied calls return EPERM rather
        # than killing the process, so we get a clean error the plugin can't
        # ignore, and the host's monitor sees the failure pattern.
        ERRNO_EPERM = 1
        f = seccomp.SyscallFilter(defaction=seccomp.ALLOW)

        denies = list(DENY_SYSCALLS_PROCESS)
        if not allow_network:
            denies += DENY_SYSCALLS_NETWORK

        for name in denies:
            try:
                f.add_rule(seccomp.ERRNO(ERRNO_EPERM), name)
                result["blocked"].append(name)
            except Exception:
                # syscall not known on this arch/kernel — skip safely
                pass

        # clone(): deny it ONLY when it's NOT thread creation (CLONE_THREAD
        # unset) — i.e. block process creation, let thread creation fall
        # through to the filter's default ALLOW action. See the long comment
        # above DENY_SYSCALLS_PROCESS for why clone() needs this instead of a
        # plain name block. (An explicit ALLOW rule for the thread case, added
        # alongside a blanket deny, looks like the obvious way to write this —
        # it isn't: libseccomp rejects an explicit ALLOW rule that matches the
        # filter's own default action with EACCES. One conditional deny is
        # both correct and all libseccomp actually accepts here.)
        try:
            f.add_rule(seccomp.ERRNO(ERRNO_EPERM), "clone",
                      seccomp.Arg(0, seccomp.MASKED_EQ, CLONE_THREAD, 0))
            result["blocked"].append("clone (except thread creation)")
        except Exception as e:
            result["reason"] = (result["reason"] + "; " if result["reason"] else "") + \
                f"clone thread-exception rule failed, leaving clone unrestricted: {e}"

        f.load()
        result["active"] = True
        # Don't clobber a partial-failure note (e.g. the clone rule above
        # failing to add) that was already recorded — append to it instead.
        result["reason"] = (result["reason"] + "; seccomp filter active"
                           if result["reason"] else "seccomp filter active")
        log.info("seccomp filter installed: %d syscalls blocked (network_blocked=%s)",
                 len(result["blocked"]), not allow_network)
    except Exception as e:
        result["reason"] = f"seccomp load failed: {e}"
        log.warning(result["reason"])

    return result
