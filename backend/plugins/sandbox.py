"""
OS-level sandboxing for plugin subprocesses.

Defense in depth, applied when launching each plugin process. Layers degrade
gracefully by platform — the strongest controls are Linux-only, and the host
logs exactly which controls are active so operators know their real posture.

Controls, strongest to weakest:

  1. Linux namespaces (via `unshare`/`bwrap` if present) — isolate mounts, PID,
     network, and users. A plugin with no NETWORK permission gets a network
     namespace with no interfaces, so it physically cannot reach the network.

  2. seccomp-bpf syscall filtering (via a preload in the runner) — blocks
     dangerous syscalls (ptrace, mount, kexec, etc). Best-effort.

  3. POSIX resource limits (RLIMIT_*) — cap memory, CPU time, file size,
     process count, and open files. Always applied on POSIX.

  4. Filesystem confinement — with bubblewrap, the rest of the FS is hidden
     entirely and the plugin's own directory is mounted READ-ONLY, so a plugin
     can't rewrite its code or drop new program files; its only writable
     space is a private, throwaway /tmp (persistent data goes through the
     storage API). Independently of the sandbox, the manager refuses to launch
     a plugin whose files changed since install (see manager.launch_plugin).

  5. Dropped privileges — never run plugins as root; drop to an unprivileged
     uid/gid when the host has the capability to do so.

If none of the Linux tools are available (e.g. on macOS during development),
the host falls back to resource limits + timeouts + the process boundary
itself, and logs a clear warning that full sandboxing is not in effect.
"""

import os
import sys
import shutil
import logging
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class SandboxCapabilities:
    """What sandboxing the current host can actually enforce."""
    bubblewrap:      bool = False   # bwrap present -> strong FS + namespace isolation
    unshare:         bool = False   # unshare present -> namespace isolation
    seccomp:         bool = False   # seccomp filtering available
    rlimits:         bool = False   # POSIX resource limits available
    drop_privileges: bool = False   # can drop to unprivileged user
    readonly_code:   bool = False   # unshare fallback can mount the plugin dir read-only
    platform:        str  = ""

    def summary(self) -> str:
        active = [k for k, v in self.__dict__.items() if v is True]
        return ", ".join(active) if active else "none (process boundary only)"

    @property
    def is_fully_sandboxed(self) -> bool:
        return (self.bubblewrap or self.unshare) and self.rlimits


def _can_actually_run(cmd: list[str], timeout: float = 5.0) -> bool:
    """
    A sandboxing tool being INSTALLED doesn't mean it can actually create the
    namespaces it needs — that requires privileges (CAP_SYS_ADMIN, or an
    unprivileged-userns sysctl) most container runtimes drop by default, and
    this project's own docker-compose.yml deliberately leaves them off unless
    an operator opts in (see its "Plugin sandboxing note"). shutil.which()
    only checks the binary is on PATH; it says nothing about whether THIS
    process, in THIS container, can use it. Actually run a no-op through it
    and check whether it succeeds, so an unprivileged container correctly
    detects "no" and falls through to the resource-limits-only tier — which
    needs no special privileges and works everywhere — instead of confidently
    attempting bwrap/unshare on every plugin launch and having each one fail
    silently at runtime (the process starts, never reports ready, and gets
    killed after a timeout with no indication of why).
    """
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


def detect_capabilities() -> SandboxCapabilities:
    """Probe the host for available sandboxing mechanisms."""
    caps = SandboxCapabilities(platform=platform.system())

    is_linux = platform.system() == "Linux"
    is_posix = os.name == "posix"

    if is_posix:
        try:
            import resource  # noqa: F401
            caps.rlimits = True
        except ImportError:
            pass

    if is_linux:
        # Functional probes, not just "is the binary on PATH" — see
        # _can_actually_run's docstring for why that distinction matters.
        if shutil.which("bwrap") is not None:
            caps.bubblewrap = _can_actually_run(
                ["bwrap", "--unshare-all", "--die-with-parent", "--", "true"])
        if shutil.which("unshare") is not None:
            caps.unshare = _can_actually_run(
                ["unshare", "--fork", "--pid", "--mount-proc", "--", "true"])
            if caps.unshare and not caps.bubblewrap:
                caps.readonly_code = _probe_readonly_mount()
        # seccomp is available if we can import the helper or use a preload;
        # we conservatively mark it available on Linux where libseccomp exists.
        caps.seccomp    = os.path.exists("/usr/lib/x86_64-linux-gnu/libseccomp.so.2") \
                          or os.path.exists("/lib/x86_64-linux-gnu/libseccomp.so.2")
        # Can drop privileges only if we're root (otherwise we're already
        # unprivileged, which is fine).
        caps.drop_privileges = (os.geteuid() == 0) if hasattr(os, "geteuid") else False

    return caps


# Runs inside the unshare fallback's private mount namespace. $1 is the plugin
# directory, $2 is "1" to give the plugin a private /tmp (like bubblewrap's).
# Re-mounts the plugin directory read-only over itself, then runs the plugin
# there. Nothing is visible outside the namespace, and if a mount fails the
# plugin doesn't start (fail closed).
_READONLY_MOUNT_SCRIPT = ('d="$1"; t="$2"; shift 2; '
                          'if [ "$t" = 1 ]; then mount -t tmpfs -o size=64m,mode=1777 tmpfs /tmp || exit 1; fi; '
                          'mount --bind "$d" "$d" && mount -o remount,bind,ro "$d" && '
                          'cd "$d" && exec "$@"')


def _private_tmp_ok(*paths) -> str:
    """ "1" if a private /tmp can be mounted without hiding any of these paths
    (the plugin directory, runtime sockets, and the Python runtime), else "0"."""
    tmp_real = os.path.realpath("/tmp")  # nosec: B108 -- validating host mount paths against system /tmp
    def under_tmp(p):
        if not p:
            return False
        p_real = os.path.realpath(p)
        return (p == "/tmp" or p.startswith("/tmp/") or  # nosec: B108 -- checking /tmp path prefix
                p_real == tmp_real or p_real.startswith(tmp_real + "/"))
    return "0" if any(under_tmp(p) for p in paths if p) else "1"


_UNSHARE_MOUNT = ["unshare", "--fork", "--pid", "--mount-proc", "--mount", "--propagation", "private"]


def _probe_readonly_mount() -> bool:
    """Can the unshare fallback make a directory read-only for a plugin? Checked
    for real: the probe must be unable to create a file in the directory."""
    import tempfile
    d = tempfile.mkdtemp(prefix="ps-ro-probe-")
    try:
        ok = _can_actually_run(_UNSHARE_MOUNT + ["--", "sh", "-c", _READONLY_MOUNT_SCRIPT, "sh", d, "0",
                                                 "sh", "-c", "! touch probe 2>/dev/null"])
        return ok and not os.path.exists(os.path.join(d, "probe"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _resource_limit_preexec(max_cpu_seconds: int, allow_network: bool):
    """
    Return a preexec_fn (runs in the child before exec) that applies POSIX
    resource limits and, where possible, tightens the environment.

    NOTE: preexec_fn runs in the forked child. Keep it minimal and import-safe.
    """
    def _apply():
        try:
            import resource
            # RLIMIT_AS (memory) is deliberately NOT set here. preexec_fn runs
            # after fork() but before exec() — subprocess.Popen is forced onto
            # that path specifically because preexec_fn is given (the faster
            # posix_spawn can't run arbitrary Python before exec). At the
            # moment this function runs, the process is still a fork()'d copy
            # of the PARENT api process (this whole FastAPI/SQLAlchemy/grpc/
            # Playwright-loaded backend, whatever its memory footprint happens
            # to be after running for a while) — not the small, fresh plugin
            # process it's about to become. Setting a manifest's, say, 384MB
            # cap here measures against THAT inherited footprint, not the
            # plugin's own needs, which is what caused real plugins to hit
            # MemoryError launching a perfectly ordinary API client, at
            # memory levels that had nothing to do with what the plugin
            # itself actually needed — the ceiling was being eaten by the
            # parent process's own size before the plugin did anything.
            # exec() replaces the address space with a fresh one, so the fix
            # is applying this limit AFTER that point instead: see runner.py,
            # which sets RLIMIT_AS on itself as the first thing it does.
            # CPU seconds
            resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_seconds, max_cpu_seconds))
            # Max file size a plugin can create: 50MB
            resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
            # Cap number of processes/threads to prevent fork bombs
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            # Cap open file descriptors
            resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
            # Prevent core dumps (could leak memory contents to disk)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except Exception:
            # Best effort — never block launch on rlimit failure
            pass

        # Start a new session so we can kill the whole process group cleanly
        try:
            os.setsid()
        except Exception:
            pass

    return _apply


def build_sandboxed_command(
    base_cmd: list[str],
    work_dir: str,
    caps: SandboxCapabilities,
    allow_network: bool,
    manifest,
    run_dir: Optional[str] = None,
    host_uds_path: Optional[str] = None,
) -> tuple[list[str], Optional[callable]]:
    """
    Wrap base_cmd (e.g. ["python", "runner.py", ...]) with the strongest
    available sandbox. Returns (command, preexec_fn).

    Strategy:
      - Prefer bubblewrap: hides the host filesystem, gives a private /tmp,
        and creates a network namespace with NO interfaces unless network is
        granted. This is the strongest readily-available isolation.
      - Fall back to `unshare` for namespace isolation.
      - Always attach POSIX resource limits via preexec_fn.
    """
    preexec = _resource_limit_preexec(
        manifest.max_cpu_seconds, allow_network
    ) if caps.rlimits else None

    # ---- Bubblewrap: strongest ----
    if caps.bubblewrap:
        bwrap = [
            "bwrap",
            "--unshare-all",                 # isolate all namespaces...
            "--share-net" if allow_network else "--unshare-net",  # ...but optionally keep net
            "--die-with-parent",             # kill plugin if host dies
            "--new-session",                 # detach from controlling terminal
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",  # nosec: B108 -- mounting isolated tmpfs inside container sandbox
            # Read-only view of the Python runtime + stdlib
            "--ro-bind", sys.prefix, sys.prefix,
            # The plugin's own code, READ-ONLY: it can't modify itself or add
            # program files. Its only writable space is the private /tmp above.
            "--ro-bind", work_dir, work_dir,
            "--chdir", work_dir,
            # Minimal, clean environment
            "--clearenv",
            "--setenv", "PATH", "/usr/bin:/bin",
            "--setenv", "HOME", "/tmp",
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        ]
        # If the interpreter lives outside sys.prefix (venv), bind it too
        py_real = os.path.realpath(sys.executable)
        if not py_real.startswith(os.path.realpath(sys.prefix)):
            bwrap += ["--ro-bind", os.path.dirname(py_real), os.path.dirname(py_real)]

        # Unix domain socket mounts for host <-> plugin IPC across network namespaces:
        # 1. Mount the per-plugin runtime directory (writable, where plugin.sock is created)
        if run_dir:
            bwrap += ["--dir", run_dir, "--bind", run_dir, run_dir]
        # 2. Mount HostService socket (read-only, so the plugin cannot delete or overwrite it)
        if host_uds_path:
            bwrap += ["--dir", os.path.dirname(host_uds_path),
                      "--ro-bind", host_uds_path, host_uds_path]

        return bwrap + base_cmd, preexec

    # ---- unshare: namespace isolation without bubblewrap ----
    if caps.unshare:
        if caps.readonly_code:
            # Same read-only plugin folder as bubblewrap gives, via a private
            # mount namespace (see _READONLY_MOUNT_SCRIPT).
            unshare = list(_UNSHARE_MOUNT)
            if not allow_network:
                unshare.append("--net")
            private_tmp = _private_tmp_ok(work_dir, sys.executable, sys.prefix, run_dir, host_uds_path)
            return (unshare + ["--", "sh", "-c", _READONLY_MOUNT_SCRIPT, "sh", work_dir, private_tmp]
                    + base_cmd), preexec
        unshare = ["unshare", "--fork", "--pid", "--mount-proc"]
        if not allow_network:
            unshare.append("--net")   # network namespace with no interfaces
        return unshare + base_cmd, preexec

    # ---- Fallback: resource limits + process boundary only ----
    log.warning(
        "Full OS sandboxing unavailable on this host (%s). Running plugins with "
        "resource limits + process isolation only. For untrusted plugins, deploy "
        "on Linux with bubblewrap (`bwrap`) installed.",
        caps.platform,
    )
    return base_cmd, preexec


def log_sandbox_posture(caps: SandboxCapabilities):
    """Emit a clear one-time statement of the effective security posture."""
    if caps.is_fully_sandboxed:
        log.info("Plugin sandbox: FULL — %s", caps.summary())
    else:
        log.warning(
            "Plugin sandbox: PARTIAL — %s. Untrusted third-party plugins are NOT "
            "fully contained. See docs/PLUGINS.md for hardening.", caps.summary()
        )
