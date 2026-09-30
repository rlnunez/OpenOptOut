#!/usr/bin/env python3
"""
Plugin system smoke test — proves the plugin runtime actually works end to end.

This is the test roadmap item 2 asks for: run ONE real plugin through the real
gRPC protocol and confirm the round-trip works. It exercises, against real
sockets and the real generated protobuf stubs:

  1. The proto stubs import and the gRPC channel connects.
  2. Host -> Plugin: Initialize handshake returns the plugin's manifest.
  3. Host -> Plugin: Ping health check round-trips a nonce.
  4. Host -> Plugin: OnEvent delivers an event and the plugin's handler runs.
  5. Plugin -> Host: the plugin calls a host capability (storage.set/get) back
     over the HostService, and the value round-trips.
  6. Host -> Plugin: Shutdown stops the plugin cleanly.

What it does NOT test: the OS sandbox (bubblewrap/seccomp). Those require a
Linux host with those tools and are validated separately by
`preflight_sandbox.py`. This test isolates the *protocol and capability
plumbing* — the part most likely to have subtle bugs — so a green run here means
"the plugin can talk to the host and back" even before the sandbox is layered on.

Run inside the backend container (where grpcio + compiled stubs exist):
    python -m plugins.smoke_test
Exit code 0 = all steps passed.
"""

import sys
import time
import uuid
import logging
from concurrent import futures

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("smoke")


def _fail(msg):
    log.error("SMOKE TEST FAILED: %s", msg)
    sys.exit(1)


def main():
    # --- 0. Imports: prove the stubs and grpc are actually available ---------
    try:
        import grpc
    except ImportError:
        _fail("grpcio not installed — run inside the backend container")

    try:
        from .proto import plugin_pb2 as pb
        from .proto import plugin_pb2_grpc as pbg
    except Exception as e:
        _fail(f"proto stubs not importable ({e}); run the protoc step from the Dockerfile")

    from .broker import SessionRegistry, CapabilityBroker
    from .grpc_host import HostServiceImpl
    from .storage import make_storage_backend
    from .settings_access import PluginSettingsAccessor

    log.info("[0/6] imports OK — grpc + compiled stubs + host modules load")

    plugin_id = "smoke-plugin"
    session_token = uuid.uuid4().hex
    granted = {"receive_events", "storage"}
    methods = {"storage.get", "storage.set", "log"}

    # --- 1. Stand up the HostService (in-process, real gRPC server) ----------
    sessions = SessionRegistry()
    sessions.register(session_token, plugin_id, granted, methods=methods)

    storage = make_storage_backend("file", storage_root="/tmp/smoke_plugin_storage")
    settings = PluginSettingsAccessor(lambda: {}, lambda cfg: None)

    broker = CapabilityBroker(sessions, storage, settings)
    host_server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pbg.add_HostServiceServicer_to_server(HostServiceImpl(broker, pb), host_server)
    host_port = host_server.add_insecure_port("127.0.0.1:0")
    host_server.start()
    log.info("[1/6] HostService listening on 127.0.0.1:%d", host_port)

    # --- 2. Build a minimal real plugin using the SDK, serve it --------------
    # We import the SDK the way a plugin would. The SDK expects `from proto
    # import ...`; make that importable by putting the proto dir on sys.path.
    import os
    proto_dir = os.path.join(os.path.dirname(__file__), "proto")
    if proto_dir not in sys.path:
        sys.path.insert(0, proto_dir)
    sys.path.insert(0, os.path.dirname(__file__))  # so `import proto` resolves too

    from .sdk.openoptout_sdk import Plugin, manifest

    events_seen = []

    plugin = Plugin(manifest(
        id=plugin_id, name="Smoke Plugin", version="1.0.0", author="test",
        permissions=["receive_events", "storage"], hooks=["on_event"],
        methods=["storage.get", "storage.set", "log"], events=["tick"],
    ))

    @plugin.on_event
    def handle(ev):
        events_seen.append(ev.event_type)
        # Plugin -> Host capability call: store a value, read it back.
        plugin.storage.set("last_event", ev.event_type)
        got = plugin.storage.get("last_event")
        if got != ev.event_type:
            return {"ok": False, "message": f"storage round-trip mismatch: {got!r}"}
        plugin.log.info(f"handled event {ev.event_type}, storage round-trip OK")
        return {"ok": True}

    # Serve the plugin on its own gRPC server (mirrors Plugin.run without stdout)
    plugin_server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    from .sdk.openoptout_sdk import _PluginServicer
    servicer = _PluginServicer(plugin)
    pbg.add_PluginServiceServicer_to_server(servicer, plugin_server)
    plugin_port = plugin_server.add_insecure_port("127.0.0.1:0")
    plugin_server.start()
    servicer._server = plugin_server
    log.info("[2/6] Plugin service listening on 127.0.0.1:%d", plugin_port)

    # --- 3. Host connects to the plugin and drives the protocol --------------
    channel = grpc.insecure_channel(f"127.0.0.1:{plugin_port}")
    stub = pbg.PluginServiceStub(channel)

    try:
        # Initialize handshake
        init_resp = stub.Initialize(pb.InitializeRequest(
            host_version="1.0", session_token=session_token, host_port=host_port,
            granted_permissions={p: "true" for p in granted},
        ), timeout=5)
        if not init_resp.ok or init_resp.manifest.id != plugin_id:
            _fail(f"Initialize returned unexpected manifest: {init_resp.manifest.id!r}")
        log.info("[3/6] Initialize OK — plugin returned manifest id=%s hooks=%s",
                 init_resp.manifest.id, list(init_resp.manifest.hooks))

        # Ping
        nonce = 12345
        ping = stub.Ping(pb.PingRequest(nonce=nonce), timeout=5)
        if ping.nonce != nonce or not ping.healthy:
            _fail(f"Ping failed: nonce={ping.nonce} healthy={ping.healthy}")
        log.info("[4/6] Ping OK — nonce round-tripped, plugin reports healthy")

        # OnEvent — this triggers the plugin's handler, which calls back into
        # the HostService for storage. This is the full bidirectional round-trip.
        ev_resp = stub.OnEvent(pb.EventRequest(
            event_type="tick", entity_id="1", data={}), timeout=5)
        if not ev_resp.ok:
            _fail(f"OnEvent handler reported failure: {ev_resp.message}")
        if events_seen != ["tick"]:
            _fail(f"plugin handler did not run as expected: {events_seen}")
        log.info("[5/6] OnEvent OK — handler ran AND called host storage back "
                 "over gRPC (bidirectional round-trip proven)")

        # Verify the value actually landed in the host-side storage backend
        stored = storage.get(plugin_id, "last_event")
        if stored != "tick":
            _fail(f"host-side storage did not persist plugin write: {stored!r}")
        log.info("      confirmed: plugin's storage.set persisted host-side (value=%r)", stored)

        # Shutdown
        sd = stub.Shutdown(pb.ShutdownRequest(reason="smoke test complete"), timeout=5)
        if not sd.ok:
            _fail("Shutdown did not return ok")
        log.info("[6/6] Shutdown OK — plugin stopped cleanly")

    finally:
        channel.close()
        host_server.stop(grace=1)
        try:
            plugin_server.stop(grace=1)
        except Exception:
            pass

    print("\n==================================================")
    print("  PLUGIN SMOKE TEST PASSED")
    print("  Real gRPC round-trip works end to end:")
    print("  host->plugin (init/ping/event) and plugin->host (storage).")
    print("  NOTE: OS sandbox not tested here — see preflight_sandbox.py")
    print("==================================================")
    sys.exit(0)


if __name__ == "__main__":
    main()
