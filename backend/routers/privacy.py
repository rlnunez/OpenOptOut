"""
OpenOptOut's own privacy record and people's rights over their data.

  GET    /api/privacy/record           what the install keeps, why, protection, retention (admins)
  GET    /api/privacy/access-log       staff access to people's details (admins)
  GET    /api/privacy/my-access-log    who outside the family looked at my family's details
  GET    /api/privacy/export           everything about me and my family, as a file
  GET    /api/privacy/export/{id}      everything about one person (staff answering a request)
  POST   /api/privacy/purge            apply the retention schedule now (super admin)
  DELETE /api/privacy/me               delete my account, my details and people only I manage
"""
import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.limits import LimitedModel
from ..models.database import get_db, User, FamilyMember, AccessLog, ProfileAccess, UserRole
from ..core.auth import get_current_user, assert_can_view, require_super_admin
from ..core.access import require_permission, has_permission
from ..core.settings_store import load_settings
from ..core import privacy_record as pr

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


def _download(data: dict, name: str):
    # Every current caller passes a fixed string or an int-derived name, so
    # there's no live injection path today — but this helper has no way to
    # know that about a future caller, so it sanitizes regardless (RFC 6266 /
    # ASVS 5.4.1-5.4.2): strip CR/LF (header/line injection) and escape the
    # backslash/quote that would otherwise break out of the quoted-string.
    safe_name = re.sub(r"[\r\n]", "", name).replace("\\", "\\\\").replace('"', '\\"')
    return JSONResponse(content=data, headers={"Content-Disposition": f'attachment; filename="{safe_name}"'})


@router.get("/record")
def privacy_record(db: Session = Depends(get_db), _=Depends(require_permission("settings.system"))):
    return pr.record(db, load_settings())


def _log_out(rows):
    return [{"at": r.at.isoformat(), "who": r.actor_name, "person": r.member_name,
             "action": r.action, "detail": r.detail} for r in rows]


@router.get("/access-log")
def access_log(member_id: int = None, limit: int = Query(200, ge=1, le=2000),
               db: Session = Depends(get_db), _=Depends(require_permission("logs.view"))):
    q = db.query(AccessLog)
    if member_id is not None:
        q = q.filter(AccessLog.member_id == member_id)
    return _log_out(q.order_by(AccessLog.at.desc()).limit(limit).all())


@router.get("/my-access-log")
def my_access_log(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..core.compliance import own_member_ids
    ids = own_member_ids(db, current_user)
    if not ids:
        return []
    rows = db.query(AccessLog).filter(AccessLog.member_id.in_(ids)).order_by(AccessLog.at.desc()).limit(200).all()
    return _log_out(rows)


@router.get("/export")
def export_mine(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..core.compliance import own_member_ids
    ids = own_member_ids(db, current_user)
    if not ids:
        return _download({"exported_at": datetime.utcnow().isoformat(), "people": []}, "openoptout-my-data.json")
    members = db.query(FamilyMember).filter(FamilyMember.id.in_(ids)).all()
    return _download({"exported_at": datetime.utcnow().isoformat(),
                      "people": [pr.export_person(db, m) for m in members]}, "openoptout-my-data.json")


@router.get("/export/{member_id}")
def export_person(member_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    member = assert_can_view(db, current_user, member_id)
    pr.log_access(db, current_user, member, "export", "full data export")
    return _download(pr.export_person(db, member), f"openoptout-person-{member_id}.json")


@router.post("/purge")
def purge_now(db: Session = Depends(get_db), _=Depends(require_super_admin)):
    cfg = load_settings()
    stats = pr.purge(db, cfg)
    pr.mark_purged(stats)
    return {"retention_days": pr.retention_days(cfg), "removed": stats}


class DeleteMe(LimitedModel):
    confirm: str


@router.delete("/me")
def delete_me(data: DeleteMe, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Delete my account and everything about me. People I added who have no
    sign-in and nobody else managing them go too; anyone shared with another
    parent stays with them.
    """
    if (data.confirm or "").strip().upper() != "DELETE":
        raise HTTPException(400, 'Type DELETE to confirm.')
    if current_user.role == UserRole.super_admin and \
            db.query(User).filter(User.role == UserRole.super_admin).count() <= 1:
        raise HTTPException(400, "You're the only main administrator. Make someone else one first.")
    from ..core.people import delete_person
    removed = []
    for g in db.query(ProfileAccess).filter(ProfileAccess.manager_id == current_user.id).all():
        dep = g.managed
        if dep is None or dep.id == current_user.id or dep.can_login:
            continue
        others = db.query(ProfileAccess).filter(ProfileAccess.managed_id == dep.id,
                                                ProfileAccess.manager_id != current_user.id).count()
        if others == 0:
            removed.append(dep.full_name)
            delete_person(db, dep)
    delete_person(db, current_user)
    db.commit()
    return {"deleted": True, "also_removed": removed}
