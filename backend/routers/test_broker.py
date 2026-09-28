"""
Test broker — validate real email delivery end to end, safely.

Creates a dedicated TEST parent company + child broker whose opt-out address is
one the operator chooses (their own inbox), then sends a real opt-out through the
exact production path: template composition -> unified send (provider plugin with
OAuth auto-refresh, or SMTP fallback) -> recipient enforcement -> effectiveness
tracking. The only differences from a real send are the destination (the
operator's address) and a "[PrivacyShield TEST]" subject prefix.

Fencing — the test pair can never leak into real work:
  - is_test=True on both the parent and the broker;
  - the broker is kept DISABLED (batch runners skip disabled brokers);
  - discovery and both batch runners also skip is_test brokers explicitly.
So the test broker only ever fires through POST /api/test-broker/send.

Endpoints (super admin only):
  GET    /api/test-broker        — current test broker, if any
  POST   /api/test-broker/setup  — create/update it with your chosen address
  POST   /api/test-broker/send   — send a test opt-out (real member or fake identity)
  DELETE /api/test-broker        — remove it
"""

import re
from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import (get_db, User, Broker, ParentCompany, FamilyMember,
                               OptOutMethod)
from ..core.auth import get_current_user
from ..core.settings_store import load_settings

router = APIRouter(prefix="/api/test-broker", tags=["test-broker"])

TEST_PARENT_NAME = "PrivacyShield Test Broker"
TEST_BROKER_NAME = "PrivacyShield Test Site"
TEST_SUBJECT_PREFIX = "[PrivacyShield TEST] "
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _admin(user: User):
    from ..core.access import has_permission, PERMISSIONS
    if not has_permission(user, "brokers.automation"):
        raise HTTPException(403, f"This needs the '{PERMISSIONS['brokers.automation']['label']}' permission")


def _get_test_parent(db: Session) -> Optional[ParentCompany]:
    return db.query(ParentCompany).filter(ParentCompany.is_test.is_(True)).first()


def _describe(parent: Optional[ParentCompany]) -> dict:
    if not parent:
        return {"exists": False}
    broker = next((c for c in (parent.children or []) if getattr(c, "is_test", False)), None)
    return {
        "exists": True,
        "parent_id": parent.id,
        "name": parent.name,
        "optout_email": parent.optout_email,
        "broker_id": broker.id if broker else None,
        "emails_sent": parent.emails_sent or 0,
        "emails_failed": parent.emails_failed or 0,
    }


def _fake_member():
    """A clearly-fake identity so a test can run without creating a family member."""
    def ident(kind, value, primary=True):
        return SimpleNamespace(kind=kind, value=value, is_primary=primary)
    return SimpleNamespace(
        id=0,
        full_name="Test Person",
        dob=None,
        identities=[
            ident("name", "Test Person"),
            ident("name", "T. Person", primary=False),
            ident("email", "test.person@example.com"),
            ident("phone", "555-0100"),
            ident("address", "123 Test St, Anytown, ST 00000"),
        ],
    )


@router.get("")
def get_test_broker(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    return _describe(_get_test_parent(db))


class SetupIn(BaseModel):
    optout_email: str


@router.post("/setup")
def setup_test_broker(body: SetupIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Create (or update the address of) the fenced-off test parent + broker."""
    _admin(user)
    addr = body.optout_email.strip()
    if not _EMAIL_RE.match(addr):
        raise HTTPException(400, "Enter a valid email address you control")

    parent = _get_test_parent(db)
    if not parent:
        parent = ParentCompany(
            name=TEST_PARENT_NAME, optout_email=addr, locale="en", is_test=True,
            notes="Test broker for validating email delivery. Sends only via the "
                  "explicit test-send action; never included in real runs.",
        )
        db.add(parent)
        db.flush()
    else:
        parent.optout_email = addr

    broker = (db.query(Broker)
              .filter(Broker.parent_company_id == parent.id, Broker.is_test.is_(True))
              .first())
    if not broker:
        broker = Broker(
            name=TEST_BROKER_NAME, method=OptOutMethod.email,
            enabled=False,          # fence: batch runners skip disabled brokers
            is_test=True,           # fence: discovery + runners skip test brokers
            parent_company_id=parent.id,
            notes="Test site under the PrivacyShield test broker. Not a real broker.",
        )
        db.add(broker)
    db.commit()
    db.refresh(parent)
    return _describe(parent)


class SendIn(BaseModel):
    member_id: Optional[int] = None   # omit to use the built-in fake identity


@router.post("/send")
def send_test_optout(body: SendIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """
    Send one test opt-out through the real production path to the test broker's
    address. Returns exactly what happened (transport used, recipient, subject,
    error) so you can confirm delivery end to end.
    """
    _admin(user)
    parent = _get_test_parent(db)
    if not parent:
        raise HTTPException(400, "Set up the test broker first (choose an address)")

    if body.member_id:
        member = db.query(FamilyMember).filter(FamilyMember.id == body.member_id).first()
        if not member:
            raise HTTPException(404, "Family member not found")
        identity = "family member"
    else:
        member = _fake_member()
        identity = "built-in fake identity"

    from ..core.optout_engine import send_parent_optout_detailed
    detail = send_parent_optout_detailed(
        member, parent, load_settings(), db,
        discovered_urls={},              # test send: no discovery lookup needed
        subject_prefix=TEST_SUBJECT_PREFIX,
    )
    detail["identity"] = identity
    return detail


@router.delete("")
def delete_test_broker(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    parent = _get_test_parent(db)
    if not parent:
        return {"deleted": False}
    for child in list(parent.children or []):
        if getattr(child, "is_test", False):
            db.delete(child)
        else:
            child.parent_company_id = None   # never delete a real broker
    db.delete(parent)
    db.commit()
    return {"deleted": True}
