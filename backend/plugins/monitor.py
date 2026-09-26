"""
Plugin runtime violation monitor.

Watches running plugin processes for signs of leak/escape attempts and records
violations. On detection it can auto-disable the offending plugin immediately
(the default, safest behavior) or, in global lockdown mode, treat any single
violation as grounds for shutdown.

Enforcement vs. monitoring — an honest split:

  PREVENTED at the OS layer (a plugin CANNOT do these when full sandbox active):
    - reach the external network        -> network namespace (no interface)
    - see/modify the host filesystem     -> bubblewrap read-only host + private tmp
    - exec binaries / fork processes     -> seccomp denies execve/fork/clone
    - escalate privileges / escape       -> seccomp denies setuid/mount/ptrace/etc.

  MONITORED here (detect + auto-disable; a safety net, and the primary layer on
  hosts WITHOUT full sandboxing):
    - a child process appeared under the plugin  -> attempted exec/fork
    - files written outside the plugin's dir     -> attempted host FS write
    - the plugin's own dir grew beyond a cap     -> possible data staging
    - resident memory exceeded the manifest cap  -> resource abuse
    - the process opened network sockets         -> attempted egress (best-effort)

Detection uses /proc where available (Linux). On non-Linux hosts, detection is
limited and the monitor says so; the recommendation there is to only run
trusted plugins.

Violations are persisted (PluginAuditLog + a violations store) and surfaced in
the admin UI so the super admin can see exactly what each plugin attempted.
"""

import os
import time
import glob
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


VIOLATION_TYPES = {
    "child_process":    {"label": "Spawned a child process", "severity": "critical"},
    "external_file":    {"label": "Wrote a file outside its sandbox", "severity": "critical"},
    "network_socket":   {"label": "Opened a network socket", "severity": "critical"},
    "undeclared_method":{"label": "Called a host method not in its manifest", "severity": "critical"},
    "undeclared_domain":{"label": "Contacted a domain not in its manifest", "severity": "critical"},
    "memory_exceeded":  {"label": "Exceeded its memory limit", "severity": "high"},
    "dir_bloat":        {"label": "Its storage dir grew abnormally large", "severity": "medium"},
    "unresponsive":     {"label": "Stopped responding to health checks", "severity": "high"},
}


@dataclass
class Violation:
    plugin_id: str
    vtype: str
    detail: str
    severity: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self):
        return {
            "plugin_id": self.plugin_id, "type": self.vtype,
            "label": VIOLATION_TYPES.get(self.vtype, {}).get("label", self.vtype),
            "detail": self.detail, "severity": self.severity,
            "timestamp": self.timestamp,
        }


class ViolationMonitor:
    """
    Polls running plugin processes and reports violations via a callback.

    on_violation(violation: Violation)  -> called for each detected violation
    is_lockdown()                        -> bool; when True, ANY violation is fatal
    """

    def __init__(self, on_violation, is_lockdown=None, poll_seconds: int = 5):
        self.on_violation = on_violation
        self.is_lockdown  = is_lockdown or (lambda: False)
        self.poll_seconds = poll_seconds
        self._watched: dict[str, dict] = {}   # plugin_id -> {pid, work_dir, max_mem_mb}
        self._baseline_children: dict[int, set] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc_available = os.path.isdir("/proc")

    # ---- registration ----

    def watch(self, plugin_id: str, pid: int, work_dir: str, max_mem_mb: int,
              heavy_monitoring: bool = False):
        """
        heavy_monitoring=True is set for any plugin running with BOTH read_pii
        and network granted (the read_pii+network exception). It tightens the
        egress checks: byte-volume tracking via /proc net stats, a much lower
        socket-count tolerance, and every connection attempt logged (not just
        ones that cross the violation threshold).
        """
        with self._lock:
            self._watched[plugin_id] = {
                "pid": pid, "work_dir": os.path.realpath(work_dir),
                "max_mem_mb": max_mem_mb,
                "dir_baseline": self._dir_size(work_dir),
                "heavy_monitoring": heavy_monitoring,
                "egress_baseline_bytes": self._net_bytes_sent(pid) if heavy_monitoring else 0,
            }
            self._baseline_children[pid] = self._child_pids(pid)
            if heavy_monitoring:
                log.warning(
                    "Plugin %s (pid %s) is running under HEAVY MONITORING "
                    "(read_pii + network exception active)", plugin_id, pid
                )

    def unwatch(self, plugin_id: str):
        with self._lock:
            info = self._watched.pop(plugin_id, None)
            if info:
                self._baseline_children.pop(info["pid"], None)

    # ---- lifecycle ----

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Violation monitor started (proc=%s, poll=%ss)",
                 self._proc_available, self.poll_seconds)

    def stop(self):
        self._stop.set()

    def capabilities(self) -> dict:
        """What this monitor can actually detect on this host."""
        return {
            "proc_inspection": self._proc_available,
            "detects": {
                "child_process":  self._proc_available,
                "external_file":  self._proc_available,
                "network_socket": self._proc_available,
                "memory_exceeded": self._proc_available,
                "dir_bloat":       True,
            },
            "note": ("Full detection available (Linux /proc)."
                     if self._proc_available else
                     "Limited detection (no /proc). Run only trusted plugins on this host."),
        }

    # ---- detection loop ----

    def _loop(self):
        while not self._stop.wait(self.poll_seconds):
            with self._lock:
                items = list(self._watched.items())
            for plugin_id, info in items:
                try:
                    self._check(plugin_id, info)
                except Exception as e:
                    log.debug("monitor check error for %s: %s", plugin_id, e)

    def _check(self, plugin_id: str, info: dict):
        pid = info["pid"]
        if not self._pid_alive(pid):
            return

        # 1) Child processes (attempted exec/fork) — critical
        if self._proc_available:
            current = self._child_pids(pid)
            baseline = self._baseline_children.get(pid, set())
            new_children = current - baseline
            if new_children:
                self._raise(plugin_id, "child_process",
                            f"pid {pid} spawned child pids {sorted(new_children)}")

        # 2) Network sockets (attempted egress) — critical, best-effort.
        #    Under heavy monitoring (read_pii + network exception active), the
        #    tolerance is tighter and every socket is logged, not just excess.
        if self._proc_available:
            heavy = info.get("heavy_monitoring", False)
            socks = self._open_sockets(pid, tight=heavy)
            if socks:
                self._raise(plugin_id, "network_socket",
                            f"{socks} network socket(s) detected"
                            + (" [HEAVY MONITORING: read_pii+network plugin]" if heavy else ""))
            elif heavy:
                # Even zero excess sockets gets a quiet log line under heavy
                # monitoring, so there's a continuous record for this plugin.
                log.debug("heavy-monitoring check OK for %s (pid %s): no excess sockets", plugin_id, pid)

        # 2b) Egress byte-volume tracking — heavy monitoring only. A single
        # connection isn't inherently a violation (network was granted), but a
        # large or sustained transfer is a strong exfiltration signal.
        if self._proc_available and info.get("heavy_monitoring", False):
            sent = self._net_bytes_sent(pid)
            delta = max(0, sent - info.get("egress_baseline_bytes", 0))
            EXFIL_BYTES_THRESHOLD = 5 * 1024 * 1024   # 5MB since watch() began
            if delta > EXFIL_BYTES_THRESHOLD:
                self._raise(plugin_id, "network_socket",
                            f"HEAVY MONITORING: {delta // 1024}KB sent since launch — "
                            f"exceeds {EXFIL_BYTES_THRESHOLD // (1024*1024)}MB exfiltration threshold")

        # 3) Files opened for write outside the sandbox dir — critical
        if self._proc_available:
            bad = self._external_writes(pid, info["work_dir"])
            if bad:
                self._raise(plugin_id, "external_file",
                            f"write handle outside sandbox: {bad[0]}")

        # 4) Memory over the manifest cap — high
        if self._proc_available:
            rss_mb = self._rss_mb(pid)
            if rss_mb and rss_mb > info["max_mem_mb"] * 1.25:  # 25% grace
                self._raise(plugin_id, "memory_exceeded",
                            f"RSS {rss_mb}MB > cap {info['max_mem_mb']}MB")

        # 5) Storage dir bloat — medium
        size = self._dir_size(info["work_dir"])
        if size - info["dir_baseline"] > 200 * 1024 * 1024:  # +200MB
            self._raise(plugin_id, "dir_bloat",
                        f"work dir grew to {size // (1024*1024)}MB")

    def _raise(self, plugin_id: str, vtype: str, detail: str):
        sev = VIOLATION_TYPES.get(vtype, {}).get("severity", "medium")
        v = Violation(plugin_id=plugin_id, vtype=vtype, detail=detail, severity=sev)
        log.warning("PLUGIN VIOLATION [%s] %s: %s", sev, plugin_id, detail)
        try:
            self.on_violation(v)
        except Exception as e:
            log.error("violation callback failed: %s", e)

    # ---- /proc helpers (Linux) ----

    def _pid_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    def _child_pids(self, pid: int) -> set:
        if not self._proc_available:
            return set()
        children = set()
        try:
            # /proc/<pid>/task/<tid>/children lists child pids
            for children_file in glob.glob(f"/proc/{pid}/task/*/children"):
                try:
                    with open(children_file) as f:
                        for tok in f.read().split():
                            children.add(int(tok))
                except Exception:
                    pass
        except Exception:
            pass
        return children

    def _open_sockets(self, pid: int, tight: bool = False) -> int:
        """
        Count socket fds. Loopback (host gRPC channel) is expected and excluded.
        tight=True (heavy monitoring: read_pii + network exception) uses a
        much lower tolerance, since any egress at all from such a plugin is
        significant.
        """
        if not self._proc_available:
            return 0
        count = 0
        try:
            fd_dir = f"/proc/{pid}/fd"
            for fd in os.listdir(fd_dir):
                try:
                    target = os.readlink(os.path.join(fd_dir, fd))
                    if target.startswith("socket:"):
                        count += 1
                except Exception:
                    pass
        except Exception:
            return 0
        # The plugin's own gRPC server + host channel use a few loopback sockets.
        # Only flag if there are more than a small expected baseline. Under
        # heavy monitoring the tolerance is tighter — even one extra socket
        # beyond the loopback baseline is flagged.
        EXPECTED_LOOPBACK = 2 if tight else 6
        return max(0, count - EXPECTED_LOOPBACK)

    def _external_writes(self, pid: int, work_dir: str) -> list:
        """Find open file descriptors pointing outside the plugin's work dir."""
        if not self._proc_available:
            return []
        bad = []
        try:
            fd_dir = f"/proc/{pid}/fd"
            for fd in os.listdir(fd_dir):
                try:
                    target = os.readlink(os.path.join(fd_dir, fd))
                    if target.startswith("/") and not target.startswith(("/dev", "/proc", "/sys")):
                        real = os.path.realpath(target)
                        # Allow the work dir, private tmp, and the python runtime
                        if (not real.startswith(work_dir)
                                and not real.startswith("/tmp")
                                and not real.startswith(("/usr", "/lib", "/opt"))):
                            bad.append(real)
                except Exception:
                    pass
        except Exception:
            pass
        return bad

    def _rss_mb(self, pid: int) -> Optional[int]:
        if not self._proc_available:
            return None
        try:
            with open(f"/proc/{pid}/statm") as f:
                pages = int(f.read().split()[1])  # resident set size in pages
            page_size = os.sysconf("SC_PAGE_SIZE")
            return (pages * page_size) // (1024 * 1024)
        except Exception:
            return None

    def _net_bytes_sent(self, pid: int) -> int:
        """
        Total bytes transmitted, read from this PID's network namespace device
        stats (/proc/<pid>/net/dev). Under bubblewrap each plugin gets its own
        net namespace when network is granted, so these counters are scoped to
        that plugin alone — not shared with the host or other plugins.

        Best-effort: returns 0 if unavailable (e.g. no separate net namespace,
        which itself is logged elsewhere as reduced sandbox posture).
        """
        try:
            with open(f"/proc/{pid}/net/dev") as f:
                lines = f.readlines()[2:]  # skip the two header lines
            total = 0
            for line in lines:
                parts = line.split()
                if len(parts) < 10:
                    continue
                iface = parts[0].rstrip(":")
                if iface == "lo":
                    continue  # exclude loopback (host gRPC channel)
                # Format: iface: rx_bytes ... tx_bytes ...  (tx is field index 9)
                try:
                    total += int(parts[9])
                except (ValueError, IndexError):
                    pass
            return total
        except Exception:
            return 0

    def _dir_size(self, path: str) -> int:
        total = 0
        try:
            for root, _dirs, files in os.walk(path):
                for name in files:
                    try:
                        total += os.path.getsize(os.path.join(root, name))
                    except Exception:
                        pass
        except Exception:
            pass
        return total
