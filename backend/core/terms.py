"""
Terms and limits: what people are asked to read and accept.

  limits          An admin (super admin), at first sign-in: "What OpenOptOut
                  can and can't do". The wording is in the app (translated);
                  LIMITS_VERSION goes up when it changes, so admins are asked
                  again.
  notice          Everyone else, at first sign-in: "How OpenOptOut works for
                  you". NOTICE_VERSION, the same way.
  operator_terms  The terms the people running this server wrote (Settings →
                  Terms), when they turn them on. Their version goes up each
                  time they're saved with changes, and people are asked again.
  acting_for      A parent who adds someone without a sign-in confirms they
                  may act for that person (they agreed, or a parent or legal
                  guardian). Recorded per person added.

Each acceptance is a TermsAcceptance row: who, what kind, which version, when.
Never a name or a detail. The wording of `limits` and `notice` lives in
frontend/src/components/TermsGate.jsx; the template for operator terms is
core/legal_templates/terms_template.md. All of it is a draft that no lawyer has
reviewed yet.
"""
from __future__ import annotations

import os
import re
from .time_utils import utc_now, utc_iso
from typing import Optional

LIMITS_VERSION = 1
NOTICE_VERSION = 1
KINDS = ("limits", "notice", "operator_terms", "acting_for")
MAX_TEXT = 40_000
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legal_templates", "terms_template.md")
# Notes in the template that the operator should replace: "[Say who, ...]".
TODO = re.compile(r"\[(?:Your organization|how to reach you)\]|\[(?:Say|Add) [^\]]*\]")


def config(settings: Optional[dict] = None) -> dict:
    """The operator's terms: {enabled, operator, contact, text, version,
    updated_at, digest (of the version people last accepted)}."""
    if settings is None:
        from .settings_store import load_settings
        settings = load_settings()
    t = dict(settings.get("terms") or {})
    return {"enabled": bool(t.get("enabled")), "operator": t.get("operator") or "",
            "contact": t.get("contact") or "", "text": t.get("text") or "",
            "version": int(t.get("version") or 0), "updated_at": t.get("updated_at") or "",
            "digest": t.get("digest") or ""}


def _digest(c: dict) -> str:
    import hashlib
    return hashlib.sha256("\x00".join((c["operator"], c["contact"], c["text"])).encode()).hexdigest()


def template(operator: str = "", contact: str = "", date: str = "") -> str:
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        text = f.read()
    return (text.replace("{operator}", operator or "[Your organization]")
                .replace("{contact}", contact or "[how to reach you]")
                .replace("{date}", date or utc_now().date().isoformat()))


def unfinished(text: str) -> list:
    """Template notes still in the text ("[Say who, ...]")."""
    return [m.group(0) for m in TODO.finditer(text or "")]


def save(settings: dict, data: dict) -> dict:
    """Apply an admin's changes. The version goes up when the text, operator or
    contact changes while the terms are on (or as they're turned on), so
    everyone is asked again."""
    old = config(settings)
    new = dict(old)
    for k in ("operator", "contact", "text"):
        if k in data and data[k] is not None:
            v = str(data[k]).strip() if k != "text" else str(data[k]).replace("\r\n", "\n").strip()
            if k != "text" and len(v) > 200:
                raise ValueError(f"The {k} is too long (200 characters at most).")
            new[k] = v
    if len(new["text"]) > MAX_TEXT:
        raise ValueError("The terms are too long (40,000 characters at most).")
    if "enabled" in data and data["enabled"] is not None:
        new["enabled"] = bool(data["enabled"])
    if new["enabled"] and not new["text"]:
        raise ValueError("Write the terms (or start from the template) before turning them on.")
    if new["enabled"] and unfinished(new["text"]):
        raise ValueError("Fill in the notes in square brackets, like " + unfinished(new["text"])[0]
                         + ", before turning the terms on.")
    # A new version whenever the terms people see differ from the last version
    # they were asked to accept, including changes made while turned off.
    # Turning them back on unchanged keeps the version, so nobody is asked twice.
    digest = _digest(new)
    if new["enabled"] and digest != old["digest"]:
        new["version"] = old["version"] + 1
        new["digest"] = digest
        new["updated_at"] = utc_iso()
    settings["terms"] = new
    return new


def _accepted(db, user_id: int, kind: str) -> int:
    from sqlalchemy import func
    from ..models.database import TermsAcceptance
    v = db.query(func.max(TermsAcceptance.version)).filter(
        TermsAcceptance.user_id == user_id, TermsAcceptance.kind == kind).scalar()
    return int(v or 0)


def needs(db, user, settings: Optional[dict] = None) -> list:
    """What this person still has to accept, in order: [{"kind", "version"}]."""
    out = []
    first = "limits" if user.is_super_admin else "notice"
    want = LIMITS_VERSION if first == "limits" else NOTICE_VERSION
    if _accepted(db, user.id, first) < want:
        out.append({"kind": first, "version": want})
    c = config(settings)
    if c["enabled"] and c["version"] and _accepted(db, user.id, "operator_terms") < c["version"]:
        out.append({"kind": "operator_terms", "version": c["version"]})
    return out


def accept(db, user, kind: str, version: int, settings: Optional[dict] = None) -> None:
    """Record an acceptance of the version that's current now. Refuses a
    version that isn't current, so an old screen can't accept new terms."""
    from ..models.database import TermsAcceptance
    current = {"limits": LIMITS_VERSION, "notice": NOTICE_VERSION,
               "operator_terms": config(settings)["version"]}.get(kind)
    if current is None:
        raise ValueError("That isn't something to accept.")
    if kind == "limits" and not user.is_super_admin:
        raise ValueError("Only an admin accepts these.")
    if not current or int(version) != current:
        raise ValueError("These terms changed while you were reading. Reload the page to see the new ones.")
    db.add(TermsAcceptance(user_id=user.id, kind=kind, version=current))
    db.commit()


def record_acting_for(db, user, subject_user_id: int) -> None:
    from ..models.database import TermsAcceptance
    db.add(TermsAcceptance(user_id=user.id, kind="acting_for", version=1, subject_user_id=subject_user_id))


def counts(db, settings: Optional[dict] = None) -> dict:
    """For the admin page: how many people who sign in have accepted the
    current operator terms. Counts only."""
    from ..models.database import TermsAcceptance, User
    c = config(settings)
    people = db.query(User).filter(User.hashed_password.isnot(None) | User.auth_source.isnot(None)).count()
    accepted = 0
    if c["version"]:
        accepted = db.query(TermsAcceptance.user_id).filter(
            TermsAcceptance.kind == "operator_terms", TermsAcceptance.version == c["version"]).distinct().count()
    return {"people": people, "accepted": accepted}
