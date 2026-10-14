"""
Privacy-request pages found on brokers' websites. See core/privacy_finder.py.

  GET  /api/privacy-pages?broker_id=        what was found (all brokers, or one)
  POST /api/privacy-pages/find/{broker_id}  look at a broker's website now (background)
  POST /api/privacy-pages/{id}/dismiss      "that's not it" (remembered)
  POST /api/privacy-pages/{id}/approve-email  use a found address for email opt-outs
"""

import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models.database import get_db, User, Broker, PrivacyPage, SessionLocal
from ..core.access import require_permission
from ..core import privacy_finder as pf

router = APIRouter(prefix="/api/privacy-pages", tags=["privacy-pages"])
_manage = require_permission("brokers.manage")
_RUNNING: set = set()
_LOCK = threading.Lock()


def _out(p: PrivacyPage, names: dict) -> dict:
    return {"id": p.id, "broker_id": p.broker_id, "broker_name": names.get(p.broker_id, ""),
            "url": p.url, "kind": p.kind, "label": p.label, "status": p.status,
            "fillable": p.kind in pf.FILLABLE,
            "found_at": p.found_at.isoformat() if p.found_at else None}


@router.get("")
def list_pages(broker_id: Optional[int] = Query(None), db: Session = Depends(get_db), _=Depends(_manage)):
    q = db.query(PrivacyPage).filter(PrivacyPage.status != "dismissed")
    if broker_id is not None:
        q = q.filter(PrivacyPage.broker_id == broker_id)
    rows = q.order_by(PrivacyPage.found_at.desc()).limit(500).all()
    names = {b.id: b.name for b in db.query(Broker).filter(Broker.id.in_({r.broker_id for r in rows})).all()} if rows else {}
    rows.sort(key=lambda p: (pf.PRIORITY.get(p.kind, 9), -(p.score or 0)))
    checked = None
    if broker_id is not None:
        b = db.query(Broker).filter(Broker.id == broker_id).first()
        checked = b.privacy_checked_at.isoformat() if b and b.privacy_checked_at else None
    return {"pages": [_out(p, names) for p in rows], "checked_at": checked,
            "running": broker_id in _RUNNING if broker_id is not None else bool(_RUNNING)}


def _run(broker_id: int):
    db = SessionLocal()
    try:
        b = db.query(Broker).filter(Broker.id == broker_id).first()
        if b is not None:
            pf.run_for_broker(db, b)
    finally:
        db.close()
        with _LOCK:
            _RUNNING.discard(broker_id)


@router.post("/find/{broker_id}")
def find_now(broker_id: int, db: Session = Depends(get_db), _=Depends(_manage)):
    b = db.query(Broker).filter(Broker.id == broker_id).first()
    if not b:
        raise HTTPException(404, "That site is gone.")
    with _LOCK:
        if broker_id in _RUNNING:
            return {"started": False, "running": True}
        _RUNNING.add(broker_id)
    threading.Thread(target=_run, args=(broker_id,), daemon=True).start()
    return {"started": True, "running": True,
            "message": f"Looking at {b.name}'s website. This takes up to a minute."}


def _page(db, page_id) -> PrivacyPage:
    p = db.query(PrivacyPage).filter(PrivacyPage.id == page_id).first()
    if not p:
        raise HTTPException(404, "That result is gone.")
    return p


@router.post("/{page_id}/dismiss")
def dismiss(page_id: int, db: Session = Depends(get_db), _=Depends(_manage)):
    p = _page(db, page_id)
    p.status = "dismissed"
    db.commit()
    return {"ok": True}


@router.post("/{page_id}/approve-email")
def approve_email(page_id: int, db: Session = Depends(get_db), user: User = Depends(_manage)):
    p = _page(db, page_id)
    if p.kind != "email":
        raise HTTPException(400, "Only email addresses can be approved.")
    addr = pf.approve_email(db, p, user.full_name or user.email)
    return {"ok": True, "message": f"Email opt-outs for this broker will go to {addr}."}
