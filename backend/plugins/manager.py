"""
Plugin manager (host side).

Responsibilities:
  - Discover installed plugins on disk (each in its own dir with a manifest.json)
  - Launch enabled plugins as sandboxed subprocesses
  - Perform the gRPC handshake (Initialize) and issue a session token
  - Supervise: ping for liveness, enforce timeouts, kill on hang/crash,
    auto-disable after repeated crashes
  - Route host hook calls (fill_form, parse_email, on_event) to plugins that
    implement them, with per-call timeouts
  - Host the capability gRPC server (HostService) that plugins call back into

The manager never imports or executes plugin code in-process. Everything
crosses the process boundary via gRPC.
"""

import os
import sys
import json
import time
import uuid
import signal
import logging
import threading
import subprocess
from concurrent import futures
from dataclasses import dataclass, field
from typing import Optional, Union, List, Dict, Any, Tuple

from .permissions import PluginManifest, Permission
from .sandbox import detect_capabilities, build_sandboxed_command, log_sandbox_posture
from .broker import SessionRegistry, CapabilityBroker

log = logging.getLogger(__name__)

# Resolved lazily so importing this module doesn't require compiled protos.
_pb = None
_pb_grpc = None
_grpc = None


def _load_grpc():
    global _pb, _pb_grpc, _grpc
    if _pb is not None:
        return True
    try:
        import grpc
        from .proto import plugin_pb2 as pb
        from .proto import plugin_pb2_grpc as pb_grpc
        _grpc, _pb, _pb_grpc = grpc, pb, pb_grpc
        return True
    except Exception as e:
        log.error("gRPC/proto not available (%s). Run backend/plugins/proto/compile.sh "
                  "and install grpcio.", e)
        return False


@dataclass
class RunningPlugin:
    manifest: PluginManifest
    process: subprocess.Popen
    port: Union[int, str]
    session_token: str
    stub: object
    channel: object
    granted: set
    crash_count: int = 0
    last_started: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)
    provider_key: str = ""   # cached from EmailProviderInfo() once confirmed —
                             # lets the credential-lookup RPC verify a plugin
                             # only ever reads ITS OWN provider's token.
    run_dir: Optional[str] = None


class PluginManager:
    """
    Central coordinator. Construct once at startup with accessors, then call
    start(). Hook dispatch methods are called from the opt-out engine, email
    monitor, and scheduler.
    """

    MAX_CRASHES_BEFORE_DISABLE = 3

    def __init__(self, plugins_dir: str, session_factory,
                 storage_backend, settings_accessor,
                 host_bind_port: int = 0, pii_filter=None,
                 on_status_change=None):
        self.plugins_dir       = plugins_dir
        self.session_factory   = session_factory
        self.storage_backend   = storage_backend
        self.settings_accessor = settings_accessor
        self.host_bind_port    = host_bind_port
        self.pii_filter        = pii_filter          # callable(plugin_granted, fields)->fields
        self.on_status_change  = on_status_change     # callback(plugin_id, status, error)

        self.sessions = SessionRegistry()
        self.caps     = detect_capabilities()
        self.running: dict[str, RunningPlugin] = {}
        # plugin_id -> set(declared outbound_domains), used to gate http_fetch
        self.plugin_outbound_domains: dict[str, set] = {}
        self._host_server = None
        self._host_port   = None
        self._host_uds_path = None
        self._supervisor_thread = None
        self._stop = threading.Event()

        # Filesystem base for per-plugin runtime directories and Unix domain sockets
        self.runtime_base = "/tmp/ps-plugins"
        try:
            os.makedirs(self.runtime_base, exist_ok=True, mode=0o777)
        except Exception:
            pass

        # Runtime violation monitor (detect + auto-disable leak/escape attempts)
        from .monitor import ViolationMonitor
        self.monitor = ViolationMonitor(
            on_violation=self._on_violation,
            is_lockdown=self._is_lockdown,
        )

    def _is_lockdown(self) -> bool:
        """Global lockdown mode: ANY violation disables the plugin immediately."""
        try:
            from ..core.settings_store import load_settings
            return load_settings().get("plugins", {}).get("lockdown_mode", False)
        except Exception:
            return False

    # ---- lifecycle ----

    def start(self):
        """Start the capability server and launch all enabled plugins."""
        if not _load_grpc():
            log.warning("Plugin system inactive — gRPC unavailable.")
            return
        # Master kill-switch: if the whole system is denied, do not start.
        if self._is_denied():
            log.warning("Plugin system is DENIED by super admin — not starting.")
            return
        log_sandbox_posture(self.caps)
        self._start_host_server()
        self.monitor.start()
        self._launch_enabled_plugins()
        self._supervisor_thread = threading.Thread(target=self._supervise, daemon=True)
        self._supervisor_thread.start()
        log.info("Plugin manager started (host capability port %s)", self._host_port)

    def _is_denied(self) -> bool:
        try:
            from ..core.settings_store import load_settings
            return load_settings().get("plugins", {}).get("denied", False)
        except Exception:
            return False

    def stop(self):
        self._stop.set()
        try:
            self.monitor.stop()
        except Exception:
            pass
        for pid in list(self.running.keys()):
            self._stop_plugin(pid, reason="host shutdown")
        if self._host_server:
            self._host_server.stop(grace=2)

    # ---- host capability server ----

    def _start_host_server(self):
        from .grpc_host import HostServiceImpl
        from .extended_capabilities import ExtendedCapabilities

        extended = ExtendedCapabilities(
            session_factory=self.session_factory,
            audit_sink=self._audit_write,
            email_sender=self._email_sender,
            http_fetcher=self._http_fetcher,
        )
        broker = CapabilityBroker(
            self.sessions, self.storage_backend, self.settings_accessor,
            event_sink=self._on_plugin_event,
            method_violation_sink=self._on_method_violation,
            extended=extended,
            plugin_outbound_domains=self.plugin_outbound_domains,
            email_provider_key_lookup=lambda pid: (
                self.running[pid].provider_key if pid in self.running else None),
        )
        self._host_server = _grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        _pb_grpc.add_HostServiceServicer_to_server(HostServiceImpl(broker, _pb), self._host_server)
        self._host_port = self._host_server.add_insecure_port(f"127.0.0.1:{self.host_bind_port}")

        # Bind Unix domain socket for sandboxed plugin IPC across network namespaces
        uds_file = os.path.join(self.runtime_base, "host.sock")
        if os.path.exists(uds_file):
            try:
                os.unlink(uds_file)
            except OSError:
                pass
        try:
            self._host_server.add_insecure_port(f"unix:{uds_file}")
            try:
                os.chmod(uds_file, 0o666)
            except OSError:
                pass
            self._host_uds_path = uds_file
            log.info("HostService listening on 127.0.0.1:%s and UDS %s", self._host_port, self._host_uds_path)
        except Exception as e:
            log.warning("Could not bind HostService to UDS %s (%s); fallback to TCP", uds_file, e)
            self._host_uds_path = None

        self._host_server.start()

    def _audit_write(self, plugin_id: str, action: str, detail: str):
        """
        Records a high-risk-write audit entry (request status changes, email
        triggers, fetches, schedule changes). Detail strings are built entirely
        from IDs/enums/timestamps by extended_capabilities.py — never member PII.
        """
        from ..models.database import PluginAuditLog
        db = self.session_factory()
        try:
            db.add(PluginAuditLog(plugin_id=plugin_id, action=action, detail=detail))
            db.commit()
        except Exception as e:
            log.error("could not write plugin audit entry: %s", e)
        finally:
            db.close()

    def _email_sender(self, request_id: int):
        """
        Real implementation backing optout.trigger_email. Calls the SAME
        send_opt_out_email() the opt-out engine itself uses — same template,
        same SMTP config, same request_key. The plugin only ever supplies a
        request_id, so this cannot become a freeform email sender.
        """
        from ..models.database import RemovalRequest
        from ..core.optout_engine import send_opt_out_email
        from ..core.settings_store import load_settings
        db = self.session_factory()
        try:
            r = db.query(RemovalRequest).filter(RemovalRequest.id == request_id).first()
            if not r:
                return False, "request not found"
            cfg = load_settings()
            ok = send_opt_out_email(r.member, r.broker, r.request_key or "", None, cfg, db)
            return ok, "" if ok else "send failed (check SMTP configuration)"
        except Exception as e:
            return False, str(e)
        finally:
            db.close()

    def _http_fetcher(self, method: str, url: str, body: str, headers: dict):
        """
        Real implementation backing http.fetch. Runs in the HOST process (never
        the plugin), with a short timeout and a response-size cap so a plugin
        can't use this to exfiltrate large amounts of data or hang the host.
        """
        import urllib.request
        req = urllib.request.Request(url, data=(body.encode() if body else None),
                                     method=method, headers=headers or {})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read(1_048_576)  # 1MB cap
            return resp.status, raw.decode(errors="replace")

    def _on_plugin_event(self, source_plugin, event_type, data):
        """A plugin emitted an event — fan out to other plugins that receive events."""
        self.dispatch_event(event_type, entity_id=source_plugin, data=dict(data),
                            exclude=source_plugin)

    # ---- discovery ----

    def discover(self) -> list[PluginManifest]:
        """Valid plugins on disk, across all type folders (see plugins/layout.py)."""
        from .layout import scan
        found = []
        for f in scan(self.plugins_dir):
            if f.valid:
                found.append(f.manifest)
            else:
                log.warning("Plugin at %s is invalid: %s", f.path, f.errors)
        return found

    # ---- launch / stop ----

    @staticmethod
    def _load_manifest_for_row(row) -> "PluginManifest":
        """
        Prefer the manifest.json actually sitting at row.install_path over the
        JSON snapshot stored in the database at install time. install_path is,
        by definition, where the code that's about to run lives — the file
        next to it is the authoritative description of what that code needs,
        current as of right now; the DB copy is a point-in-time snapshot that
        goes stale the moment the on-disk plugin changes without a matching
        uninstall/reinstall. This matters most for the bundled email-provider
        plugins (copied from backend/plugins/bundled/), which ship as part of the app
        image and get updated on every rebuild — without this, a manifest
        fix (e.g. a corrected resource limit) would silently never take
        effect for an already-installed plugin, launched here again on every
        restart from the OLD stored copy, even after the file on disk (and
        the running container) had moved on.
        Falls back to the stored snapshot if the file is missing or invalid
        (e.g. an admin-uploaded plugin whose extracted files were removed) —
        never worse than the old always-use-the-snapshot behavior.
        """
        manifest_path = os.path.join(row.install_path or "", "manifest.json")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path) as f:
                    return PluginManifest.from_dict(json.load(f))
            except Exception as e:
                log.warning("Could not read manifest.json for %s at %s (%s) — "
                           "falling back to the stored copy", row.plugin_id, manifest_path, e)
        return PluginManifest.from_dict(json.loads(row.manifest_json))

    def _launch_enabled_plugins(self):
        from ..models.database import InstalledPlugin
        db = self.session_factory()
        try:
            enabled = db.query(InstalledPlugin).filter(InstalledPlugin.enabled == True).all()
            for row in enabled:
                try:
                    manifest = self._load_manifest_for_row(row)
                    if manifest.is_data_only or not manifest.entrypoint:
                        continue
                    granted  = set(json.loads(row.granted_permissions or "[]"))
                    self.launch_plugin(manifest, row.install_path, granted)
                except Exception as e:
                    log.error("Failed to launch plugin %s: %s", row.plugin_id, e)
        finally:
            db.close()

    def _verify_integrity(self, plugin_id: str, install_path: str):
        """
        Refuse to run a plugin whose files changed since a super admin installed
        or enabled it: a plugin rewriting its own code or adding program files,
        or anyone tampering with it on disk. Works whatever sandbox the host has.
        A plugin installed before hashes were recorded gets one on first launch.
        On a mismatch the plugin is disabled and flagged for re-approval.
        """
        from .layout import dir_hash
        from ..models.database import InstalledPlugin, PluginViolation, PluginAuditLog
        current = dir_hash(install_path)
        db = self.session_factory()
        try:
            row = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == plugin_id).first()
            if row is None:
                return
            if not row.code_hash:
                row.code_hash = current
                db.commit()
                log.info("Recorded code hash for plugin %s (installed before integrity checks)",
                         plugin_id)
                return
            if row.code_hash == current:
                return
            detail = "plugin files changed since it was installed or last enabled"
            row.enabled = False
            row.status = "disabled"
            row.needs_reapproval = True
            row.last_error = (detail[0].upper() + detail[1:] + "; not started. Review it and "
                              "enable it again to accept the change.")
            db.add(PluginViolation(plugin_id=plugin_id, vtype="code_changed", severity="critical",
                                   detail=detail, action_taken="disabled_pending_reapproval"))
            db.add(PluginAuditLog(plugin_id=plugin_id, action="violation",
                                  detail=f"[critical] code_changed: {detail} -> disabled_pending_reapproval"))
            db.commit()
        finally:
            db.close()
        log.error("Plugin %s: files at %s changed since install; refusing to launch",
                  plugin_id, install_path)
        raise PermissionError(f"plugin {plugin_id} failed its integrity check")

    def launch_plugin(self, manifest: PluginManifest, install_path: str, granted: set):
        """Launch a single plugin as a sandboxed subprocess and handshake."""
        if manifest.is_data_only or not manifest.entrypoint:
            # Declarative broker add-ons, language packs and themes are loaded by the host, never launched as processes.
            return
        if manifest.id in self.running:
            log.info("Plugin %s already running", manifest.id)
            return
        self._verify_integrity(manifest.id, install_path)

        session_token = uuid.uuid4().hex
        self.sessions.register(session_token, manifest.id, granted,
                               methods=set(manifest.methods))
        self.plugin_outbound_domains[manifest.id] = set(manifest.outbound_domains)

        entry = os.path.join(install_path, manifest.entrypoint)
        runner = os.path.join(os.path.dirname(__file__), "runner.py")
        allow_network = Permission.NETWORK.value in granted

        # Setup per-plugin runtime dir for Unix domain sockets
        plugin_run_dir = os.path.join(self.runtime_base, manifest.id)
        try:
            os.makedirs(plugin_run_dir, exist_ok=True, mode=0o777)
        except Exception:
            pass
        plugin_uds_path = os.path.join(plugin_run_dir, "plugin.sock")
        if os.path.exists(plugin_uds_path):
            try:
                os.unlink(plugin_uds_path)
            except OSError:
                pass

        base_cmd = [sys.executable, runner, "--plugin-file", entry,
                    "--plugin-id", manifest.id,
                    "--max-memory-mb", str(manifest.max_memory_mb)]
        if self._host_uds_path:
            base_cmd.extend(["--uds-path", plugin_uds_path])
        if allow_network:
            base_cmd.append("--allow-network")

        cmd, preexec = build_sandboxed_command(
            base_cmd, install_path, self.caps, allow_network, manifest,
            run_dir=plugin_run_dir, host_uds_path=self._host_uds_path,
        )

        env = {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": os.pathsep.join([
                os.path.join(os.path.dirname(__file__), "sdk"),   # openoptout_sdk (+ privacyshield_sdk alias)
                os.path.dirname(__file__),                        # plugins/ -> `proto` pkg
            ]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PS_SESSION_TOKEN": session_token,
            "PS_HOST_PORT": str(self._host_port or 0),
            "PS_HOST_UDS_PATH": self._host_uds_path or "",
            "PS_PLUGIN_UDS_PATH": plugin_uds_path if self._host_uds_path else "",
        }

        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env, preexec_fn=preexec,
                text=True, bufsize=1,
                cwd=install_path,   # never the API server's own directory
            )
        except Exception as e:
            log.error("Could not start plugin %s process: %s", manifest.id, e)
            self.sessions.revoke(session_token)
            self._set_status(manifest.id, "crashed", str(e))
            if os.path.isdir(plugin_run_dir):
                shutil.rmtree(plugin_run_dir, ignore_errors=True)
            return

        # Read the handshake line: "PLUGIN_READY <port>" or "PLUGIN_READY unix:<path>"
        endpoint = self._read_ready(proc, manifest.timeout_seconds)
        if endpoint is None:
            log.error("Plugin %s did not report ready — killing", manifest.id)
            self._kill(proc)
            self.sessions.revoke(session_token)
            self._set_status(manifest.id, "crashed", "no ready handshake")
            if os.path.isdir(plugin_run_dir):
                shutil.rmtree(plugin_run_dir, ignore_errors=True)
            return

        if isinstance(endpoint, int):
            target = f"127.0.0.1:{endpoint}"
        elif endpoint.startswith("unix:"):
            target = endpoint
        else:
            target = f"unix:{endpoint}"

        channel = _grpc.insecure_channel(target)
        stub = _pb_grpc.PluginServiceStub(channel)

        # Initialize the plugin
        try:
            resp = stub.Initialize(_pb.InitializeRequest(
                host_version="1.0", session_token=session_token,
                host_port=self._host_port or 0,
                granted_permissions={p: "true" for p in granted},
                host_uds_path=self._host_uds_path or "",
            ), timeout=manifest.timeout_seconds)
            if not resp.ok:
                raise RuntimeError(resp.error or "initialize failed")
        except Exception as e:
            log.error("Plugin %s initialize failed: %s", manifest.id, e)
            self._kill(proc); channel.close()
            self.sessions.revoke(session_token)
            self._set_status(manifest.id, "crashed", str(e))
            if os.path.isdir(plugin_run_dir):
                shutil.rmtree(plugin_run_dir, ignore_errors=True)
            return

        self.running[manifest.id] = RunningPlugin(
            manifest=manifest, process=proc, port=endpoint,
            session_token=session_token, stub=stub, channel=channel,
            granted=granted, last_started=time.time(),
            run_dir=plugin_run_dir,
        )
        # Register with the violation monitor (detect leak/escape attempts).
        # Heavy monitoring kicks in whenever a plugin runs with BOTH read_pii
        # and network granted — the combination that can exfiltrate member data.
        heavy = Permission.READ_PII.value in granted and Permission.NETWORK.value in granted
        try:
            self.monitor.watch(manifest.id, proc.pid, install_path, manifest.max_memory_mb,
                               heavy_monitoring=heavy)
        except Exception as e:
            log.debug("monitor.watch failed for %s: %s", manifest.id, e)
        self._set_status(manifest.id, "running", None)
        log.info("Plugin %s v%s launched (pid %s)%s", manifest.id, manifest.version, proc.pid,
                 " [HEAVY MONITORING: read_pii+network]" if heavy else "")

    def _read_ready(self, proc, timeout) -> Optional[Union[int, str]]:
        """Read the PLUGIN_READY handshake line with a timeout.
        Returns integer port or string UDS endpoint (e.g. 'unix:/path/to/sock')."""
        result = {"endpoint": None}
        def _reader():
            try:
                for line in proc.stdout:
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="replace")
                    line = line.strip()
                    if line.startswith("PLUGIN_READY"):
                        parts = line.split(None, 1)
                        if len(parts) > 1:
                            val = parts[1].strip()
                            if val.isdigit():
                                result["endpoint"] = int(val)
                            else:
                                result["endpoint"] = val
                        return
            except Exception:
                pass
        t = threading.Thread(target=_reader, daemon=True)
        t.start(); t.join(timeout)
        return result["endpoint"]

    def _stop_plugin(self, plugin_id: str, reason: str = ""):
        rp = self.running.pop(plugin_id, None)
        if not rp:
            return
        try:
            self.monitor.unwatch(plugin_id)
        except Exception:
            pass
        try:
            rp.stub.Shutdown(_pb.ShutdownRequest(reason=reason), timeout=3)
        except Exception:
            pass
        self._kill(rp.process)
        try: rp.channel.close()
        except Exception: pass
        self.sessions.revoke(rp.session_token)
        self.plugin_outbound_domains.pop(plugin_id, None)
        if rp.run_dir and os.path.isdir(rp.run_dir):
            try:
                shutil.rmtree(rp.run_dir, ignore_errors=True)
            except Exception:
                pass
        self._set_status(plugin_id, "stopped", None)
        log.info("Plugin %s stopped (%s)", plugin_id, reason)

    def _kill(self, proc):
        """Kill a process group hard."""
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            try: proc.kill()
            except Exception: pass

    # ---- supervision ----

    def _supervise(self):
        while not self._stop.wait(10):
            for pid, rp in list(self.running.items()):
                # Process died?
                if rp.process.poll() is not None:
                    log.warning("Plugin %s exited unexpectedly (code %s)", pid, rp.process.returncode)
                    self._handle_crash(pid, "process exited")
                    continue
                # Liveness ping
                try:
                    r = rp.stub.Ping(_pb.PingRequest(nonce=int(time.time())), timeout=5)
                    if not r.healthy:
                        raise RuntimeError("unhealthy ping")
                except Exception as e:
                    log.warning("Plugin %s failed liveness ping: %s", pid, e)
                    self._handle_crash(pid, f"ping failure: {e}")

    def _handle_crash(self, plugin_id: str, reason: str):
        rp = self.running.get(plugin_id)
        crash_count = (rp.crash_count + 1) if rp else 1
        self._stop_plugin(plugin_id, reason=f"crash: {reason}")
        self._record_crash(plugin_id, reason, crash_count)

        if crash_count >= self.MAX_CRASHES_BEFORE_DISABLE:
            log.error("Plugin %s crashed %d times — auto-disabling", plugin_id, crash_count)
            self._auto_disable(plugin_id, reason)
        else:
            # Try to relaunch
            self._relaunch(plugin_id, crash_count)

    def _relaunch(self, plugin_id: str, crash_count: int):
        from ..models.database import InstalledPlugin
        db = self.session_factory()
        try:
            row = db.query(InstalledPlugin).filter(
                InstalledPlugin.plugin_id == plugin_id).first()
            if row and row.enabled:
                manifest = self._load_manifest_for_row(row)
                granted  = set(json.loads(row.granted_permissions or "[]"))
                self.launch_plugin(manifest, row.install_path, granted)
                if plugin_id in self.running:
                    self.running[plugin_id].crash_count = crash_count
        finally:
            db.close()

    def _auto_disable(self, plugin_id: str, reason: str):
        from ..models.database import InstalledPlugin, PluginAuditLog
        db = self.session_factory()
        try:
            row = db.query(InstalledPlugin).filter(
                InstalledPlugin.plugin_id == plugin_id).first()
            if row:
                row.enabled = False
                row.status = "disabled"
                row.last_error = f"Auto-disabled after repeated crashes: {reason}"
                db.add(PluginAuditLog(plugin_id=plugin_id, action="auto_disabled", detail=reason))
                db.commit()
        finally:
            db.close()
        if self.on_status_change:
            self.on_status_change(plugin_id, "disabled", reason)

    # ---- violation handling ----

    def _on_method_violation(self, plugin_id: str, method: str):
        """
        Called by the broker when a plugin invokes a host method it did NOT
        declare in its manifest. This is a manifest-integrity breach: the plugin
        is reaching for capability surface it never disclosed. Policy (per admin
        choice): record the violation, raise the admin banner, disable the
        plugin, and require the method to be re-declared + re-approved before it
        can run again.
        """
        from ..models.database import PluginViolation, PluginAuditLog, InstalledPlugin
        detail = f"called undeclared host method '{method}'"
        db = self.session_factory()
        try:
            db.add(PluginViolation(
                plugin_id=plugin_id, vtype="undeclared_method",
                severity="critical", detail=detail,
                action_taken="disabled_pending_reapproval",
            ))
            db.add(PluginAuditLog(
                plugin_id=plugin_id, action="violation",
                detail=f"[critical] undeclared_method: {detail} -> disabled_pending_reapproval",
            ))
            # Flag the plugin as needing re-approval (locks re-enable until the
            # admin re-reviews the manifest's declared methods).
            row = db.query(InstalledPlugin).filter(
                InstalledPlugin.plugin_id == plugin_id).first()
            if row:
                row.needs_reapproval = True
            db.commit()
        except Exception as e:
            log.error("could not record method violation: %s", e)
        finally:
            db.close()

        self._stop_plugin(plugin_id, reason=f"undeclared method: {method}")
        self._disable_in_db(plugin_id,
                            f"Disabled — called undeclared method '{method}'. Re-approval required.")
        log.error("Plugin %s DISABLED — undeclared method '%s' (re-approval required)",
                  plugin_id, method)

    def _on_violation(self, violation):
        """
        Called by the monitor when a plugin attempts something disallowed.
        Default policy (safest): auto-disable the offending plugin immediately
        on the first violation. In lockdown mode this is identical (any
        violation disables), and we also record it as a lockdown action.
        """
        from ..models.database import PluginViolation, PluginAuditLog
        lockdown = False
        try:
            lockdown = self._is_lockdown()
        except Exception:
            pass
        action = "lockdown_disabled" if lockdown else "auto_disabled"

        # Persist the violation + audit entry
        db = self.session_factory()
        try:
            db.add(PluginViolation(
                plugin_id=violation.plugin_id, vtype=violation.vtype,
                severity=violation.severity, detail=violation.detail,
                action_taken=action,
            ))
            db.add(PluginAuditLog(
                plugin_id=violation.plugin_id, action="violation",
                detail=f"[{violation.severity}] {violation.vtype}: {violation.detail} -> {action}",
            ))
            db.commit()
        except Exception as e:
            log.error("could not record violation: %s", e)
        finally:
            db.close()

        # Stop the plugin and mark it disabled so it won't relaunch
        self._stop_plugin(violation.plugin_id, reason=f"violation: {violation.vtype}")
        self._disable_in_db(violation.plugin_id,
                            f"Auto-disabled: {violation.vtype} ({violation.detail})")
        log.error("Plugin %s AUTO-DISABLED due to violation: %s",
                  violation.plugin_id, violation.vtype)

    def _disable_in_db(self, plugin_id: str, reason: str):
        from ..models.database import InstalledPlugin
        db = self.session_factory()
        try:
            row = db.query(InstalledPlugin).filter(
                InstalledPlugin.plugin_id == plugin_id).first()
            if row:
                row.enabled = False
                row.status = "disabled"
                row.last_error = reason
                db.commit()
        finally:
            db.close()
        if self.on_status_change:
            self.on_status_change(plugin_id, "disabled", reason)

    def deny_all(self):
        """
        Master kill-switch. Immediately stop every running plugin. Called when
        the super admin denies the plugin system. Does not change enablement
        rows (that's handled by the settings/router layer) — this just halts
        execution right now.
        """
        log.warning("KILL-SWITCH: stopping all plugins immediately")
        for pid in list(self.running.keys()):
            self._stop_plugin(pid, reason="plugin system denied by admin")

    def stop_all_running(self):
        """Stop all running plugins without altering their enabled state."""
        for pid in list(self.running.keys()):
            self._stop_plugin(pid, reason="stop all")


    # ---- status bookkeeping ----

    def _set_status(self, plugin_id, status, error):
        from ..models.database import InstalledPlugin
        db = self.session_factory()
        try:
            row = db.query(InstalledPlugin).filter(
                InstalledPlugin.plugin_id == plugin_id).first()
            if row:
                row.status = status
                if status == "running":
                    from datetime import datetime
                    row.last_started = datetime.utcnow()
                if error:
                    row.last_error = error
                db.commit()
        finally:
            db.close()
        if self.on_status_change:
            self.on_status_change(plugin_id, status, error)

    def _record_crash(self, plugin_id, reason, crash_count):
        from ..models.database import InstalledPlugin, PluginAuditLog
        db = self.session_factory()
        try:
            row = db.query(InstalledPlugin).filter(
                InstalledPlugin.plugin_id == plugin_id).first()
            if row:
                row.crash_count = crash_count
                row.status = "crashed"
                row.last_error = reason
            db.add(PluginAuditLog(plugin_id=plugin_id, action="crashed", detail=reason))
            db.commit()
        finally:
            db.close()

    # ---- hook dispatch (called by the rest of the app) ----

    def dispatch_fill_form(self, broker: dict, page_html: str, fields=None,
                           fields_provider=None) -> Optional[dict]:
        """
        Ask plugins (that implement fill_form) to handle this broker. Returns the
        first handled response, or None if no plugin handled it.

        PII handling (defense-in-depth): prefer passing `fields_provider`, a
        zero-arg callable that returns the member's real field values. The real
        values are then pulled ONLY for a plugin that holds read_pii — a plugin
        without it never causes the raw PII to be materialized here at all. The
        older `fields` dict is still accepted for compatibility, but a plugin
        without read_pii gets it redacted to empty strings, same as before.
        """
        # The redacted view (keys only, empty values) — safe to build eagerly.
        if fields is not None:
            keys = list(fields.keys())
        elif fields_provider is not None:
            # We need the key set; get it from a real fetch, but we won't hand
            # the values to unpermitted plugins.
            _probe = fields_provider() or {}
            keys = list(_probe.keys())
        else:
            keys = []
        redacted = {k: "" for k in keys}

        _real_cache = {"v": None}
        def _real_fields():
            if _real_cache["v"] is None:
                _real_cache["v"] = (fields if fields is not None
                                    else (fields_provider() if fields_provider else {})) or {}
            return _real_cache["v"]

        for pid, rp in list(self.running.items()):
            if "fill_form" not in rp.manifest.hooks:
                continue
            # Only a read_pii plugin ever sees real values; others get redacted.
            granted_pii = Permission.READ_PII.value in rp.granted
            safe_fields = _real_fields() if granted_pii else redacted
            req = _pb.FillFormRequest(
                broker_id=str(broker.get("id", "")),
                broker_name=broker.get("name", ""),
                opt_out_url=broker.get("opt_out_url", ""),
                page_html=page_html[:100_000],
                fields=[_pb.MemberField(key=k, value=str(v)) for k, v in safe_fields.items()],
                broker_meta={k: str(v) for k, v in broker.get("meta", {}).items()},
            )
            try:
                resp = rp.stub.FillForm(req, timeout=rp.manifest.timeout_seconds)
                if resp.handled:
                    return {
                        "handled": True,
                        "actions": [{"action": a.action, "selector": a.selector,
                                     "value": a.value, "timeout_ms": a.timeout_ms,
                                     "optional": a.optional}
                                    for a in resp.actions],
                        "success_selector": resp.success_selector,
                        "needs_captcha": resp.needs_captcha,
                        "plugin_id": pid,
                    }
            except Exception as e:
                log.warning("fill_form dispatch to %s failed: %s", pid, e)
                self._handle_crash(pid, f"fill_form error: {e}")
        return None

    def dispatch_solve_captcha(self, challenge: dict, preferred_plugin_id: Optional[str] = None) -> Optional[dict]:
        """
        Ask plugins (that implement solve_captcha) to solve a CAPTCHA. Returns
        the first real result — {"solved": True, "token": ...} or
        {"defer_to_human": True} — or None if no solver plugin is installed
        (in which case the caller uses the human path).

        If preferred_plugin_id is specified, any matching running plugin is
        tried first before falling back to other registered solvers.
        """
        candidates = [
            (pid, rp) for pid, rp in list(self.running.items())
            if "solve_captcha" in rp.manifest.hooks
        ]
        if preferred_plugin_id:
            candidates.sort(key=lambda item: 0 if item[0] == preferred_plugin_id else 1)

        for pid, rp in candidates:
            req = _pb.SolveCaptchaRequest(
                challenge=_pb.CaptchaChallenge(
                    type=challenge.get("type", "other"),
                    site_key=challenge.get("site_key", ""),
                    page_url=challenge.get("page_url", ""),
                    screenshot=challenge.get("screenshot", b"") or b"",
                    meta={k: str(v) for k, v in challenge.get("meta", {}).items()},
                )
            )
            try:
                resp = rp.stub.SolveCaptcha(req, timeout=rp.manifest.timeout_seconds)
                # A plugin that defers or solves is a real answer; a plugin that
                # errors/does-nothing falls through to the next solver.
                if resp.solved or resp.defer_to_human:
                    return {
                        "solved": resp.solved, "token": resp.token,
                        "defer_to_human": resp.defer_to_human,
                        "error": resp.error, "plugin_id": pid,
                    }
            except Exception as e:
                log.warning("solve_captcha dispatch to %s failed: %s", pid, e)
                self._handle_crash(pid, f"solve_captcha error: {e}")
        return None

    def dispatch_email_provider_info(self, provider_key: str = "") -> Optional[dict]:
        """
        Ask a running email-provider plugin to describe itself — including its
        OAuth flow (auth/token URLs, scopes, PKCE), which the HOST executes. If
        provider_key is given, return the matching provider; otherwise the first
        email provider found. Returns a dict, or None if none is running.

        This is how an UPLOADED custom email plugin tells the host how to run its
        OAuth (the plugin describes; the host holds the secrets and executes).
        """
        for pid, rp in list(self.running.items()):
            if "email_provider" not in rp.manifest.hooks:
                continue
            try:
                info = rp.stub.EmailProviderInfo(_pb.EmailProviderInfoRequest(),
                                                 timeout=rp.manifest.timeout_seconds)
            except Exception as e:
                log.warning("email_provider_info dispatch to %s failed: %s", pid, e)
                self._handle_crash(pid, f"email_provider_info error: {e}")
                continue
            if provider_key and info.provider_key != provider_key:
                continue
            return {
                "plugin_id": pid,
                "provider_key": info.provider_key,
                "display_name": info.display_name,
                "auth_type": info.auth_type,
                "can_send": info.can_send,
                "can_receive": info.can_receive,
                "oauth_scopes": info.oauth_scopes,
                "notes": info.notes,
                "oauth_auth_url": info.oauth_auth_url,
                "oauth_token_url": info.oauth_token_url,
                "oauth_use_pkce": info.oauth_use_pkce,
                "oauth_extra_params": info.oauth_extra_params,
            }
        return None

    def dispatch_email_send(self, provider_key: str, account_ref: str,
                            to: list, cc: list, subject: str, body: str,
                            meta: dict = None) -> Optional[dict]:
        """
        Send an email through the matching email-provider plugin. The HOST supplies
        the recipient list (to/cc); the plugin sends ONLY to those and returns
        sent_to, which the host verifies against what it asked for — so a plugin
        can't add a hidden recipient at runtime (belt-and-suspenders with the
        static inspector). Returns the result dict, or None if no provider matches.
        """
        for pid, rp in list(self.running.items()):
            if "email_provider" not in rp.manifest.hooks:
                continue
            # Match the provider if a key is given.
            if provider_key:
                try:
                    info = rp.stub.EmailProviderInfo(_pb.EmailProviderInfoRequest(),
                                                     timeout=rp.manifest.timeout_seconds)
                    if info.provider_key != provider_key:
                        continue
                    rp.provider_key = info.provider_key   # cache for GetEmailCredentials
                except Exception:
                    continue
            req = _pb.EmailProviderSendRequest(
                account_ref=account_ref, to=list(to), cc=list(cc),
                subject=subject, body=body,
                meta={k: str(v) for k, v in (meta or {}).items()},
            )
            try:
                resp = rp.stub.EmailProviderSend(req, timeout=rp.manifest.timeout_seconds)
            except Exception as e:
                log.warning("email_send dispatch to %s failed: %s", pid, e)
                self._handle_crash(pid, f"email_send error: {e}")
                return {"ok": False, "error": str(e)}
            # RUNTIME recipient enforcement: the plugin must have sent ONLY to the
            # host-supplied recipients. Any extra address = reject and flag.
            intended = set(a.lower() for a in list(to) + list(cc))
            reported = set(a.lower() for a in resp.sent_to)
            extra = reported - intended
            if extra:
                log.error("email provider %s reported sending to UNDECLARED recipients %s "
                          "— rejecting and disabling", pid, extra)
                # An email provider sending to a recipient the host didn't supply is
                # exactly the exfiltration the trusted-class model guards against —
                # disable it immediately (belt-and-suspenders with the static inspector).
                self._handle_crash(pid, f"email provider sent to undeclared recipients: {extra}")
                return {"ok": False, "error": f"provider sent to undeclared recipients: {extra}"}
            return {"ok": resp.ok, "message_id": resp.message_id,
                    "sent_to": list(resp.sent_to), "error": resp.error, "plugin_id": pid}
        return None

    def dispatch_parse_email(self, email: dict, tracking_keys: list) -> Optional[dict]:
        for pid, rp in list(self.running.items()):
            if "parse_email" not in rp.manifest.hooks:
                continue
            req = _pb.ParseEmailRequest(
                message_id=email.get("message_id", ""),
                subject=email.get("subject", ""),
                from_addr=email.get("from_addr", ""),
                body_text=email.get("body_text", ""),
                body_html=email.get("body_html", ""),
                tracking_keys=tracking_keys,
            )
            try:
                resp = rp.stub.ParseEmail(req, timeout=rp.manifest.timeout_seconds)
                if resp.handled:
                    return {
                        "handled": True, "matched": resp.matched,
                        "matched_key": resp.matched_key, "status": resp.status,
                        "extracted": dict(resp.extracted), "plugin_id": pid,
                    }
            except Exception as e:
                log.warning("parse_email dispatch to %s failed: %s", pid, e)
                self._handle_crash(pid, f"parse_email error: {e}")
        return None

    def dispatch_event(self, event_type: str, entity_id: str = "", data: dict = None,
                       exclude: str = None):
        """Fire an event to all plugins that receive events. Fire-and-forget."""
        data = data or {}
        for pid, rp in list(self.running.items()):
            if pid == exclude:
                continue
            if "on_event" not in rp.manifest.hooks:
                continue
            req = _pb.EventRequest(
                event_type=event_type, entity_id=str(entity_id),
                data={k: str(v) for k, v in data.items()},
                timestamp=int(time.time()),
            )
            try:
                rp.stub.OnEvent(req, timeout=rp.manifest.timeout_seconds)
            except Exception as e:
                log.warning("on_event dispatch to %s failed: %s", pid, e)
                self._handle_crash(pid, f"on_event error: {e}")

    # ---- status query ----

    def status(self) -> dict:
        try:
            monitor_caps = self.monitor.capabilities()
        except Exception:
            monitor_caps = {"proc_inspection": False}
        return {
            "sandbox": {
                "posture": "full" if self.caps.is_fully_sandboxed else "partial",
                "controls": self.caps.summary(),
                "platform": self.caps.platform,
            },
            "monitor": monitor_caps,
            "lockdown_mode": self._is_lockdown(),
            "host_port": self._host_port,
            "host_uds_path": self._host_uds_path,
            "running": [
                {"plugin_id": pid, "name": rp.manifest.name,
                 "version": rp.manifest.version, "pid": rp.process.pid,
                 "crash_count": rp.crash_count, "hooks": rp.manifest.hooks,
                 "permissions": list(rp.granted)}
                for pid, rp in self.running.items()
            ],
        }


# ---- module-level singleton wiring ----

_manager: Optional[PluginManager] = None


def get_manager() -> Optional[PluginManager]:
    return _manager


def set_manager(m: PluginManager):
    global _manager
    _manager = m
