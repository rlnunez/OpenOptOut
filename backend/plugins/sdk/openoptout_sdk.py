"""
OpenOptOut Plugin SDK
=====================

The library plugin authors import. It hides all the gRPC plumbing so a plugin
is just a manifest plus a few handler functions.

Minimal example (plugin.py):

    from openoptout_sdk import Plugin, manifest

    plugin = Plugin(manifest(
        id="hello-world",
        name="Hello World",
        version="1.0.0",
        author="you",
        permissions=["receive_events", "storage"],
        hooks=["on_event"],
    ))

    @plugin.on_event
    def handle_event(event):
        plugin.log.info(f"Got event: {event.event_type}")
        count = int(plugin.storage.get("count") or "0") + 1
        plugin.storage.set("count", str(count))
        return {"ok": True}

    if __name__ == "__main__":
        plugin.run()

The SDK connects back to the host's capability service using the session token
and host port passed in at Initialize. All capability calls are permission-
gated on the host side — if your manifest didn't request a permission, the
corresponding SDK call will raise PermissionDenied.
"""

import os
import sys
import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Any

# These imports resolve once the proto stubs are compiled (compile.sh).
try:
    import grpc
    try:
        from proto import plugin_pb2 as pb
        from proto import plugin_pb2_grpc as pb_grpc
    except ImportError:
        # Fallback if proto directory is relative to plugins package
        from ..proto import plugin_pb2 as pb
        from ..proto import plugin_pb2_grpc as pb_grpc
    _GRPC_AVAILABLE = True
except Exception:  # pragma: no cover - allows importing SDK without grpc for docs
    _GRPC_AVAILABLE = False
    pb = None
    pb_grpc = None


class PermissionDenied(Exception):
    pass


# ---- Manifest helper ----

def manifest(id, name, version, author, description="", permissions=None,
             hooks=None, methods=None, events=None, outbound_domains=None,
             api_version="1.0", max_memory_mb=256,
             max_cpu_seconds=30, timeout_seconds=20, type="") -> dict:
    return {
        "id": id, "name": name, "version": version, "author": author,
        "type": type,
        "description": description, "permissions": permissions or [],
        "hooks": hooks or [], "methods": methods or [],
        "events": events or [], "outbound_domains": outbound_domains or [],
        "api_version": api_version,
        "max_memory_mb": max_memory_mb, "max_cpu_seconds": max_cpu_seconds,
        "timeout_seconds": timeout_seconds,
    }


# ---- Event / request wrappers (friendly views over protobuf) ----

@dataclass
class Event:
    event_type: str
    entity_id: str
    data: dict
    timestamp: int


@dataclass
class CaptchaChallenge:
    """A CAPTCHA challenge passed to a solve_captcha handler."""
    type: str           # "recaptcha_v2" | "recaptcha_v3" | "hcaptcha" | "image" | "other"
    site_key: str
    page_url: str
    screenshot: bytes
    meta: dict


@dataclass
class EmailMessage:
    message_id: str
    subject: str
    from_addr: str
    body_text: str
    body_html: str
    tracking_keys: list


@dataclass
class FormContext:
    broker_id: str
    broker_name: str
    opt_out_url: str
    page_html: str
    fields: dict          # key -> value (empty if no read_pii)
    broker_meta: dict
    current_url: str = ""
    page_title: str = ""
    has_iframes: bool = False
    stage_index: int = 0


@dataclass
class FormResult:
    """What a fill_form handler returns."""
    handled: bool = True
    actions: list = field(default_factory=list)  # list of dict actions
    success_selector: str = ""
    error: str = ""
    next_stage: bool = False

    @staticmethod
    def fill(selector, value, timeout_ms=5000):
        return {"action": "fill", "selector": selector, "value": value, "timeout_ms": timeout_ms}

    @staticmethod
    def click(selector, timeout_ms=5000):
        return {"action": "click", "selector": selector, "value": "", "timeout_ms": timeout_ms}

    @staticmethod
    def click_matching(selector, text, timeout_ms=5000):
        return {"action": "click_matching", "selector": selector, "value": text, "timeout_ms": timeout_ms}

    @staticmethod
    def press(selector, key="Enter", timeout_ms=5000):
        return {"action": "press", "selector": selector, "value": key, "timeout_ms": timeout_ms}

    @staticmethod
    def frame(selector=""):
        return {"action": "frame", "selector": selector, "value": "", "timeout_ms": 1000}

    @staticmethod
    def scroll(selector="", timeout_ms=5000):
        return {"action": "scroll", "selector": selector, "value": "", "timeout_ms": timeout_ms}

    @staticmethod
    def select(selector, value, timeout_ms=5000):
        return {"action": "select", "selector": selector, "value": value, "timeout_ms": timeout_ms}

    @staticmethod
    def check(selector, timeout_ms=5000):
        return {"action": "check", "selector": selector, "value": "", "timeout_ms": timeout_ms}

    @staticmethod
    def wait_for(selector, timeout_ms=8000):
        return {"action": "wait_for", "selector": selector, "value": "", "timeout_ms": timeout_ms}

    @staticmethod
    def wait(timeout_ms=1000):
        return {"action": "wait", "selector": "", "value": "", "timeout_ms": timeout_ms}

    @staticmethod
    def expect_success(selector="", text="", timeout_ms=8000):
        return {"action": "expect_success", "selector": selector, "value": text, "timeout_ms": timeout_ms}


# ---- Host capability client ----

class _HostClient:
    """Talks back to the host's HostService. All calls are permission-gated host-side."""

    def __init__(self, host_target: Any, session_token: str, plugin_id: str):
        self._token = session_token
        self._pid   = plugin_id
        if isinstance(host_target, str) and (host_target.startswith("unix:") or "/" in host_target):
            addr = host_target if host_target.startswith("unix:") else f"unix:{host_target}"
        else:
            addr = f"127.0.0.1:{host_target}"
        self._channel = grpc.insecure_channel(addr)
        self._stub = pb_grpc.HostServiceStub(self._channel)

    def _auth(self):
        return pb.Auth(session_token=self._token, plugin_id=self._pid)

    # storage
    def storage_get(self, key):
        r = self._stub.StorageGet(pb.StorageGetRequest(auth=self._auth(), key=key))
        return r.value if r.found else None

    def storage_set(self, key, value):
        self._stub.StorageSet(pb.StorageSetRequest(auth=self._auth(), key=key, value=str(value)))

    def storage_delete(self, key):
        self._stub.StorageDelete(pb.StorageDeleteRequest(auth=self._auth(), key=key))

    def storage_list(self, prefix=""):
        r = self._stub.StorageList(pb.StorageListRequest(auth=self._auth(), prefix=prefix))
        return list(r.keys)

    # settings
    def setting_get(self, key):
        r = self._stub.SettingGet(pb.SettingGetRequest(auth=self._auth(), key=key))
        return r.value if r.found else None

    def setting_set(self, key, value):
        self._stub.SettingSet(pb.SettingSetRequest(auth=self._auth(), key=key, value=str(value)))

    # email-provider credentials
    def get_email_credentials(self, account_ref):
        """Returns {"access_token": str, "token_type": str} or None. Only
        works for an email-provider plugin asking about its OWN account —
        see broker.py's email_credentials_get for the enforcement."""
        r = self._stub.GetEmailCredentials(
            pb.GetEmailCredentialsRequest(auth=self._auth(), account_ref=account_ref))
        if not r.found:
            return None
        return {"access_token": r.access_token, "token_type": r.token_type or "Bearer"}

    # log
    def log(self, level, message):
        try:
            self._stub.Log(pb.LogRequest(auth=self._auth(), level=level, message=message))
        except Exception:
            pass  # never let logging failure crash a plugin

    # events
    def emit_event(self, event_type, data):
        self._stub.EmitEvent(pb.HostEventRequest(auth=self._auth(), event_type=event_type,
                                                 data={k: str(v) for k, v in (data or {}).items()}))

    # broker read
    def broker_get(self, broker_id):
        r = self._stub.BrokerGet(pb.BrokerGetRequest(auth=self._auth(), broker_id=broker_id))
        return _broker_to_dict(r) if r.found else None

    def broker_list(self, limit=100):
        r = self._stub.BrokerList(pb.BrokerListRequest(auth=self._auth(), limit=limit))
        return [_broker_to_dict(b) for b in r.brokers]

    def broker_history(self, broker_id):
        r = self._stub.BrokerHistory(pb.BrokerHistoryRequest(auth=self._auth(), broker_id=broker_id))
        if not r.found:
            return None
        return {"total_requests": r.total_requests, "confirmed_count": r.confirmed_count,
                "failed_count": r.failed_count, "pending_count": r.pending_count}

    # request lifecycle
    def request_get_status(self, request_id):
        r = self._stub.RequestGetStatus(pb.RequestGetStatusRequest(auth=self._auth(), request_id=request_id))
        if not r.found:
            return None
        return {"request_id": r.request_id, "status": r.status, "method_used": r.method_used,
                "sent_at": r.sent_at, "confirmed_at": r.confirmed_at, "recheck_after": r.recheck_after}

    def request_mark(self, which, request_id, reason=""):
        req = pb.RequestMarkRequest(auth=self._auth(), request_id=request_id, reason=reason)
        stub_method = {"sent": self._stub.RequestMarkSent,
                      "confirmed": self._stub.RequestMarkConfirmed,
                      "failed": self._stub.RequestMarkFailed}[which]
        r = stub_method(req)
        return {"ok": r.ok, "error": r.error, "previous_status": r.previous_status, "new_status": r.new_status}

    # constrained opt-out email trigger
    def trigger_optout_email(self, request_id):
        r = self._stub.TriggerOptoutEmail(pb.TriggerOptoutEmailRequest(auth=self._auth(), request_id=request_id))
        return {"ok": r.ok, "error": r.error}

    # host-mediated HTTP fetch
    def http_fetch(self, method, url, body="", headers=None):
        r = self._stub.HttpFetch(pb.HttpFetchRequest(
            auth=self._auth(), method=method, url=url, body=body,
            headers={k: str(v) for k, v in (headers or {}).items()}))
        return {"ok": r.ok, "error": r.error, "status_code": r.status_code, "body": r.body}

    # custom recheck scheduling
    def schedule_set_recheck(self, request_id, recheck_after_ts, reason=""):
        r = self._stub.ScheduleSetRecheck(pb.ScheduleSetRecheckRequest(
            auth=self._auth(), request_id=request_id,
            recheck_after_ts=int(recheck_after_ts), reason=reason))
        return {"ok": r.ok, "error": r.error, "previous_recheck": r.previous_recheck, "new_recheck": r.new_recheck}


def _broker_to_dict(b):
    return {"broker_id": b.broker_id, "name": b.name, "method": b.method,
            "difficulty": b.difficulty, "status": b.status}


class _StorageProxy:
    def __init__(self, client): self._c = client
    def get(self, key): return self._c.storage_get(key)
    def set(self, key, value): self._c.storage_set(key, value)
    def delete(self, key): self._c.storage_delete(key)
    def list(self, prefix=""): return self._c.storage_list(prefix)


class _SettingsProxy:
    def __init__(self, client): self._c = client
    def get(self, key): return self._c.setting_get(key)
    def set(self, key, value): self._c.setting_set(key, value)


class _LogProxy:
    def __init__(self, client): self._c = client
    def debug(self, m): self._c.log("debug", m)
    def info(self, m): self._c.log("info", m)
    def warning(self, m): self._c.log("warning", m)
    def error(self, m): self._c.log("error", m)


class _BrokerProxy:
    """Read-only broker lookups. Never returns member PII — only broker fields."""
    def __init__(self, client): self._c = client
    def get(self, broker_id): return self._c.broker_get(broker_id)
    def list(self, limit=100): return self._c.broker_list(limit)
    def history(self, broker_id): return self._c.broker_history(broker_id)


class _RequestProxy:
    """
    Removal-request status reads/writes. Reads return status/timestamps only —
    never member PII. Writes (mark_sent/confirmed/failed) require the
    request_write permission and are diff-logged on the host's audit trail.
    """
    def __init__(self, client): self._c = client
    def get_status(self, request_id): return self._c.request_get_status(request_id)
    def mark_sent(self, request_id, reason=""): return self._c.request_mark("sent", request_id, reason)
    def mark_confirmed(self, request_id, reason=""): return self._c.request_mark("confirmed", request_id, reason)
    def mark_failed(self, request_id, reason=""): return self._c.request_mark("failed", request_id, reason)


class _OptoutProxy:
    """
    Constrained opt-out actions. trigger_email sends the EXISTING opt-out email
    template for one pending request via the host's own SMTP config — there is
    no way to supply custom subject/body/recipient through this API.
    """
    def __init__(self, client): self._c = client
    def trigger_email(self, request_id): return self._c.trigger_optout_email(request_id)


class _HttpProxy:
    """
    Host-mediated HTTP fetch. The HOST makes the request, not the plugin — the
    plugin never gets a raw socket. Restricted to domains declared in the
    plugin's manifest outbound_domains.
    """
    def __init__(self, client): self._c = client
    def get(self, url, headers=None): return self._c.http_fetch("GET", url, "", headers)
    def post(self, url, body="", headers=None): return self._c.http_fetch("POST", url, body, headers)


class _ScheduleProxy:
    """Set a custom recheck-after time for one confirmed request. Diff-logged."""
    def __init__(self, client): self._c = client
    def set_recheck(self, request_id, recheck_after_ts, reason=""):
        return self._c.schedule_set_recheck(request_id, recheck_after_ts, reason)


# ---- The Plugin object ----

class Plugin:
    """
    The main entry point plugin authors instantiate. Register handlers with the
    decorators, then call run() to start serving the host.
    """

    def __init__(self, manifest_dict: dict):
        self.manifest = manifest_dict
        self._handlers: dict[str, Callable] = {}
        self._host: Optional[_HostClient] = None
        self.storage: Optional[_StorageProxy] = None
        self.settings: Optional[_SettingsProxy] = None
        self.brokers: Optional["_BrokerProxy"] = None
        self.requests: Optional["_RequestProxy"] = None
        self.optout: Optional["_OptoutProxy"] = None
        self.http: Optional["_HttpProxy"] = None
        self.schedule: Optional["_ScheduleProxy"] = None
        self.log = logging.getLogger(manifest_dict.get("id", "plugin"))

    # ---- decorators for the three hooks ----

    def on_event(self, fn):
        self._handlers["on_event"] = fn
        return fn

    def fill_form(self, fn):
        self._handlers["fill_form"] = fn
        return fn

    def parse_email(self, fn):
        self._handlers["parse_email"] = fn
        return fn

    def solve_captcha(self, fn):
        """Register a CAPTCHA solver. fn receives a challenge object (type,
        site_key, page_url, screenshot, meta) and returns a dict:
          {"solved": True, "token": "..."}         to inject a solution, or
          {"defer_to_human": True}                  to hand to the human path, or
          {"solved": False, "error": "..."}         on failure."""
        self._handlers["solve_captcha"] = fn
        return fn

    def email_provider(self, info=None):
        """
        Register an email-provider adapter. Use as @plugin.email_provider(info={...})
        where info describes the provider (provider_key, display_name, auth_type,
        can_send, can_receive, oauth_scopes, notes). Then register the operations:
          @plugin.email_send      -> fn(req_dict) -> {"ok":bool,"message_id":str,"sent_to":[...]}
          @plugin.email_list      -> fn(req_dict) -> {"ok":bool,"messages":[...]}
        The host controls recipients and verifies what the plugin reports sending to.
        """
        self._email_info = info or {}
        def deco(fn):
            self._handlers["email_provider"] = fn
            return fn
        # allow bare @plugin.email_provider (no info) too
        if callable(info):
            fn = info; self._email_info = {}; self._handlers["email_provider"] = fn
            return fn
        return deco

    def email_send(self, fn):
        self._handlers["email_send"] = fn
        return fn

    def email_list(self, fn):
        self._handlers["email_list"] = fn
        return fn

    # ---- connect host capabilities once handshake provides the token ----

    def _attach_host(self, host_port: int, session_token: str, host_uds_path: str = ""):
        uds = host_uds_path or os.getenv("OP_HOST_UDS_PATH") or os.getenv("PS_HOST_UDS_PATH", "")
        target = uds if uds else host_port
        self._host = _HostClient(target, session_token, self.manifest["id"])
        self.storage  = _StorageProxy(self._host)
        self.settings = _SettingsProxy(self._host)
        self.log = _LogProxy(self._host)
        self.brokers  = _BrokerProxy(self._host)
        self.requests = _RequestProxy(self._host)
        self.optout   = _OptoutProxy(self._host)
        self.http     = _HttpProxy(self._host)
        self.schedule = _ScheduleProxy(self._host)

    def get_email_credentials(self, account_ref):
        """For email-provider plugins only: the CURRENT access token for
        account_ref (already refreshed host-side if it needed to be), or None
        if that account isn't connected or belongs to a different provider
        than this plugin. This is the intended way to get your own account's
        token — plugin.settings.get() will always refuse anything that looks
        like a credential, on purpose, for every plugin including this one."""
        return self._host.get_email_credentials(account_ref)

    def run(self):
        """Start the plugin gRPC server and serve until shutdown."""
        if not _GRPC_AVAILABLE:
            print("ERROR: grpc not available. Run compile.sh and install grpcio.", file=sys.stderr)
            sys.exit(1)
        import threading
        try:
            threading.stack_size(512 * 1024)
        except (ValueError, RuntimeError, AttributeError):
            pass

        from concurrent import futures
        server_options = [
            ("grpc.max_concurrent_streams", 4),
            ("grpc.so_reuseport", 0),
        ]
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=4), options=server_options)
        servicer = _PluginServicer(self)
        pb_grpc.add_PluginServiceServicer_to_server(servicer, server)

        uds_path = os.getenv("OP_PLUGIN_UDS_PATH") or os.getenv("PS_PLUGIN_UDS_PATH")
        if uds_path:
            os.makedirs(os.path.dirname(uds_path), exist_ok=True)
            if os.path.exists(uds_path):
                try:
                    os.unlink(uds_path)
                except OSError:
                    pass
            server.add_insecure_port(f"unix:{uds_path}")
            try:
                os.chmod(uds_path, 0o666)  # nosec B103 -- UDS socket requires read/write access across sandbox namespace
            except OSError:
                pass
            server.start()
            print(f"PLUGIN_READY unix:{uds_path}", flush=True)
        else:
            # Bind to an ephemeral local port; report it on stdout for the host.
            port = server.add_insecure_port("127.0.0.1:0")
            server.start()
            # Handshake line the host reads from stdout:
            print(f"PLUGIN_READY {port}", flush=True)

        servicer._server = server
        server.wait_for_termination()


# ---- gRPC servicer bridging protobuf <-> handler functions ----

class _PluginServicer:
    def __init__(self, plugin: Plugin):
        self.plugin = plugin
        self._server = None

    def Initialize(self, request, context):
        m = self.plugin.manifest
        uds_path = getattr(request, "host_uds_path", "") or os.getenv("OP_HOST_UDS_PATH") or os.getenv("PS_HOST_UDS_PATH", "")
        self.plugin._attach_host(request.host_port, request.session_token, host_uds_path=uds_path)
        return pb.InitializeResponse(
            ok=True,
            manifest=pb.Manifest(
                id=m["id"], name=m["name"], version=m["version"],
                author=m["author"], description=m.get("description", ""),
                permissions=m.get("permissions", []), hooks=m.get("hooks", []),
                api_version=m.get("api_version", "1.0"),
            ),
        )

    def Ping(self, request, context):
        return pb.PingResponse(nonce=request.nonce, healthy=True)

    def FillForm(self, request, context):
        fn = self.plugin._handlers.get("fill_form")
        if not fn:
            return pb.FillFormResponse(handled=False)
        bmeta = dict(request.broker_meta)
        ctx = FormContext(
            broker_id=request.broker_id, broker_name=request.broker_name,
            opt_out_url=request.opt_out_url, page_html=request.page_html,
            fields={f.key: f.value for f in request.fields},
            broker_meta=bmeta,
            current_url=bmeta.get("current_url", request.opt_out_url),
            page_title=bmeta.get("page_title", ""),
            has_iframes=bmeta.get("has_iframes") in ("True", "true", "1", True),
            stage_index=int(bmeta.get("stage_index", 0) or 0),
        )
        try:
            result = fn(ctx)
        except Exception as e:
            return pb.FillFormResponse(handled=False, error=str(e))
        if isinstance(result, FormResult):
            actions = [pb.BrowserAction(action=a["action"], selector=a["selector"],
                                        value=a.get("value", ""), timeout_ms=a.get("timeout_ms", 5000))
                       for a in result.actions]
            return pb.FillFormResponse(handled=result.handled, actions=actions,
                                       success_selector=result.success_selector, error=result.error)
        return pb.FillFormResponse(handled=False)

    def ParseEmail(self, request, context):
        fn = self.plugin._handlers.get("parse_email")
        if not fn:
            return pb.ParseEmailResponse(handled=False)
        msg = EmailMessage(
            message_id=request.message_id, subject=request.subject,
            from_addr=request.from_addr, body_text=request.body_text,
            body_html=request.body_html, tracking_keys=list(request.tracking_keys),
        )
        try:
            result = fn(msg) or {}
        except Exception as e:
            return pb.ParseEmailResponse(handled=False)
        return pb.ParseEmailResponse(
            handled=result.get("handled", True),
            matched=result.get("matched", False),
            matched_key=result.get("matched_key", ""),
            status=result.get("status", ""),
            extracted={k: str(v) for k, v in result.get("extracted", {}).items()},
        )

    def OnEvent(self, request, context):
        fn = self.plugin._handlers.get("on_event")
        if not fn:
            return pb.EventResponse(ok=True)
        ev = Event(event_type=request.event_type, entity_id=request.entity_id,
                   data=dict(request.data), timestamp=request.timestamp)
        try:
            result = fn(ev) or {}
        except Exception as e:
            return pb.EventResponse(ok=False, message=str(e))
        return pb.EventResponse(ok=result.get("ok", True), message=result.get("message", ""))

    def SolveCaptcha(self, request, context):
        fn = self.plugin._handlers.get("solve_captcha")
        if not fn:
            # No solver registered — defer to the host's human path.
            return pb.SolveCaptchaResponse(solved=False, defer_to_human=True)
        ch = request.challenge
        challenge = CaptchaChallenge(
            type=ch.type, site_key=ch.site_key, page_url=ch.page_url,
            screenshot=ch.screenshot, meta=dict(ch.meta),
        )
        try:
            result = fn(challenge) or {}
        except Exception as e:
            return pb.SolveCaptchaResponse(solved=False, error=str(e))
        return pb.SolveCaptchaResponse(
            solved=bool(result.get("solved", False)),
            token=result.get("token", ""),
            defer_to_human=bool(result.get("defer_to_human", False)),
            error=result.get("error", ""),
        )

    def EmailProviderInfo(self, request, context):
        info = getattr(self.plugin, "_email_info", {}) or {}
        return pb.EmailProviderInfoResponse(
            provider_key=info.get("provider_key", ""),
            display_name=info.get("display_name", ""),
            auth_type=info.get("auth_type", "oauth"),
            can_send=bool(info.get("can_send", True)),
            can_receive=bool(info.get("can_receive", False)),
            oauth_scopes=info.get("oauth_scopes", ""),
            notes=info.get("notes", ""),
        )

    def EmailProviderSend(self, request, context):
        fn = self.plugin._handlers.get("email_send")
        if not fn:
            return pb.EmailProviderSendResponse(ok=False, error="no email_send handler")
        req = {
            "account_ref": request.account_ref,
            "to": list(request.to), "cc": list(request.cc),
            "subject": request.subject, "body": request.body,
            "meta": dict(request.meta),
        }
        try:
            r = fn(req) or {}
        except Exception as e:
            return pb.EmailProviderSendResponse(ok=False, error=str(e) or type(e).__name__)
        return pb.EmailProviderSendResponse(
            ok=bool(r.get("ok", False)), message_id=r.get("message_id", ""),
            sent_to=list(r.get("sent_to", [])), error=r.get("error", ""),
        )

    def EmailProviderList(self, request, context):
        fn = self.plugin._handlers.get("email_list")
        if not fn:
            return pb.EmailProviderListResponse(ok=False, error="no email_list handler")
        req = {"account_ref": request.account_ref,
               "max_results": request.max_results, "since_ts": request.since_ts}
        try:
            r = fn(req) or {}
        except Exception as e:
            return pb.EmailProviderListResponse(ok=False, error=str(e))
        msgs = []
        for m in r.get("messages", []):
            im = pb.InboundMessage(
                message_id=m.get("message_id", ""),
                subject=m.get("subject", ""), snippet=m.get("snippet", ""),
                received_ts=int(m.get("received_ts", 0)),
            )
            setattr(im, "from", m.get("from", ""))  # 'from' is a Python keyword
            msgs.append(im)
        return pb.EmailProviderListResponse(ok=bool(r.get("ok", False)),
                                            messages=msgs, error=r.get("error", ""))

    def Shutdown(self, request, context):
        if self._server:
            self._server.stop(grace=2)
        return pb.ShutdownResponse(ok=True)
