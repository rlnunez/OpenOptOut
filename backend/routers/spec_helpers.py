"""
Automatic broker steps: AI helper settings, and steps drafted or repaired
automatically (core/ai_helpers.py, core/spec_drafter.py).

  GET    /api/spec-helpers/settings                      helpers and options (no keys)        super admin
  PUT    /api/spec-helpers/settings                      options                              super admin
  PUT    /api/spec-helpers/providers/{pid}               key, model, on/off                   super admin
  POST   /api/spec-helpers/providers/{pid}/test          try the key (or your own model)       super admin
  POST   /api/spec-helpers/local                         connect your own model               super admin
  PUT    /api/spec-helpers/local/{id}  DELETE ...        change or remove it                  super admin
  GET    /api/spec-helpers/drafts                        drafts and fixes                     brokers.manage
  GET    /api/spec-helpers/drafts/{id}                   one, with steps in plain words        brokers.manage
  GET    /api/spec-helpers/drafts/{id}/screenshot        the rehearsal (made-up details)      brokers.manage
  GET    /api/spec-helpers/drafts/{id}/export            as an installable plugin .zip        brokers.manage
  POST   /api/spec-helpers/drafts/{id}/approve|reject|revert|retry                            brokers.manage
  POST   /api/spec-helpers/brokers/{broker_id}/draft     draft steps for a broker now         brokers.manage
  POST   /api/spec-helpers/brokers/{broker_id}/repair    rehearse and fix a broker's steps    brokers.manage
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.access import require_permission
from ..core.auth import require_super_admin
from ..models.database import get_db, SessionLocal, SpecDraft, Broker, User

router = APIRouter(prefix="/api/spec-helpers", tags=["spec-helpers"])
_brokers = require_permission("brokers.manage")


# ── Settings ──────────────────────────────────────────────────────────────────

class OptionsIn(BaseModel):
    order: Optional[List[str]] = None
    repair_broken_steps: Optional[bool] = None
    auto_apply_repairs: Optional[bool] = None
    draft_new_brokers: Optional[bool] = None
    monthly_limit: Optional[int] = None


class ProviderIn(BaseModel):
    enabled: Optional[bool] = None
    model: Optional[str] = None
    api_key: Optional[str] = None      # omit to keep the saved key; "" to remove it


@router.get("/settings")
def get_settings(_=Depends(require_super_admin)):
    from ..core import ai_helpers as ai
    from ..core.settings_store import load_settings
    return ai.public(load_settings())


@router.put("/settings")
def put_settings(body: OptionsIn, _=Depends(require_super_admin)):
    from ..core import ai_helpers as ai
    try:
        return ai.save_options(**body.model_dump())
    except ValueError as e:
        logger.warning("Spec helpers settings update failed: %s", e)
        raise HTTPException(400, "Invalid settings for AI helpers.")


@router.put("/providers/{pid}")
def put_provider(pid: str, body: ProviderIn, _=Depends(require_super_admin)):
    from ..core import ai_helpers as ai
    try:
        return ai.save_provider(pid, body.enabled, body.model, body.api_key)
    except ValueError as e:
        logger.warning("Spec helpers provider update failed: %s", e)
        raise HTTPException(400, "Invalid AI helper provider configuration.")


@router.post("/providers/{pid}/test")
def test_provider(pid: str, _=Depends(require_super_admin)):
    from ..core import ai_helpers as ai
    from ..core.settings_store import load_settings
    cfg = load_settings()
    if pid not in ai.PROVIDERS and pid not in {ai.LOCAL + k for k in ai.settings_of(cfg)["local"]}:
        raise HTTPException(404, "Unknown helper.")
    try:
        return ai.test_connection(cfg, pid)
    except ai.AIError as e:
        logger.warning("Spec helpers provider connection test failed: %s", e)
        return {"ok": False, "message": "Connection test failed. Check the endpoint URL and API key."}


class LocalIn(BaseModel):
    name: str
    base_url: str
    model: str
    api_key: Optional[str] = None      # most local servers need none
    enabled: bool = True


@router.post("/local")
def add_local(body: LocalIn, _=Depends(require_super_admin)):
    """Connect your own model (LM Studio, Ollama, llama.cpp, vLLM...)."""
    from ..core import ai_helpers as ai
    try:
        return ai.save_local(None, body.name, body.base_url, body.model, body.api_key, body.enabled)
    except ValueError as e:
        logger.warning("Spec helpers add local failed: %s", e)
        raise HTTPException(400, "Invalid local model configuration. Check the URL and model name.")


@router.put("/local/{local_id}")
def change_local(local_id: str, body: LocalIn, _=Depends(require_super_admin)):
    from ..core import ai_helpers as ai
    try:
        return ai.save_local(local_id, body.name, body.base_url, body.model, body.api_key, body.enabled)
    except ValueError as e:
        logger.warning("Spec helpers change local failed: %s", e)
        raise HTTPException(400, "Invalid local model configuration. Check the URL and model name.")


@router.delete("/local/{local_id}")
def remove_local(local_id: str, _=Depends(require_super_admin)):
    from ..core import ai_helpers as ai
    return ai.delete_local(local_id)


# ── Drafts ────────────────────────────────────────────────────────────────────

def _steps_in_words(spec_json: Optional[str]) -> list:
    if not spec_json:
        return []
    from ..core.interpreter.broker_spec import BrokerSpec
    from ..core.interpreter.executor import DryRunExecutor
    from ..core.interpreter.compiler import JobStep
    spec = BrokerSpec.from_dict(json.loads(spec_json))
    out = []
    for i, s in enumerate(spec.steps):
        js = JobStep(kind=s.kind, selector=s.selector, value=s.value or (f"{{{s.field}}}" if s.field else ""),
                     url=s.url, text=s.text, timeout_ms=s.timeout_ms, optional=s.optional)
        out.append({"kind": s.kind, "selector": s.selector, "field": s.field, "text": s.text, "url": s.url,
                    "optional": s.optional, "words": DryRunExecutor._describe(i, js)})
    return out


def _changes(prev: Optional[str], new: Optional[str]) -> list:
    """What a repair changed, step by step."""
    if not prev or not new:
        return []
    a, b = json.loads(prev).get("steps", []), json.loads(new).get("steps", [])
    out = []
    for i in range(max(len(a), len(b))):
        x, y = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
        if x == y:
            continue
        if x is None:
            out.append({"step": i + 1, "change": "added", "after": y})
        elif y is None:
            out.append({"step": i + 1, "change": "removed", "before": x})
        else:
            keys = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))
            out.append({"step": i + 1, "change": "changed", "fields": keys,
                        "before": {k: x.get(k) for k in keys}, "after": {k: y.get(k) for k in keys}})
    return out


def _row(r: SpecDraft, broker: Optional[Broker], full: bool = False) -> dict:
    out = {
        "id": r.id, "broker_id": r.broker_id, "broker": broker.name if broker else "?", "kind": r.kind,
        "status": r.status, "source": r.source, "model": r.model, "confidence": r.confidence,
        "reason": r.reason, "notes": r.notes, "warnings": json.loads(r.warnings_json or "[]"),
        "rehearsal": json.loads(r.rehearsal_json or "null"), "has_screenshot": bool(r.screenshot_path),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None, "decided_by": r.decided_by,
    }
    if full:
        out["steps"] = _steps_in_words(r.spec_json)
        out["changes"] = _changes(r.previous_spec_json, r.spec_json)
        out["spec"] = json.loads(r.spec_json) if r.spec_json else None
    elif out["rehearsal"]:
        out["rehearsal"].pop("trace", None)
    return out


@router.get("/drafts")
def list_drafts(status: Optional[str] = Query(None), db: Session = Depends(get_db), _=Depends(_brokers)):
    q = db.query(SpecDraft)
    if status:
        q = q.filter(SpecDraft.status.in_(status.split(",")))
    rows = q.order_by(SpecDraft.created_at.desc()).limit(200).all()
    names = {b.id: b for b in db.query(Broker).filter(Broker.id.in_({r.broker_id for r in rows})).all()} if rows else {}
    return [_row(r, names.get(r.broker_id)) for r in rows]


def _get(db, draft_id: int) -> SpecDraft:
    r = db.query(SpecDraft).filter(SpecDraft.id == draft_id).first()
    if r is None:
        raise HTTPException(404, "That draft doesn't exist.")
    return r


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int, db: Session = Depends(get_db), _=Depends(_brokers)):
    r = _get(db, draft_id)
    return _row(r, db.query(Broker).filter(Broker.id == r.broker_id).first(), full=True)


@router.get("/drafts/{draft_id}/screenshot")
def draft_screenshot(draft_id: int, db: Session = Depends(get_db), _=Depends(_brokers)):
    from ..core.spec_drafter import SCREENSHOTS_DIR
    r = _get(db, draft_id)
    path = os.path.realpath(r.screenshot_path or "")
    if not r.screenshot_path or not path.startswith(os.path.realpath(SCREENSHOTS_DIR) + os.sep) \
            or not os.path.isfile(path):
        raise HTTPException(404, "There's no rehearsal picture for this draft.")
    return FileResponse(path, media_type="image/png")


@router.get("/drafts/{draft_id}/export")
def export_draft(draft_id: int, db: Session = Depends(get_db), _=Depends(_brokers)):
    from ..core.spec_drafter import export_plugin
    r = _get(db, draft_id)
    if not r.spec_json:
        raise HTTPException(400, "This draft has no steps to export.")
    broker = db.query(Broker).filter(Broker.id == r.broker_id).first()
    out = os.path.join(tempfile.mkdtemp(), f"broker-{r.broker_id}-draft-{r.id}.zip")
    try:
        export_plugin(r, broker, out)
    except ValueError as e:
        logger.warning("Spec helpers export draft failed: %s", e)
        raise HTTPException(400, "Could not export draft plugin. Check the draft steps.")
    return FileResponse(out, media_type="application/zip", filename=os.path.basename(out))


def _decide(fn, draft_id: int, db, user):
    from ..core import spec_drafter as sd
    r = _get(db, draft_id)
    try:
        getattr(sd, fn)(db, r, getattr(user, "email", "admin"))
    except ValueError as e:
        logger.warning("Spec helpers draft decision failed: %s", e)
        raise HTTPException(400, "Draft action could not be completed.")
    return _row(r, db.query(Broker).filter(Broker.id == r.broker_id).first())


@router.post("/drafts/{draft_id}/approve")
def approve(draft_id: int, db: Session = Depends(get_db), user: User = Depends(_brokers)):
    return _decide("approve", draft_id, db, user)


@router.post("/drafts/{draft_id}/reject")
def reject(draft_id: int, db: Session = Depends(get_db), user: User = Depends(_brokers)):
    return _decide("reject", draft_id, db, user)


@router.post("/drafts/{draft_id}/revert")
def revert(draft_id: int, db: Session = Depends(get_db), user: User = Depends(_brokers)):
    return _decide("revert", draft_id, db, user)


def _in_background(fn, *args):
    """Drafting drives a browser and may wait minutes for a helper: do it off
    the request, with its own database session."""
    def run():
        db = SessionLocal()
        try:
            fn(db, *args)
        finally:
            db.close()
    threading.Thread(target=run, daemon=True).start()


class StartIn(BaseModel):
    provider: Optional[str] = None


def _check_provider(pid: Optional[str]) -> None:
    from ..core import ai_helpers as ai
    from ..core.settings_store import load_settings
    if pid and pid not in ai.available(load_settings()):
        raise HTTPException(400, "That helper isn't turned on.")


def _broker(db, broker_id: int) -> Broker:
    b = db.query(Broker).filter(Broker.id == broker_id).first()
    if b is None:
        raise HTTPException(404, "That broker doesn't exist.")
    return b


@router.post("/brokers/{broker_id}/draft")
def start_draft(broker_id: int, body: StartIn = StartIn(), db: Session = Depends(get_db), _=Depends(_brokers)):
    from ..core import spec_drafter as sd
    _broker(db, broker_id)
    _check_provider(body.provider)

    def work(s, bid, provider):
        sd.draft_new(s, s.query(Broker).filter(Broker.id == bid).first(), provider or "")
    _in_background(work, broker_id, body.provider)
    return {"started": True, "message": "Drafting has started. It can take a few minutes; this page updates when it's done."}


@router.post("/brokers/{broker_id}/repair")
def start_repair(broker_id: int, body: StartIn = StartIn(), db: Session = Depends(get_db), _=Depends(_brokers)):
    from ..core import spec_drafter as sd
    _broker(db, broker_id)
    _check_provider(body.provider)
    row = SpecDraft(broker_id=broker_id, kind="repair", status="queued", reason="Asked for by an admin.")
    db.add(row)
    db.commit()

    def work(s, draft_id, provider):
        sd.repair(s, s.query(SpecDraft).filter(SpecDraft.id == draft_id).first(), provider or "")
    _in_background(work, row.id, body.provider)
    return {"started": True, "id": row.id,
            "message": "Rehearsing this broker's steps. It can take a few minutes; this page updates when it's done."}


@router.post("/drafts/{draft_id}/retry")
def retry(draft_id: int, body: StartIn = StartIn(), db: Session = Depends(get_db), _=Depends(_brokers)):
    r = _get(db, draft_id)
    if r.kind == "new":
        return start_draft(r.broker_id, body, db)
    return start_repair(r.broker_id, body, db)
