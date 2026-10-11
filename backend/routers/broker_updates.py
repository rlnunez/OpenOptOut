"""
Broker update notifications for administrators. See core/broker_updates.py.

  GET  /api/broker-updates            recent updates (?unread=true for new ones only)
  GET  /api/broker-updates/count      unread count, for the sidebar badge
  POST /api/broker-updates/read       mark read ({"ids": [...]}, or all when empty)
  GET  /api/broker-updates/settings   email digest setting
  PUT  /api/broker-updates/settings   off | daily | weekly
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..core.access import require_permission
from ..core.settings_store import load_settings, SETTINGS_FILE
from ..core import broker_updates as bu

router = APIRouter(prefix="/api/broker-updates", tags=["broker-updates"])
_admin = require_permission("brokers.manage")


@router.get("")
def list_updates(unread: bool = Query(False), db: Session = Depends(get_db), _=Depends(_admin)):
    return {"updates": bu.listing(db, unread_only=unread), "unread": bu.unread_count(db)}


@router.get("/count")
def count(db: Session = Depends(get_db), _=Depends(_admin)):
    return {"count": bu.unread_count(db)}


class ReadIn(BaseModel):
    ids: Optional[List[int]] = None


@router.post("/read")
def read(body: ReadIn, db: Session = Depends(get_db), _=Depends(_admin)):
    return {"marked": bu.mark_read(db, body.ids)}


@router.get("/settings")
def get_settings(_=Depends(_admin)):
    return bu.settings_of(load_settings())


class SettingsIn(BaseModel):
    email_digest: str = "daily"


@router.put("/settings")
def put_settings(body: SettingsIn, _=Depends(require_permission("settings.system"))):
    if body.email_digest not in ("off", "daily", "weekly"):
        raise HTTPException(400, "Choose off, daily or weekly.")
    cfg = load_settings()
    cfg["broker_updates"] = {"email_digest": body.email_digest}
    with open(SETTINGS_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    return {"ok": True}
