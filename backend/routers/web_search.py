"""
General web search. See core/web_search.py.

  GET  /api/web-search/settings          provider and options (admin)
  PUT  /api/web-search/settings          save them (admin)
  GET  /api/web-search/status            is it set up? (anyone — drives the UI)
  POST /api/web-search/run/{member_id}   search now (runs in the background)
  GET  /api/web-search/hits/{member_id}  results: added, waiting for review, dismissed
  POST /api/web-search/hits/{hit_id}/add      "That's me" → removal cycle
  POST /api/web-search/hits/{hit_id}/dismiss  "Not me" (remembered)
"""

import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, User, WebSearchHit, Broker, SessionLocal, FamilyMember
from ..core.auth import get_current_user, assert_can_view, assert_can_edit
from ..core.access import require_permission
from ..core.settings_store import load_settings, SETTINGS_FILE
from ..core import web_search as wsm

router = APIRouter(prefix="/api/web-search", tags=["web-search"])
_admin = require_permission("settings.system")   # privacy & automation settings

# member_id -> {"running": bool, "stats": {...}, "error": str}
_RUNS: dict = {}
_LOCK = threading.Lock()


def _save(cfg: dict):
    import json
    with open(SETTINGS_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


@router.get("/settings")
def get_settings(_=Depends(_admin)):
    ws = wsm.settings_of(load_settings())
    return {"enabled": ws["enabled"], "provider": ws["provider"], "searxng_url": ws["searxng_url"],
            "brave_key_set": bool(ws["brave_key_enc"]), "max_queries": ws["max_queries"],
            "weekly": ws["weekly"], "auto_add_strong": ws["auto_add_strong"],
            "privacy_note": wsm.PRIVACY_NOTE}


class SettingsIn(BaseModel):
    enabled: bool = False
    provider: str = ""
    searxng_url: str = ""
    brave_key: Optional[str] = None      # None = keep the saved key; "" = clear it
    max_queries: int = 12
    weekly: bool = False
    auto_add_strong: bool = True


@router.put("/settings")
def put_settings(body: SettingsIn, _=Depends(_admin)):
    if body.provider not in ("", "searxng", "brave"):
        raise HTTPException(400, "Choose SearXNG or Brave Search.")
    url = body.searxng_url.strip()
    if url and not url.startswith(("https://", "http://")):
        raise HTTPException(400, "The SearXNG address should start with https:// (or http:// on your own network).")
    cfg = load_settings()
    ws = wsm.settings_of(cfg)
    ws.update(enabled=body.enabled, provider=body.provider, searxng_url=url,
              max_queries=max(1, min(int(body.max_queries or 12), 40)),
              weekly=body.weekly, auto_add_strong=body.auto_add_strong)
    if body.brave_key is not None:
        from ..core.oauth_engine import _encrypt
        ws["brave_key_enc"] = _encrypt(body.brave_key.strip()) if body.brave_key.strip() else ""
    if ws["enabled"] and not wsm.configured(ws):
        raise HTTPException(400, "Fill in the SearXNG address or the Brave API key before turning this on.")
    cfg["web_search"] = ws
    _save(cfg)
    return {"ok": True}


@router.get("/status")
def status(user: User = Depends(get_current_user)):
    ws = wsm.settings_of(load_settings())
    return {"available": wsm.configured(ws), "privacy_note": wsm.PRIVACY_NOTE}


def _run(member_id: int):
    db = SessionLocal()
    try:
        member = db.query(FamilyMember).filter(FamilyMember.id == member_id).first()
        stats = wsm.run_for_member(db, member, load_settings())
        with _LOCK:
            _RUNS[member_id] = {"running": False, "stats": stats, "error": ""}
    except Exception as e:
        with _LOCK:
            _RUNS[member_id] = {"running": False, "stats": None, "error": str(e)}
    finally:
        db.close()


@router.post("/run/{member_id}")
def run(member_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_can_edit(db, user, member_id)
    if not wsm.configured(wsm.settings_of(load_settings())):
        raise HTTPException(400, "Web search isn't set up yet. Ask your administrator to turn it on.")
    with _LOCK:
        if (_RUNS.get(member_id) or {}).get("running"):
            return {"started": False, "running": True}
        _RUNS[member_id] = {"running": True, "stats": None, "error": ""}
    threading.Thread(target=_run, args=(member_id,), daemon=True).start()
    return {"started": True, "running": True}


@router.get("/hits/{member_id}")
def hits(member_id: int, status: Optional[str] = Query(None),
         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_can_view(db, user, member_id)
    q = db.query(WebSearchHit).filter(WebSearchHit.member_id == member_id)
    if status:
        q = q.filter(WebSearchHit.status == status)
    rows = q.order_by(WebSearchHit.found_at.desc()).limit(300).all()
    brokers = {b.id: b.name for b in db.query(Broker).filter(
        Broker.id.in_([h.broker_id for h in rows if h.broker_id])).all()} if rows else {}
    order = {"strong": 0, "medium": 1, "weak": 2}
    out = [{"id": h.id, "url": h.url, "domain": h.domain, "title": h.title, "snippet": h.snippet,
            "strength": h.strength, "matched_on": h.matched_on, "query_label": h.query_label,
            "broker_name": brokers.get(h.broker_id), "status": h.status,
            "found_at": h.found_at.isoformat() if h.found_at else None} for h in rows]
    out.sort(key=lambda h: (h["status"] != "new", order.get(h["strength"], 3)))
    return {"hits": out, "run": _RUNS.get(member_id) or {"running": False}}


def _hit(db, user, hit_id) -> WebSearchHit:
    h = db.query(WebSearchHit).filter(WebSearchHit.id == hit_id).first()
    if not h:
        raise HTTPException(404, "That result is gone.")
    assert_can_edit(db, user, h.member_id)
    return h


@router.post("/hits/{hit_id}/add")
def add(hit_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    h = _hit(db, user, hit_id)
    member = db.query(FamilyMember).filter(FamilyMember.id == h.member_id).first()
    try:
        return wsm.add_hit(db, h, member)
    except ValueError as e:
        raise HTTPException(400, str(e))


class DismissIn(BaseModel):
    reason: str = "not_me"


@router.post("/hits/{hit_id}/dismiss")
def dismiss(hit_id: int, body: DismissIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wsm.dismiss_hit(db, _hit(db, user, hit_id), body.reason)
    return {"ok": True}
