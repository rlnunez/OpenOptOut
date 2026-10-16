"""
Broker confirmation links. See core/confirm_links.py.

  GET /api/confirm-links/summary    waiting / clicked / need a person (your family)
  GET /api/confirm-links/settings   auto-click options (admin)
  PUT /api/confirm-links/settings   save them (admin)

Links that need a person show up on the checklist ("Confirm these opt-outs").
"""

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.limits import LimitedModel
from ..models.database import get_db, User, ConfirmationLink, RemovalRequest
from ..core.auth import get_current_user, get_accessible_member_ids
from ..core.access import require_permission
from ..core.settings_store import load_settings, save_settings, SETTINGS_FILE
from ..core import confirm_links as cl

router = APIRouter(prefix="/api/confirm-links", tags=["confirm-links"])
_admin = require_permission("settings.system")


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = get_accessible_member_ids(db, user)
    counts = {"pending": 0, "clicked": 0, "needs_person": 0, "done": 0}
    if ids:
        rows = (db.query(ConfirmationLink.status)
                  .join(RemovalRequest, RemovalRequest.id == ConfirmationLink.request_id)
                  .filter(RemovalRequest.member_id.in_(ids)).all())
        for (st,) in rows:
            counts[st] = counts.get(st, 0) + 1
    s = cl.settings_of(load_settings())
    return {**counts, "auto_click": s["auto_click"]}


@router.get("/settings")
def get_settings(_=Depends(_admin)):
    return cl.settings_of(load_settings())


class SettingsIn(LimitedModel):
    auto_click: bool = True
    use_browser: bool = True


@router.put("/settings")
def put_settings(body: SettingsIn, _=Depends(_admin)):
    cfg = load_settings()
    cfg["confirm_links"] = {"auto_click": body.auto_click, "use_browser": body.use_browser}
    save_settings(cfg)
    return {"ok": True}
