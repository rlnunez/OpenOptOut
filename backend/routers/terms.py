"""
Terms and limits (core/terms.py).

  GET  /api/terms/status     what the signed-in person still has to accept      signed in
  POST /api/terms/accept     accept one: {kind, version}                         signed in
  GET  /api/terms/public     the operator's terms, if turned on (the Terms page) public
  GET  /api/terms/settings   the operator's terms, counts, template notes left   super admin
  PUT  /api/terms/settings   change them: {enabled, operator, contact, text}     super admin
  GET  /api/terms/template   the starting draft, filled in with operator/contact super admin
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core import terms as T
from ..core.auth import get_current_user, require_super_admin
from ..core.settings_store import load_settings, save_settings
from ..models.database import get_db, User

router = APIRouter(prefix="/api/terms", tags=["terms"])


def _save(s: dict) -> None:
    save_settings(s)


def _defaults(s: dict) -> dict:
    """Who runs this, from Branding, for the screens and the template."""
    b = s.get("branding") or {}
    c = T.config(s)
    name = b.get("system_name") or ""
    if name.strip().lower() == "openoptout":      # the default name says nothing about who runs it
        name = ""
    return {"operator": c["operator"] or name,
            "contact": c["contact"] or b.get("contact_email") or b.get("support_url") or ""}


def _public(c: dict, s: dict) -> dict:
    d = _defaults(s)
    return {"enabled": c["enabled"], "operator": d["operator"], "contact": d["contact"],
            "text": c["text"] if c["enabled"] else "", "version": c["version"] if c["enabled"] else 0,
            "updated_at": c["updated_at"], "terms_url": (s.get("branding") or {}).get("terms_url") or ""}


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = load_settings()
    c = T.config(s)
    return {"needs": T.needs(db, user, s), "limits_version": T.LIMITS_VERSION,
            "notice_version": T.NOTICE_VERSION, "terms": _public(c, s)}


class Accept(BaseModel):
    kind: str
    version: int


@router.post("/accept")
def accept(req: Accept, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = load_settings()
    try:
        T.accept(db, user, req.kind, req.version, s)
    except ValueError as e:
        raise HTTPException(409 if "changed" in str(e) else 400, str(e))
    return {"needs": T.needs(db, user, s)}


@router.get("/public")
def public():
    s = load_settings()
    return _public(T.config(s), s)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    s = load_settings()
    c = T.config(s)
    c.pop("digest", None)
    return {**c, "defaults": _defaults(s), "unfinished": T.unfinished(c["text"]),
            "counts": T.counts(db, s), "terms_url": (s.get("branding") or {}).get("terms_url") or ""}


class TermsIn(BaseModel):
    enabled: Optional[bool] = None
    operator: Optional[str] = None
    contact: Optional[str] = None
    text: Optional[str] = None


@router.put("/settings")
def put_settings(req: TermsIn, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    s = load_settings()
    try:
        T.save(s, req.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    _save(s)
    return get_settings(db, _)


@router.get("/template")
def get_template(operator: str = "", contact: str = "", _: User = Depends(require_super_admin)):
    s = load_settings()
    d = _defaults(s)
    return {"text": T.template(operator or d["operator"], contact or d["contact"])}
