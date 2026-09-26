"""
Extended plugin capabilities: broker read, request lifecycle, constrained
opt-out email trigger, host-mediated HTTP fetch, and custom recheck scheduling.

Design principles enforced throughout:

  - PII MINIMIZATION: every response here returns IDs, enums, counts, and
    timestamps only. Never a member's name, address, phone, or email. This
    module has no code path that can return that data — it queries Broker and
    RemovalRequest, not FamilyMember or Identity fields.

  - HIGH-RISK WRITES ARE DIFF-LOGGED: request.mark_* and schedule.set_recheck
    record the before/after value to PluginAuditLog in addition to the normal
    action entry, so a super admin can see exactly what changed.

  - CONSTRAINED, NOT FREEFORM: the email trigger calls the exact same
    send_opt_out_email() function the opt-out engine itself uses. A plugin
    cannot supply its own subject, body, or recipient — only a request_id.

  - HOST-MEDIATED FETCH: HttpFetch is executed BY THE HOST, not the plugin.
    The plugin never gets a raw socket; it asks the host to fetch a URL, and
    the host enforces the domain allowlist declared in the manifest.
"""

import time
import logging
from typing import Optional
from urllib.parse import urlparse

from .permissions import Permission

log = logging.getLogger(__name__)


class ExtendedCapabilityError(Exception):
    pass


def _to_ts(dt) -> int:
    return int(dt.timestamp()) if dt else 0


class ExtendedCapabilities:
    """
    Backs the new HostService RPCs. Constructed with a session_factory so each
    call gets its own short-lived DB session (consistent with the rest of the
    broker's pattern), plus an audit_sink for diff-logged writes and an
    email_sender/http_fetcher injected from the host's real implementations.
    """

    def __init__(self, session_factory, audit_sink, email_sender=None, http_fetcher=None):
        self.session_factory = session_factory
        self.audit_sink = audit_sink          # (plugin_id, action, detail) -> None
        self.email_sender = email_sender      # (request_id) -> (ok: bool, error: str)
        self.http_fetcher = http_fetcher      # (method, url, body, headers) -> (status, body)

    # ── Broker read (no member PII) ───────────────────────────────────────────

    def broker_get(self, plugin_id: str, broker_id: int) -> dict:
        from ..models.database import Broker
        db = self.session_factory()
        try:
            b = db.query(Broker).filter(Broker.id == broker_id).first()
            if not b:
                return {"found": False}
            return {
                "found": True, "broker_id": b.id, "name": b.name,
                "method": b.method.value if b.method else "",
                "difficulty": b.difficulty.value if b.difficulty else "",
                "status": b.status.value if b.status else "",
            }
        finally:
            db.close()

    def broker_list(self, plugin_id: str, limit: int = 100) -> list[dict]:
        from ..models.database import Broker
        limit = max(1, min(limit or 100, 500))  # guard against unbounded pulls
        db = self.session_factory()
        try:
            rows = db.query(Broker).limit(limit).all()
            return [{
                "found": True, "broker_id": b.id, "name": b.name,
                "method": b.method.value if b.method else "",
                "difficulty": b.difficulty.value if b.difficulty else "",
                "status": b.status.value if b.status else "",
            } for b in rows]
        finally:
            db.close()

    def broker_history(self, plugin_id: str, broker_id: int) -> dict:
        from ..models.database import Broker, RemovalRequest, RequestStatus
        db = self.session_factory()
        try:
            b = db.query(Broker).filter(Broker.id == broker_id).first()
            if not b:
                return {"found": False}
            q = db.query(RemovalRequest).filter(RemovalRequest.broker_id == broker_id)
            total = q.count()
            confirmed = q.filter(RemovalRequest.status == RequestStatus.confirmed).count()
            failed    = q.filter(RemovalRequest.status == RequestStatus.failed).count()
            pending   = q.filter(RemovalRequest.status == RequestStatus.pending).count()
            return {"found": True, "total_requests": total, "confirmed_count": confirmed,
                    "failed_count": failed, "pending_count": pending}
        finally:
            db.close()

    # ── Request lifecycle (status only, no member PII) ───────────────────────

    def request_get_status(self, plugin_id: str, request_id: int) -> dict:
        from ..models.database import RemovalRequest
        db = self.session_factory()
        try:
            r = db.query(RemovalRequest).filter(RemovalRequest.id == request_id).first()
            if not r:
                return {"found": False}
            return {
                "found": True, "request_id": r.id,
                "status": r.status.value if r.status else "",
                "method_used": r.method_used.value if r.method_used else "",
                "sent_at": _to_ts(r.sent_at), "confirmed_at": _to_ts(r.confirmed_at),
                "recheck_after": _to_ts(r.recheck_after),
            }
        finally:
            db.close()

    def _mark(self, plugin_id: str, request_id: int, new_status_name: str, reason: str) -> dict:
        """Shared implementation for mark_sent/mark_confirmed/mark_failed."""
        from ..models.database import RemovalRequest, RequestStatus
        from datetime import datetime
        db = self.session_factory()
        try:
            r = db.query(RemovalRequest).filter(RemovalRequest.id == request_id).first()
            if not r:
                return {"ok": False, "error": "request not found"}
            previous = r.status.value if r.status else ""
            new_status = RequestStatus(new_status_name)
            r.status = new_status
            if new_status_name == "sent":
                r.sent_at = datetime.utcnow()
            elif new_status_name == "confirmed":
                r.confirmed_at = datetime.utcnow()
            r.updated_at = datetime.utcnow()
            db.commit()
            # Diff-logged audit entry — status values only, never member PII.
            self.audit_sink(
                plugin_id, "request_write",
                f"request_id={request_id} status: {previous} -> {new_status_name}"
                + (f" (reason: {reason[:200]})" if reason else ""),
            )
            return {"ok": True, "previous_status": previous, "new_status": new_status_name}
        except ValueError:
            return {"ok": False, "error": f"invalid status: {new_status_name}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            db.close()

    def request_mark_sent(self, plugin_id: str, request_id: int, reason: str) -> dict:
        return self._mark(plugin_id, request_id, "sent", reason)

    def request_mark_confirmed(self, plugin_id: str, request_id: int, reason: str) -> dict:
        return self._mark(plugin_id, request_id, "confirmed", reason)

    def request_mark_failed(self, plugin_id: str, request_id: int, reason: str) -> dict:
        return self._mark(plugin_id, request_id, "failed", reason)

    # ── Constrained opt-out email trigger ─────────────────────────────────────

    def trigger_optout_email(self, plugin_id: str, request_id: int) -> dict:
        """
        Sends the EXISTING opt-out email template for one pending request. The
        plugin supplies only a request_id — no subject, body, or recipient are
        accepted, so this cannot be used to send arbitrary email.
        """
        from ..models.database import RemovalRequest, RequestStatus, OptOutMethod
        db = self.session_factory()
        try:
            r = db.query(RemovalRequest).filter(RemovalRequest.id == request_id).first()
            if not r:
                return {"ok": False, "error": "request not found"}
            if r.status != RequestStatus.pending:
                return {"ok": False, "error": f"request is not pending (status={r.status.value})"}
            if not r.broker or r.broker.method != OptOutMethod.email:
                return {"ok": False, "error": "broker is not an email-method broker"}
            if not self.email_sender:
                return {"ok": False, "error": "email sending not available on this host"}
        finally:
            db.close()

        ok, error = self.email_sender(request_id)
        self.audit_sink(
            plugin_id, "optout_email_triggered",
            f"request_id={request_id} -> {'sent' if ok else 'failed: ' + (error or '')}",
        )
        return {"ok": ok, "error": error or ""}

    # ── Host-mediated HTTP fetch ──────────────────────────────────────────────

    def http_fetch(self, plugin_id: str, method: str, url: str, body: str,
                   headers: dict, allowed_domains: set) -> dict:
        """
        The HOST performs this fetch, not the plugin. Restricted to domains the
        plugin declared in its manifest's outbound_domains — a plugin cannot
        fetch an arbitrary URL just because it holds the http_fetch permission.
        """
        if method.upper() not in ("GET", "POST"):
            return {"ok": False, "error": "only GET/POST supported"}
        try:
            parsed = urlparse(url)
        except Exception:
            return {"ok": False, "error": "invalid URL"}
        if parsed.scheme not in ("http", "https"):
            return {"ok": False, "error": "only http/https URLs allowed"}
        host = (parsed.hostname or "").lower()
        if not any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed_domains):
            self.audit_sink(plugin_id, "fetch_domain_denied", f"url={url} host={host}")
            return {"ok": False, "error": f"domain '{host}' not in this plugin's declared outbound_domains"}
        if not self.http_fetcher:
            return {"ok": False, "error": "HTTP fetch not available on this host"}

        try:
            status_code, resp_body = self.http_fetcher(method.upper(), url, body, headers)
            self.audit_sink(plugin_id, "http_fetch", f"{method.upper()} {url} -> {status_code}")
            return {"ok": True, "status_code": status_code, "body": resp_body}
        except Exception as e:
            self.audit_sink(plugin_id, "http_fetch_error", f"{method.upper()} {url} -> {e}")
            return {"ok": False, "error": str(e)}

    # ── Custom recheck scheduling ─────────────────────────────────────────────

    def schedule_set_recheck(self, plugin_id: str, request_id: int,
                             recheck_after_ts: int, reason: str) -> dict:
        from ..models.database import RemovalRequest
        from datetime import datetime, timezone
        db = self.session_factory()
        try:
            r = db.query(RemovalRequest).filter(RemovalRequest.id == request_id).first()
            if not r:
                return {"ok": False, "error": "request not found"}
            previous = _to_ts(r.recheck_after)
            new_dt = datetime.fromtimestamp(recheck_after_ts, tz=timezone.utc).replace(tzinfo=None)
            r.recheck_after = new_dt
            r.updated_at = datetime.utcnow()
            db.commit()
            self.audit_sink(
                plugin_id, "schedule_write",
                f"request_id={request_id} recheck_after: {previous} -> {recheck_after_ts}"
                + (f" (reason: {reason[:200]})" if reason else ""),
            )
            return {"ok": True, "previous_recheck": previous, "new_recheck": recheck_after_ts}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            db.close()
