"""
Usage statistics web service (core/usage_stats.py).

  GET    /api/stats/v1/...               the API for clients                  Authorization: Bearer <key>
  GET    /api/stats-admin                settings, institutions, keys         super admin
  PUT    /api/stats-admin                {enabled}
  POST   /api/stats-admin/keys           {name, institutions} -> the key, shown once
  DELETE /api/stats-admin/keys/{id}
  POST   /api/stats-admin/self-test      the client checks, run against this server
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core import usage_stats as U
from ..core.auth import require_super_admin
from ..core.settings_store import load_settings, save_settings
from ..models.database import get_db, User

logger = logging.getLogger(__name__)

api_router = APIRouter(tags=["usage statistics"])
router = APIRouter(prefix="/api/stats-admin", tags=["usage statistics"])


def _save(s: dict) -> None:
    save_settings(s)


def _respond(status, body, media):
    if media == "text/csv":
        return Response(body, status_code=status, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'inline; filename="openoptout-usage.csv"',
                                 "Cache-Control": "no-store"})
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


@api_router.get("/api/stats/{path:path}")
def stats_api(path: str, request: Request, db: Session = Depends(get_db)):
    s = load_settings()
    cfg = U.config(s)
    auth = request.headers.get("authorization", "")
    status, body, media = U.handle(db, "/" + path, dict(request.query_params), auth, cfg)
    if status < 400 and auth:
        _note_use(s, cfg, auth)
    return _respond(status, body, media)


def _note_use(s: dict, cfg: dict, auth: str) -> None:
    """Remember when each key was last used (at most hourly)."""
    m = U.KEY.match(auth[7:].strip()) if auth.lower().startswith("bearer ") else None
    if not m:
        return
    now = datetime.utcnow()
    for c in cfg["clients"]:
        if c["id"] == m.group(1):
            try:
                last = datetime.fromisoformat(c.get("last_used") or "2000-01-01T00:00:00")
            except ValueError:
                last = datetime(2000, 1, 1)
            if now - last > timedelta(hours=1):
                c["last_used"] = now.isoformat(timespec="seconds")
                s["stats_api"] = cfg
                try:
                    _save(s)
                except OSError:
                    pass
            return


def _view(db, cfg: dict) -> dict:
    return {"enabled": cfg["enabled"],
            "clients": [U.public_client(c) for c in cfg["clients"]],
            "institutions": [U.public_institution(i) for i in U.institutions(db)],
            "metrics": [{"name": k, "description": v} for k, v in U.METRICS.items()]}


@router.get("")
def get_admin(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    return _view(db, U.config())


class StatsSettings(BaseModel):
    enabled: Optional[bool] = None


@router.put("")
def put_admin(req: StatsSettings, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    s = load_settings()
    cfg = U.config(s)
    if req.enabled is not None:
        cfg["enabled"] = bool(req.enabled)
    s["stats_api"] = cfg
    _save(s)
    return _view(db, cfg)


class KeyIn(BaseModel):
    name: str
    institutions: List[str] = ["*"]


@router.post("/keys")
def add_key(req: KeyIn, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    s = load_settings()
    cfg = U.config(s)
    known = {i["id"] for i in U.institutions(db)}
    bad = [i for i in req.institutions if i != "*" and i not in known]
    if bad:
        raise HTTPException(400, f"Unknown institution: {', '.join(bad)}")
    try:
        c, key = U.new_client(cfg, req.name, req.institutions)
    except ValueError as e:
        logger.warning("Stats key generation failed: %s", e)
        safe_msg = "Give the key a name, like the script or system that will use it."
        detail = safe_msg if str(e) == safe_msg else "Invalid key name or institutions."
        raise HTTPException(400, detail)
    s["stats_api"] = cfg
    _save(s)
    return {"client": U.public_client(c), "key": key}


@router.delete("/keys/{cid}")
def delete_key(cid: str, _: User = Depends(require_super_admin)):
    s = load_settings()
    cfg = U.config(s)
    cfg["clients"] = [c for c in cfg["clients"] if c["id"] != cid]
    s["stats_api"] = cfg
    _save(s)
    return {"removed": True}


@router.post("/self-test")
def self_test(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    """Run the client checks against this server with a throwaway key that's
    never saved. Works while the service is off, and says so."""
    from ..core import stats_check
    cfg = U.config()
    trial = dict(cfg, enabled=True, clients=list(cfg["clients"]))
    _, key = U.new_client(trial, "self-test", ["*"])

    def get(path, params, k):
        st, body, _media = U.handle(db, path, params, f"Bearer {k}" if k else "", trial)
        return st, body

    results = stats_check.run(get, key)
    for r in results:
        r["text"] = stats_check.CHECK_TEXTS[r["key"]]
    return {"ok": all(r["ok"] for r in results), "enabled": cfg["enabled"], "results": results}
