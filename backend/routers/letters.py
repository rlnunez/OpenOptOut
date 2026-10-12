"""
Opt-out letters: the wording sent to brokers, and which broker gets which.

Letters are plugins of type "letters" (core/legal_letters.py). Adding one is a
plugin upload; turning one off is the Plugins page. This API shows them,
previews them with made-up details, and records an admin's choice of letter
for a broker or parent company.

  GET  /api/letters                       letters, and the letter each broker gets     brokers.manage
  GET  /api/letters/{letter_id}/preview   filled in with made-up details               brokers.manage
  PUT  /api/letters/assign                pick a letter for a broker or parent company brokers.manage
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.access import require_permission
from ..models.database import get_db, Broker, ParentCompany, User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/letters", tags=["letters"])
_brokers = require_permission("brokers.manage")

# Made-up details for previews. Never a real person.
SAMPLE = {
    "full_name": "Jordan Example",
    "name_variants": ["Jordan Q. Example", "J. Example"],
    "emails": ["jordan@example.invalid"],
    "phones": ["555-0100"],
    "addresses": ["100 Example Street, Springfield"],
    "age_range": "40-45",
}


def _broker_row(db, b: Broker) -> dict:
    from ..core import legal_letters as ll
    spec = None
    try:
        from ..plugins.broker_addon import get_broker_spec_for_broker
        spec = get_broker_spec_for_broker(db, b)
    except Exception:
        spec = None
    j = spec.effective_jurisdiction() if spec else "US"
    lang = spec.effective_legal_language() if spec else "en"
    choice = ll.letter_choice(admin_choice=b.letter_template or "", spec=spec,
                              jurisdiction=j, legal_language=lang)
    auto = ll.letter_choice(spec=spec, jurisdiction=j, legal_language=lang)
    by_state = sorted(tid for tid, t in ll.templates().items()
                      if t.get("residents_of") and ll._fit(t, j, (t["residents_of"] or [""])[0]))
    return {
        "kind": "broker", "id": b.id, "name": b.name, "jurisdiction": j,
        "chosen": b.letter_template or "", "addon_letter": getattr(spec, "letter", "") if spec else "",
        "uses": choice["template_id"], "source": choice["source"], "missing": choice["missing"],
        "by_state": by_state,
        "automatic": auto["template_id"], "automatic_source": auto["source"],
    }


def _parent_row(p: ParentCompany) -> dict:
    from ..core import legal_letters as ll
    j = p.jurisdiction or "US"
    choice = ll.letter_choice(admin_choice=p.letter_template or "", jurisdiction=j,
                              legal_language=p.locale or "")
    auto = ll.letter_choice(jurisdiction=j, legal_language=p.locale or "")
    by_state = sorted(tid for tid, t in ll.templates().items()
                      if t.get("residents_of") and ll._fit(t, j, (t["residents_of"] or [""])[0]))
    return {
        "kind": "parent", "id": p.id, "name": p.name, "jurisdiction": j,
        "chosen": p.letter_template or "", "addon_letter": "",
        "uses": choice["template_id"], "source": choice["source"], "missing": choice["missing"],
        "by_state": by_state,
        "automatic": auto["template_id"], "automatic_source": auto["source"],
    }


@router.get("")
def list_letters(db: Session = Depends(get_db), _: User = Depends(_brokers)):
    from ..core import legal_letters as ll
    ll.reload()
    letters = ll.catalog()
    brokers = [_broker_row(db, b) for b in db.query(Broker).order_by(Broker.name).all()
               if b.enabled or b.letter_template]
    parents = [_parent_row(p) for p in db.query(ParentCompany).order_by(ParentCompany.name).all()
               if not getattr(p, "is_test", False)]
    for t in letters:
        t["chosen_for"] = sum(1 for r in brokers + parents if r["chosen"] == t["id"])
        t["used_by"] = sum(1 for r in brokers + parents if r["uses"] == t["id"])
    return {"letters": letters, "brokers": brokers, "parents": parents}


@router.get("/{letter_id}/preview")
def preview(letter_id: str, language: str = Query(""), broker: str = Query("Example Broker"),
            _: User = Depends(_brokers)):
    """The letter as a broker would get it, filled in with made-up details."""
    from ..core import legal_letters as ll
    from ..core.optout_email_template import Identifiers
    t = ll.all_templates().get(letter_id)
    if not t:
        raise HTTPException(404, "There's no letter with that name.")
    lang = language if language in t["languages"] else t["default_language"]
    letter = ll.compose_letter(Identifiers(**SAMPLE), (broker or "Example Broker")[:80],
                               jurisdiction=(t.get("jurisdictions") or ["US"])[0].replace("*", "US"),
                               legal_language=lang, residence_state=(t.get("residents_of") or [""])[0],
                               sites=[("Example People Search", "")], request_key="OO-EXAMPLE",
                               template_id=letter_id, allow_disabled=True)
    return {"id": letter_id, "language": letter.language, "languages": sorted(t["languages"]),
            "subject": letter.subject, "body": letter.body, "review_status": letter.review_status,
            "deadline_days": letter.deadline_days}


class Assign(BaseModel):
    kind: str                      # broker | parent
    id: int
    letter_id: Optional[str] = ""  # empty = automatic


@router.put("/assign")
def assign(req: Assign, db: Session = Depends(get_db), user: User = Depends(_brokers)):
    from ..core import legal_letters as ll
    letter_id = (req.letter_id or "").strip()
    if letter_id and letter_id not in ll.templates():
        raise HTTPException(400, "That letter isn't available. It may be turned off on the Plugins page.")
    model = {"broker": Broker, "parent": ParentCompany}.get(req.kind)
    if model is None:
        raise HTTPException(400, "Choose a broker or a parent company.")
    row = db.query(model).filter(model.id == req.id).first()
    if row is None:
        raise HTTPException(404, "That broker or parent company wasn't found.")
    row.letter_template = letter_id or None
    db.commit()
    log.info("Letter for %s %s set to %s by user %s", req.kind, row.id, letter_id or "automatic", user.id)
    return _broker_row(db, row) if req.kind == "broker" else _parent_row(row)
