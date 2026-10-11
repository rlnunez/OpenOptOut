"""
Removal checks. See core/verification.py.

  GET  /api/verification/summary          gone / still listed / couldn't check, and recent checks
  POST /api/verification/request/{id}     check one request now
  POST /api/verification/run              run today's checks now (admin)
  GET  /api/verification/settings         (admin)
  PUT  /api/verification/settings         (admin)
"""

import json
import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, User, RemovalRequest, SessionLocal
from ..core.auth import get_current_user, get_accessible_member_ids, assert_can_edit
from ..core.access import require_permission
from ..core.settings_store import load_settings, SETTINGS_FILE
from ..core import verification as vf

router = APIRouter(prefix="/api/verification", tags=["verification"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    out = vf.summary(db, get_accessible_member_ids(db, user))
    out["enabled"] = vf.settings_of(load_settings())["enabled"]
    return out


@router.post("/request/{req_id}")
def check_one(req_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(RemovalRequest).filter(RemovalRequest.id == req_id).first()
    if not r:
        raise HTTPException(404, "That request is gone.")
    assert_can_edit(db, user, r.member_id)
    res = vf.verify_request(db, r, load_settings())
    words = {"gone": "The listing is gone.", "listed": "The listing is still up.",
             "not_found": "Nothing turned up, but the listing itself couldn't be seen.",
             "blocked": "The site refused the check. It will be tried again later.",
             "unknown": "Couldn't check right now."}
    msg = words.get(res["verdict"], "")
    if res["action"].startswith("resend"):
        msg += " The opt-out will be sent again."
    elif res["action"] == "confirmed":
        msg += " Marked removed."
    return {**res, "message": msg}


def _run():
    db = SessionLocal()
    try:
        vf.run_daily(db, load_settings())
    finally:
        db.close()


@router.post("/run")
def run_now(_=Depends(require_permission("scheduler.manage"))):
    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "message": "Checking removals now. Results show up here in a few minutes."}


@router.get("/settings")
def get_settings(_=Depends(require_permission("settings.system"))):
    return vf.settings_of(load_settings())


class SettingsIn(BaseModel):
    enabled: bool = True
    use_browser: bool = True
    per_day: int = 40


@router.put("/settings")
def put_settings(body: SettingsIn, _=Depends(require_permission("settings.system"))):
    cfg = load_settings()
    cur = vf.settings_of(cfg)
    cur.update(enabled=body.enabled, use_browser=body.use_browser, per_day=max(1, min(int(body.per_day), 500)))
    cfg["verification"] = cur
    with open(SETTINGS_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    return {"ok": True}
