"""
Monitoring, log forwarding and webhook notifications (core/monitoring.py,
core/log_forwarding.py, core/webhooks.py).

  GET    /api/health/ready                          health checks (public)            200 ok / 503 problem
  GET    /api/metrics                               Prometheus metrics                metrics token or super admin
  GET    /api/observability                         settings (no secrets)             super admin
  PUT    /api/observability/log-forwarding[/{id}]   add or change a log server        super admin
  DELETE /api/observability/log-forwarding/{id}
  POST   /api/observability/log-forwarding/{id}/test
  PUT    /api/observability/webhooks[/{id}]         add or change a webhook           super admin
  DELETE /api/observability/webhooks/{id}
  POST   /api/observability/webhooks/{id}/test
  POST   /api/observability/metrics-token           make a new token (shown once)     super admin
  DELETE /api/observability/metrics-token

Everything here sends data off the server, so only super admins set it up.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.auth import require_super_admin
from ..core.settings_store import load_settings, SETTINGS_FILE
from ..models.database import get_db, User

router = APIRouter(prefix="/api/observability", tags=["observability"])
ops_router = APIRouter(tags=["monitoring"])


def _save(s: dict) -> None:
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)


def _obs(s: dict) -> dict:
    return s.setdefault("observability", {})


# ── Health and metrics ────────────────────────────────────────────────────────

@ops_router.get("/api/health/ready")
def health_ready(db: Session = Depends(get_db)):
    from ..core.monitoring import ready
    r = ready(db)
    return JSONResponse(r, status_code=200 if r["status"] == "ok" else 503)


@ops_router.get("/api/metrics")
def get_metrics(request: Request, db: Session = Depends(get_db)):
    from ..core import monitoring
    s = load_settings()
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    allowed = monitoring.token_ok(s, token)
    if not allowed and token:
        try:
            from ..core.auth import get_current_user
            from ..models.database import UserRole
            u = get_current_user(token=token, db=db)
            allowed = u.role == UserRole.super_admin
        except Exception:
            allowed = False
    if not allowed:
        raise HTTPException(401, "Send the metrics token as: Authorization: Bearer <token>.",
                            headers={"WWW-Authenticate": "Bearer"})
    return PlainTextResponse(monitoring.metrics(db, s), media_type="text/plain; version=0.0.4")


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("")
def get_settings(_: User = Depends(require_super_admin)):
    from ..core import log_forwarding as lf, webhooks as wh
    s = load_settings()
    return {
        "log_forwarding": [lf.public_view(d) for d in lf.destinations(s)],
        "log_kinds": lf.KINDS, "log_levels": list(lf.LEVELS),
        "log_stats": lf.STATS,
        "webhooks": [wh.public_view(t) for t in wh.targets(s)],
        "webhook_kinds": wh.KINDS,
        "events": {k: v[0] for k, v in wh.EVENTS.items() if k != "test"},
        "default_events": wh.DEFAULT_EVENTS,
        "has_metrics_token": bool(_obs(s).get("metrics_token_hash")),
    }


class LogDest(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    transport: Optional[str] = None
    endpoint: Optional[str] = None
    level: Optional[str] = None
    token: Optional[str] = None             # empty string clears it; left out keeps it
    headers: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None
    verify_tls: Optional[bool] = None


def _upsert(listname: str, item_id: Optional[str], build):
    s = load_settings()
    items: List[dict] = list(_obs(s).get(listname) or [])
    old = next((x for x in items if x["id"] == item_id), None) if item_id else None
    if item_id and old is None:
        raise HTTPException(404, "That one wasn't found. It may have been removed.")
    try:
        new = build(old)
    except ValueError as e:
        raise HTTPException(400, str(e))
    items = [new if x["id"] == new["id"] else x for x in items] if old else items + [new]
    _obs(s)[listname] = items
    _save(s)
    return s, new


@router.put("/log-forwarding")
@router.put("/log-forwarding/{dest_id}")
def save_log_destination(req: LogDest, dest_id: Optional[str] = None, _: User = Depends(require_super_admin)):
    from ..core import log_forwarding as lf
    data = req.model_dump(exclude_unset=True)
    s, new = _upsert("log_forwarding", dest_id, lambda old: lf.make_destination(data, old))
    lf.apply(s)
    return lf.public_view(new)


@router.delete("/log-forwarding/{dest_id}")
def delete_log_destination(dest_id: str, _: User = Depends(require_super_admin)):
    from ..core import log_forwarding as lf
    s = load_settings()
    _obs(s)["log_forwarding"] = [d for d in lf.destinations(s) if d["id"] != dest_id]
    _save(s)
    lf.apply(s)
    return {"removed": True}


@router.post("/log-forwarding/{dest_id}/test")
def test_log_destination(dest_id: str, _: User = Depends(require_super_admin)):
    from ..core import log_forwarding as lf
    d = next((d for d in lf.destinations() if d["id"] == dest_id), None)
    if d is None:
        raise HTTPException(404, "That log server wasn't found.")
    problem = lf.test(d)
    return {"ok": not problem,
            "message": "Sent a test line. Look for \"Test message from OpenOptOut\" on the log server."
                       if not problem else f"Couldn't send it: {problem}"}


class Webhook(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None


@router.put("/webhooks")
@router.put("/webhooks/{hook_id}")
def save_webhook(req: Webhook, hook_id: Optional[str] = None, _: User = Depends(require_super_admin)):
    from ..core import webhooks as wh
    data = req.model_dump(exclude_unset=True)
    _, new = _upsert("webhooks", hook_id, lambda old: wh.make_target(data, old))
    return wh.public_view(new)


@router.delete("/webhooks/{hook_id}")
def delete_webhook(hook_id: str, _: User = Depends(require_super_admin)):
    from ..core import webhooks as wh
    s = load_settings()
    _obs(s)["webhooks"] = [t for t in wh.targets(s) if t["id"] != hook_id]
    _save(s)
    return {"removed": True}


@router.post("/webhooks/{hook_id}/test")
def test_webhook(hook_id: str, _: User = Depends(require_super_admin)):
    from ..core import webhooks as wh
    t = next((t for t in wh.targets() if t["id"] == hook_id), None)
    if t is None:
        raise HTTPException(404, "That webhook wasn't found.")
    title, message, details = wh.build("test", "Test message from OpenOptOut. If you can read this, notifications work.")
    ok, status = wh._deliver(t, "test", title, message, details)
    wh._record(t["id"], ok, status)
    return {"ok": ok, "message": "Sent. Check that it arrived." if ok else f"Not delivered: {status}."}


@router.post("/metrics-token")
def make_metrics_token(_: User = Depends(require_super_admin)):
    from ..core.monitoring import new_token
    s = load_settings()
    token = new_token(s)
    _save(s)
    return {"token": token}


@router.delete("/metrics-token")
def drop_metrics_token(_: User = Depends(require_super_admin)):
    s = load_settings()
    _obs(s).pop("metrics_token_hash", None)
    _save(s)
    return {"removed": True}
