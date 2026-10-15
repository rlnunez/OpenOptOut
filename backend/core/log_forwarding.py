"""
Log forwarding: copies of OpenOptOut's log lines sent to a central server.

Kinds:
  syslog      RFC 5424 over UDP, TCP or TLS (rsyslog, syslog-ng, Graylog, Splunk
              and most SIEMs accept it)
  otlp        OpenTelemetry logs over HTTP/JSON (POST <endpoint>/v1/logs):
              an OpenTelemetry Collector, Grafana Alloy, Loki 3, Graylog 6.1+,
              Splunk through its collector, and others
  loki        Grafana Loki's own push API (POST <endpoint>/loki/api/v1/push)
  splunk_hec  Splunk HTTP Event Collector (POST <endpoint>/services/collector/event)

What leaves: the same lines the System logs page shows, after the same
scrubbing (tokens, passwords, secrets), plus email addresses and phone numbers
replaced with [email] and [number]. Logs are written to hold no personal
details in the first place (AGENTS.md); this is a second net, not the first.

Settings (settings.json "observability.log_forwarding"), set by a super admin:
  [{"id", "name", "kind", "host", "port", "transport", "endpoint", "level",
    "headers_enc", "token_enc", "enabled", "verify_tls"}]

Lines are queued (at most 10,000; older ones are dropped and counted when the
server can't keep up) and sent by a background thread, so a slow or
unreachable server never slows OpenOptOut down.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import socket
import ssl
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

log = logging.getLogger(__name__)

KINDS = {"syslog": "Syslog", "otlp": "OpenTelemetry (OTLP)", "loki": "Grafana Loki",
         "splunk_hec": "Splunk HTTP Event Collector"}
TRANSPORTS = ("udp", "tcp", "tls")
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
QUEUE_MAX = 10000
BATCH = 200
FLUSH_SECONDS = 2.0

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")
_SEVERITY = {"DEBUG": 7, "INFO": 6, "WARNING": 4, "ERROR": 3, "CRITICAL": 2}
_OTLP_SEVERITY = {"DEBUG": 5, "INFO": 9, "WARNING": 13, "ERROR": 17, "CRITICAL": 21}

STATS: Dict[str, int] = {"sent": 0, "dropped": 0, "failed_batches": 0}
LAST_ERROR: Dict[str, str] = {}

# Replaced in tests: (destination, list of records) -> None, raising on failure.
SENDER: Optional[Callable] = None
HOSTNAME = socket.gethostname()[:64] or "openoptout"


def scrub(msg: str) -> str:
    from .logging_config import sanitize_log_message
    return _PHONE.sub("[number]", _EMAIL.sub("[email]", sanitize_log_message(msg)))


def _encrypt(v: str) -> str:
    from .oauth_engine import _encrypt as e
    return e(v) if v else ""


def _decrypt(v: str) -> str:
    from .oauth_engine import _decrypt as d
    return d(v) if v else ""


def destinations(settings: Optional[dict] = None) -> List[dict]:
    if settings is None:
        from .settings_store import load_settings
        settings = load_settings()
    return list(((settings.get("observability") or {}).get("log_forwarding")) or [])


def public_view(d: dict) -> dict:
    return {k: d.get(k) for k in ("id", "name", "kind", "host", "port", "transport", "endpoint",
                                  "level", "enabled", "verify_tls")} | {
        "has_token": bool(d.get("token_enc")), "has_headers": bool(d.get("headers_enc")),
        "last_error": LAST_ERROR.get(d.get("id", ""), "")}


def make_destination(data: dict, old: Optional[dict] = None) -> dict:
    """A stored destination from the settings page. Raises ValueError in
    plain words."""
    old = old or {}
    g = lambda k, default=None: data[k] if data.get(k) not in (None, "") else old.get(k, default)
    kind = g("kind", "syslog")
    if kind not in KINDS:
        raise ValueError("Choose a kind of log server from the list.")
    level = str(g("level", "INFO")).upper()
    if level not in LEVELS:
        raise ValueError("Choose which log lines to send.")
    out = {"id": old.get("id") or uuid.uuid4().hex[:12], "name": str(g("name", KINDS[kind]))[:60],
           "kind": kind, "level": level, "enabled": bool(data.get("enabled", old.get("enabled", True))),
           "verify_tls": bool(data.get("verify_tls", old.get("verify_tls", True)))}
    if kind == "syslog":
        host = str(g("host", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}|\[?[0-9a-fA-F:]+\]?", host or ""):
            raise ValueError("Enter the log server's name or address, for example logs.example.org.")
        transport = g("transport", "udp")
        if transport not in TRANSPORTS:
            raise ValueError("Choose UDP, TCP or TLS.")
        try:
            port = int(g("port", 6514 if transport == "tls" else 514))
            assert 0 < port < 65536
        except Exception:
            raise ValueError("The port must be a number from 1 to 65535.")
        out.update(host=host, port=port, transport=transport, endpoint="")
    else:
        endpoint = str(g("endpoint", "")).strip().rstrip("/")
        if not re.match(r"^https?://[^\s/]+", endpoint):
            raise ValueError("The address must start with https:// (or http:// on your own network).")
        out.update(endpoint=endpoint, host="", port=None, transport="")
    token = data.get("token")
    out["token_enc"] = (_encrypt(token) if token else "") if token is not None else old.get("token_enc", "")
    headers = data.get("headers")
    if headers is not None:
        if headers and (not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                                  for k, v in headers.items())):
            raise ValueError("Extra headers must be names and values.")
        out["headers_enc"] = _encrypt(json.dumps(headers)) if headers else ""
    else:
        out["headers_enc"] = old.get("headers_enc", "")
    return out


# ── Formats ───────────────────────────────────────────────────────────────────

def syslog_line(rec: dict, facility: int = 16) -> bytes:
    """RFC 5424: <PRI>1 TIMESTAMP HOST APP PROCID MSGID - MSG (facility local0)."""
    pri = facility * 8 + _SEVERITY.get(rec["level"], 6)
    ts = datetime.fromtimestamp(rec["time"], tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    logger = re.sub(r"[^\x21-\x7e]", "_", rec["logger"])[:32] or "-"
    return f"<{pri}>1 {ts} {HOSTNAME} openoptout {os.getpid()} {logger} - {rec['message']}".encode("utf-8")


def _version() -> str:
    try:
        from .version import get_version
        return get_version()
    except Exception:
        return ""


def otlp_json(records: List[dict]) -> dict:
    return {"resourceLogs": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": "openoptout"}},
            {"key": "service.version", "value": {"stringValue": _version()}},
            {"key": "host.name", "value": {"stringValue": HOSTNAME}}]},
        "scopeLogs": [{"scope": {"name": "openoptout"}, "logRecords": [{
            "timeUnixNano": str(int(r["time"] * 1e9)),
            "severityNumber": _OTLP_SEVERITY.get(r["level"], 9),
            "severityText": r["level"],
            "body": {"stringValue": r["message"]},
            "attributes": [{"key": "logger", "value": {"stringValue": r["logger"]}}],
        } for r in records]}]}]}


def loki_json(records: List[dict]) -> dict:
    streams: Dict[str, list] = {}
    for r in records:
        streams.setdefault(r["level"].lower(), []).append([str(int(r["time"] * 1e9)), f"[{r['logger']}] {r['message']}"])
    return {"streams": [{"stream": {"service_name": "openoptout", "host": HOSTNAME, "level": lvl},
                         "values": vals} for lvl, vals in streams.items()]}


def splunk_lines(records: List[dict]) -> str:
    return "\n".join(json.dumps({"time": r["time"], "host": HOSTNAME, "source": "openoptout",
                                 "sourcetype": "openoptout", "event": {"level": r["level"], "logger": r["logger"],
                                                                       "message": r["message"]}})
                     for r in records)


# ── Sending ───────────────────────────────────────────────────────────────────

_sockets: Dict[str, object] = {}


def _send_syslog(d: dict, records: List[dict]) -> None:
    host, port, transport = d["host"], int(d["port"]), d.get("transport", "udp")
    if transport == "udp":
        with socket.socket(socket.AF_INET6 if ":" in host.strip("[]") else socket.AF_INET, socket.SOCK_DGRAM) as s:
            for r in records:
                s.sendto(syslog_line(r)[:8192], (host.strip("[]"), port))
        return
    sock = _sockets.get(d["id"])
    if sock is None:
        raw = socket.create_connection((host.strip("[]"), port), timeout=10)
        if transport == "tls":
            ctx = ssl.create_default_context()
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            if not d.get("verify_tls", True):
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE  # nosec B323
            raw = ctx.wrap_socket(raw, server_hostname=host.strip("[]"))
        sock = raw
        _sockets[d["id"]] = sock
    try:
        for r in records:
            line = syslog_line(r)
            sock.sendall(f"{len(line)} ".encode() + line)     # RFC 6587 octet counting
    except Exception:
        _sockets.pop(d["id"], None)
        try:
            sock.close()
        except Exception:
            pass
        raise


def _http_headers(d: dict) -> dict:
    h = {"User-Agent": "OpenOptOut"}
    extra = _decrypt(d.get("headers_enc", ""))
    if extra:
        h.update(json.loads(extra))
    token = _decrypt(d.get("token_enc", ""))
    if token:
        h["Authorization"] = f"Splunk {token}" if d["kind"] == "splunk_hec" else f"Bearer {token}"
    return h


def _send_http(d: dict, records: List[dict]) -> None:
    import httpx
    base = d["endpoint"]
    h = _http_headers(d)
    if d["kind"] == "otlp":
        url = base if base.endswith("/v1/logs") else base + "/v1/logs"
        body, h["Content-Type"] = json.dumps(otlp_json(records)), "application/json"
    elif d["kind"] == "loki":
        url = base if base.endswith("/loki/api/v1/push") else base + "/loki/api/v1/push"
        body, h["Content-Type"] = json.dumps(loki_json(records)), "application/json"
    else:
        url = base if "/services/collector" in base else base + "/services/collector/event"
        body, h["Content-Type"] = splunk_lines(records), "application/json"
    r = httpx.post(url, content=body.encode("utf-8"), headers=h, timeout=10.0,
                   verify=d.get("verify_tls", True), follow_redirects=False)
    if not 200 <= r.status_code < 300:
        raise RuntimeError(f"the server answered {r.status_code}")


def send(d: dict, records: List[dict]) -> None:
    if SENDER is not None:
        return SENDER(d, records)
    if d["kind"] == "syslog":
        return _send_syslog(d, records)
    return _send_http(d, records)


# ── The logging handler ───────────────────────────────────────────────────────

class ForwardingHandler(logging.Handler):
    """Queues scrubbed records; a thread sends them in batches."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.q: "queue.Queue" = queue.Queue(maxsize=QUEUE_MAX)
        self.dests: List[dict] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def configure(self, dests: List[dict]) -> None:
        self.dests = [d for d in dests if d.get("enabled", True)]
        for k in list(_sockets):
            if k not in {d["id"] for d in self.dests}:
                try:
                    _sockets.pop(k).close()
                except Exception:
                    pass
        if self.dests and (self._thread is None or not self._thread.is_alive()):
            self._thread = threading.Thread(target=self._run, name="log-forwarding", daemon=True)
            self._thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        if not self.dests or record.name.startswith(("httpx", "httpcore", __name__)):
            return      # never forward our own sending (it would loop)
        try:
            rec = {"time": record.created, "level": record.levelname, "logger": record.name,
                   "message": scrub(record.getMessage())}
        except Exception:
            return
        try:
            self.q.put_nowait(rec)
        except queue.Full:
            try:
                self.q.get_nowait()
                self.q.put_nowait(rec)
            except Exception:
                pass
            STATS["dropped"] += 1

    def _run(self) -> None:
        while not self._stop.is_set():
            batch = []
            deadline = time.monotonic() + FLUSH_SECONDS
            while len(batch) < BATCH and time.monotonic() < deadline:
                try:
                    batch.append(self.q.get(timeout=max(0.05, deadline - time.monotonic())))
                except queue.Empty:
                    break
            if batch:
                self.flush_batch(batch)

    def flush_batch(self, batch: List[dict]) -> None:
        for d in list(self.dests):
            want = logging.getLevelName(d.get("level", "INFO"))
            recs = [r for r in batch if logging.getLevelName(r["level"]) >= want]
            if not recs:
                continue
            try:
                send(d, recs)
                STATS["sent"] += len(recs)
                LAST_ERROR.pop(d["id"], None)
            except Exception as e:
                STATS["failed_batches"] += 1
                STATS["dropped"] += len(recs)
                LAST_ERROR[d["id"]] = f"{type(e).__name__}: {str(e)[:120]}"


_handler: Optional[ForwardingHandler] = None


def handler() -> ForwardingHandler:
    global _handler
    if _handler is None:
        _handler = ForwardingHandler()
    return _handler


def apply(settings: Optional[dict] = None) -> int:
    """Attach (or update) the forwarding handler from the settings. Returns
    how many destinations are on."""
    h = handler()
    root = logging.getLogger()
    dests = destinations(settings)
    h.configure(dests)
    if h.dests and h not in root.handlers:
        root.addHandler(h)
    return len(h.dests)


def test(d: dict) -> str:
    """Send one line to `d` now. Returns "" when it worked, else the problem
    in plain words."""
    rec = {"time": time.time(), "level": "INFO", "logger": "openoptout.test",
           "message": "Test message from OpenOptOut. If you can read this, log forwarding works."}
    try:
        send(d, [rec])
        return ""
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:160]}"
