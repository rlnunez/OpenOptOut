"""
State data-broker registries (admin). See core/registry_sync.py.

  GET  /api/registry/sources              each state's page, saved address, last import
  PUT  /api/registry/sources/{state}      save (or clear) the address to download from
  POST /api/registry/{state}/preview      upload a file, or use the saved address: what would change
  POST /api/registry/{state}/import       same input: apply (new brokers start turned off)
  GET  /api/registry/brokers              registry brokers, filterable
  POST /api/registry/enable               turn brokers on — requires acknowledging the warning
  POST /api/registry/disable              turn brokers off
  POST /api/registry/check-sites          check up to 50 broker sites for dead addresses now
"""

import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, Broker, BrokerHealth
from ..core.access import require_permission
from ..core.settings_store import load_settings, save_settings, SETTINGS_FILE
from ..core import registry_sync as rs

router = APIRouter(prefix="/api/registry", tags=["registry"])
_admin = require_permission("brokers.manage")


def _save(s: dict):
    save_settings(s)


def _state(state: str) -> str:
    st = (state or "").upper()
    if st not in rs.SOURCES:
        raise HTTPException(404, "Unknown state. Supported: " + ", ".join(rs.SOURCES))
    return st


@router.get("/sources")
def sources(db: Session = Depends(get_db), _=Depends(_admin)):
    s = load_settings()
    saved = s.get("registry_sources") or {}
    out = []
    for st, meta in rs.SOURCES.items():
        mine = saved.get(st) or {}
        total = db.query(Broker).filter(Broker.registry_states.like(f"%{st}%")).count()
        out.append({"state": st, **{k: meta[k] for k in ("label", "page", "how")},
                    "url": mine.get("url", ""), "suggested_url": meta["default_url"],
                    "last_import_at": mine.get("last_import_at"), "last_counts": mine.get("last_counts"),
                    "brokers": total})
    q = db.query(Broker).filter(Broker.origin == "registry")
    return {"sources": out, "warning": rs.REGISTRY_ENABLE_WARNING,
            "registry_brokers": q.count(), "registry_brokers_on": q.filter(Broker.enabled.is_(True)).count()}


class SourceIn(BaseModel):
    url: str = ""


@router.put("/sources/{state}")
def save_source(state: str, body: SourceIn, _=Depends(_admin)):
    st = _state(state)
    url = (body.url or "").strip()
    if url and not url.startswith("https://"):
        raise HTTPException(400, "Registry addresses must start with https://")
    s = load_settings()
    s.setdefault("registry_sources", {}).setdefault(st, {})["url"] = url
    _save(s)
    return {"ok": True}


async def _rows(state: str, file: Optional[UploadFile]):
    try:
        if file is not None:
            data = await file.read(rs.MAX_BYTES + 1)
            return rs.parse_registry(data, file.filename or "registry.csv")
        url = ((load_settings().get("registry_sources") or {}).get(state) or {}).get("url")
        if not url:
            raise ValueError("Upload the registry file, or save the address to download it from first.")
        data, name = rs.fetch_registry(url)
        return rs.parse_registry(data, name)
    except ValueError as e:
        logger.warning("Registry file or URL processing failed: %s", e)
        raise HTTPException(400, "Invalid registry data or download address.")


@router.post("/{state}/preview")
async def preview(state: str, file: Optional[UploadFile] = File(None),
                  db: Session = Depends(get_db), _=Depends(_admin)):
    st = _state(state)
    parsed = await _rows(st, file)
    p = rs.plan(db, st, parsed["rows"])
    p["columns"] = {"used": parsed["mapped"], "ignored": parsed["unmapped"]}
    p["rows_skipped"] = parsed["skipped"]
    p["new"] = p["new"][:200]          # enough to review; counts carry the totals
    return p


@router.post("/{state}/import")
async def do_import(state: str, file: Optional[UploadFile] = File(None),
                    db: Session = Depends(get_db), _=Depends(_admin)):
    st = _state(state)
    parsed = await _rows(st, file)

    def remember(state_, counts, when):
        s = load_settings()
        rs.record_import(s, state_, counts, when)
        _save(s)

    p = rs.apply(db, st, parsed["rows"], settings_update=remember)
    return {"ok": True, "counts": p["counts"],
            "message": (f"Imported {p['counts']['new']} new brokers (turned off) and updated "
                        f"{p['counts']['matched']} you already had.")}


@router.get("/brokers")
def registry_brokers(state: Optional[str] = Query(None), enabled: Optional[bool] = Query(None),
                     search: Optional[str] = Query(None), limit: int = Query(200, le=1000),
                     db: Session = Depends(get_db), _=Depends(_admin)):
    q = db.query(Broker).filter(Broker.registry_states.isnot(None))
    if state:
        q = q.filter(Broker.registry_states.like(f"%{_state(state)}%"))
    if enabled is not None:
        q = q.filter(Broker.enabled.is_(enabled))
    if search:
        q = q.filter(Broker.name.ilike(f"%{search}%"))
    rows = q.order_by(Broker.name).limit(limit).all()
    health = {h.broker_id: h for h in db.query(BrokerHealth).filter(
        BrokerHealth.broker_id.in_([b.id for b in rows])).all()} if rows else {}
    return [{"id": b.id, "name": b.name, "website": b.opt_out_url, "origin": b.origin,
             "states": b.registry_states, "enabled": bool(b.enabled),
             "contact_email": b.registry_contact_email,
             "last_seen": b.registry_last_seen.isoformat() if b.registry_last_seen else None,
             "defunct": bool(health.get(b.id) and health[b.id].defunct)} for b in rows]


class EnableIn(BaseModel):
    broker_ids: List[int] = []
    all_registry: bool = False
    acknowledge: bool = False


@router.post("/enable")
def enable(body: EnableIn, db: Session = Depends(get_db), _=Depends(_admin)):
    if not body.acknowledge:
        raise HTTPException(400, rs.REGISTRY_ENABLE_WARNING)
    if not body.all_registry and not body.broker_ids:
        raise HTTPException(400, "Choose which brokers to turn on.")
    n = rs.enable_brokers(db, body.broker_ids, all_registry=body.all_registry)
    return {"ok": True, "enabled": n}


class DisableIn(BaseModel):
    broker_ids: List[int]


@router.post("/disable")
def disable(body: DisableIn, db: Session = Depends(get_db), _=Depends(_admin)):
    n = 0
    for b in db.query(Broker).filter(Broker.id.in_(body.broker_ids), Broker.origin == "registry").all():
        b.enabled = False
        n += 1
    db.commit()
    return {"ok": True, "disabled": n}


@router.post("/check-sites")
def check_sites(db: Session = Depends(get_db), _=Depends(_admin)):
    from ..core.broker_health import probe_sites
    return probe_sites(db, limit=50)
