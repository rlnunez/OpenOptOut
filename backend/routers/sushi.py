"""
Usage statistics over the COUNTER API (SUSHI): core/sushi.py.

  GET    /api/sushi/r51/...                    the COUNTER API for harvesters      requestor_id + api_key
  GET    /api/sushi-admin                      settings, institutions, harvesters  super admin
  PUT    /api/sushi-admin                      {enabled, platform, namespace, registry_record}
  POST   /api/sushi-admin/harvesters           {name, customers} -> the API key, shown once
  DELETE /api/sushi-admin/harvesters/{id}
  POST   /api/sushi-admin/self-test            the harvester checks, run against this server
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core import sushi as S
from ..core.auth import require_super_admin
from ..core.settings_store import load_settings, SETTINGS_FILE
from ..models.database import get_db, User

api_router = APIRouter(tags=["sushi"])
router = APIRouter(prefix="/api/sushi-admin", tags=["sushi"])


def _save(s: dict) -> None:
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)


@api_router.get("/api/sushi/{path:path}")
def counter_api(path: str, request: Request, db: Session = Depends(get_db)):
    s = load_settings()
    cfg = S.config(s)
    params = dict(request.query_params)
    status, body = S.dispatch(db, "/" + path, params, cfg)
    if status < 400 and params.get("requestor_id"):
        _note_use(s, cfg, params["requestor_id"])
    return JSONResponse(body, status_code=status)


def _note_use(s: dict, cfg: dict, rid: str) -> None:
    """Remember when each harvester last collected (at most hourly, so a
    harvest doesn't rewrite the settings on every request)."""
    now = datetime.utcnow()
    for h in cfg["harvesters"]:
        if h["requestor_id"] == rid:
            try:
                last = datetime.fromisoformat(h.get("last_used") or "2000-01-01T00:00:00")
            except ValueError:
                last = datetime(2000, 1, 1)
            if now - last > timedelta(hours=1):
                h["last_used"] = now.isoformat(timespec="seconds")
                s["sushi"] = cfg
                try:
                    _save(s)
                except OSError:
                    pass
            return


def _view(db, cfg: dict) -> dict:
    first, last = S.months_available(db)
    return {"enabled": cfg["enabled"], "platform": cfg["platform"], "namespace": cfg["namespace"],
            "registry_record": cfg.get("registry_record") or "",
            "harvesters": [S.public_harvester(h) for h in cfg["harvesters"]],
            "customers": [{"id": c["id"], "name": c["name"]} for c in S.customers(db, cfg)],
            "reports": [{"id": r["id"], "name": r["name"]} for r in S.reports(cfg).values()],
            "first_month": first.isoformat()[:7] if first else None, "last_month": last.isoformat()[:7]}


@router.get("")
def get_admin(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    return _view(db, S.config())


class SushiSettings(BaseModel):
    enabled: Optional[bool] = None
    platform: Optional[str] = None
    namespace: Optional[str] = None
    registry_record: Optional[str] = None


@router.put("")
def put_admin(req: SushiSettings, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    s = load_settings()
    cfg = S.config(s)
    data = req.model_dump(exclude_unset=True)
    if data.get("platform") is not None:
        p = data["platform"].strip()
        if not p or len(p) > 100:
            raise HTTPException(400, "The platform name must be 1 to 100 characters.")
        cfg["platform"] = p
    if data.get("namespace") is not None:
        if not S.NAMESPACE.match(data["namespace"]):
            raise HTTPException(400, "The namespace may use letters, digits, _ . and /, up to 17 characters.")
        cfg["namespace"] = data["namespace"]
    if data.get("registry_record") is not None:
        r = data["registry_record"].strip()
        if r and not r.startswith("https://"):
            raise HTTPException(400, "The COUNTER Registry address must start with https://")
        cfg["registry_record"] = r
    if data.get("enabled") is not None:
        cfg["enabled"] = bool(data["enabled"])
    s["sushi"] = cfg
    _save(s)
    return _view(db, cfg)


class HarvesterIn(BaseModel):
    name: str
    customers: List[str] = ["*"]


@router.post("/harvesters")
def add_harvester(req: HarvesterIn, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    s = load_settings()
    cfg = S.config(s)
    known = {c["id"] for c in S.customers(db, cfg)}
    bad = [c for c in req.customers if c != "*" and c not in known]
    if bad:
        raise HTTPException(400, f"Unknown institution: {', '.join(bad)}")
    try:
        h, key = S.new_harvester(cfg, req.name, req.customers)
    except ValueError as e:
        raise HTTPException(400, str(e))
    s["sushi"] = cfg
    _save(s)
    return {"harvester": S.public_harvester(h), "api_key": key}


@router.delete("/harvesters/{hid}")
def delete_harvester(hid: str, _: User = Depends(require_super_admin)):
    s = load_settings()
    cfg = S.config(s)
    cfg["harvesters"] = [h for h in cfg["harvesters"] if h["id"] != hid]
    s["sushi"] = cfg
    _save(s)
    return {"removed": True}


@router.post("/self-test")
def self_test(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    """Run the harvester checks against this server with a throwaway key
    that's never saved. Works while the service is off, and says so."""
    from ..core import sushi_check
    cfg = S.config()
    trial = dict(cfg, enabled=True, harvesters=list(cfg["harvesters"]))
    h, key = S.new_harvester(trial, "self-test", ["*"])

    def get(path, params):
        return S.dispatch(db, path, params, trial)

    results = sushi_check.run(get, h["requestor_id"], key, "all")
    for r in results:
        r["label"] = sushi_check.text(r)
        r["text"] = sushi_check.CHECK_TEXTS[r["key"]]
    return {"ok": all(r["ok"] for r in results), "enabled": cfg["enabled"], "results": results}
