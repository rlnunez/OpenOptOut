"""
Family email inboxes.

Every user connects their own inbox; a parent can connect several and assign
each to a family member. Opt-outs for a member are sent from, and answered at,
that inbox — the system inbox only sends notifications. See core/mailboxes.py.

  GET    /api/mailboxes                 my inboxes + the members I manage and which inbox each uses
  GET    /api/mailboxes/providers       which kinds of inbox can be connected here
  GET    /api/mailboxes/me              does my own profile have a usable inbox? (for the sign-in prompt)
  POST   /api/mailboxes                 add an inbox (OAuth: returns the sign-in link)
  POST   /api/mailboxes/{id}/reconnect  new sign-in link for an OAuth inbox
  POST   /api/mailboxes/{id}/check-plus send the +address test email
  POST   /api/mailboxes/assign          assign an inbox to a family member (or clear it)
  DELETE /api/mailboxes/{id}            disconnect an inbox
"""

import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.limits import LimitedModel
from ..models.database import get_db, User, Mailbox, FamilyMember
from ..core.auth import get_current_user, get_accessible_member_ids, assert_can_edit
from ..core.settings_store import load_settings
from ..core import mailboxes as mbx
from ..core import oauth_engine as oe

router = APIRouter(prefix="/api/mailboxes", tags=["mailboxes"])

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
OAUTH_PROVIDERS = {"gmail": "Gmail or Google Workspace",
                   "outlook": "Outlook or Microsoft 365",
                   "yahoo": "Yahoo Mail"}

PLUS_LABELS = {
    "verified": "Gives every opt-out its own address",
    "checking": "Checking whether this inbox accepts +addresses…",
    "unsupported": "Uses the same address for every opt-out",
    "unknown": "Not checked yet",
}


class MailboxOut(BaseModel):
    id: int
    label: Optional[str] = None
    address: str
    provider_key: str
    transport: str
    status: str
    status_detail: Optional[str] = None
    plus_status: str
    plus_label: str
    example_address: Optional[str] = None
    member_ids: List[int] = []


class MemberInbox(BaseModel):
    member_id: int
    full_name: str
    mailbox_id: Optional[int] = None       # explicit assignment
    using_mailbox_id: Optional[int] = None # what opt-outs will actually use
    using_address: Optional[str] = None
    how: str                                # assigned | own | parent | none


def _out(mb: Mailbox, db: Session) -> MailboxOut:
    members = db.query(FamilyMember).filter(FamilyMember.mailbox_id == mb.id).all()
    return MailboxOut(
        id=mb.id, label=mb.label, address=mbx.base_address(mb.address),
        provider_key=mb.provider_key, transport=mb.transport,
        status=mb.status, status_detail=mb.status_detail,
        plus_status=mb.plus_status, plus_label=PLUS_LABELS.get(mb.plus_status, mb.plus_status),
        example_address=mbx.tagged(mb.address, "oo7f3k2a9") if mb.plus_status == "verified" else None,
        member_ids=[m.id for m in members],
    )


def _own(db: Session, user: User, mailbox_id: int) -> Mailbox:
    mb = db.query(Mailbox).filter(Mailbox.id == mailbox_id, Mailbox.status != "removed").first()
    if not mb or (mb.owner_user_id != user.id and not user.is_super_admin):
        raise HTTPException(404, "Inbox not found")
    return mb


def _how(db: Session, member: FamilyMember, used: Optional[Mailbox]) -> str:
    if used is None:
        return "none"
    if member.mailbox_id == used.id:
        return "assigned"
    return "own" if used.owner_user_id == member.user_id else "parent"


@router.get("/providers")
def providers(user: User = Depends(get_current_user)):
    """Inbox types this deployment can connect. OAuth ones need the admin to
    have registered the provider's app under Settings → Email."""
    s = load_settings()
    clients = s.get("oauth_clients") or {}
    out = [{"key": k, "label": v, "transport": "oauth", "available": k in clients}
           for k, v in OAUTH_PROVIDERS.items()]
    out.append({"key": "smtp", "label": "Other email (with an app password)",
                "transport": "app_password", "available": True})
    return {"providers": out}


@router.get("")
def list_mailboxes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    mine = db.query(Mailbox).filter(Mailbox.owner_user_id == user.id,
                                    Mailbox.status != "removed").order_by(Mailbox.id).all()
    members = db.query(FamilyMember).filter(
        FamilyMember.id.in_(get_accessible_member_ids(db, user))).order_by(FamilyMember.created_at).all()
    rows = []
    for m in members:
        used = mbx.resolve_mailbox(db, m)
        rows.append(MemberInbox(
            member_id=m.id, full_name=m.full_name, mailbox_id=m.mailbox_id,
            using_mailbox_id=used.id if used else None,
            using_address=mbx.base_address(used.address) if used else None,
            how=_how(db, m, used),
        ))
    return {"mailboxes": [_out(mb, db) for mb in mine], "members": rows}


@router.get("/me")
def my_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    member = db.query(FamilyMember).filter(FamilyMember.user_id == user.id).first()
    if not member:
        return {"needs_inbox": False}
    used = mbx.resolve_mailbox(db, member)
    return {"needs_inbox": used is None, "full_name": member.full_name}


class MailboxIn(LimitedModel):
    address: str
    provider_key: str                      # gmail | outlook | yahoo | smtp
    label: Optional[str] = None
    # App-password inboxes:
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    imap_host: Optional[str] = None
    imap_port: Optional[int] = 993
    username: Optional[str] = None
    password: Optional[str] = None
    assign_member_id: Optional[int] = None


def _begin_oauth(mb: Mailbox) -> str:
    from .email_oauth import _provider_flow, _client, _PENDING
    s = load_settings()
    flow = _provider_flow(mb.provider_key)
    try:
        client = _client(s, mb.provider_key)
    except HTTPException:
        raise HTTPException(400, f"{OAUTH_PROVIDERS.get(mb.provider_key, mb.provider_key)} sign-in "
                                 "hasn't been set up on this system yet. Ask your administrator to "
                                 "add it under Settings → Email, or connect with an app password.")
    url, pending = oe.begin_authorization(flow, client, mb.account_ref)
    _PENDING[pending.state] = pending
    return url


@router.post("", status_code=201)
def add_mailbox(body: MailboxIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    address = (body.address or "").strip()
    if not _EMAIL_RE.match(address):
        raise HTTPException(400, "That doesn't look like an email address.")
    address = mbx.base_address(address)
    if body.provider_key not in list(OAUTH_PROVIDERS) + ["smtp"]:
        raise HTTPException(400, "Choose Gmail, Outlook, Yahoo, or another provider.")

    existing = db.query(Mailbox).filter(Mailbox.address_hash == mbx.address_hash(address)).first()
    if existing and existing.status != "removed":
        if existing.owner_user_id != user.id:
            raise HTTPException(409, "This inbox is already connected to another account.")
        raise HTTPException(409, "You've already connected this inbox.")

    transport = "app_password" if body.provider_key == "smtp" else "oauth"
    if transport == "app_password":
        missing = [n for n, v in (("outgoing mail server", body.smtp_host),
                                  ("incoming mail server", body.imap_host),
                                  ("app password", body.password)) if not v]
        if missing:
            raise HTTPException(400, "Please fill in the " + ", ".join(missing) + ".")

    if existing:
        # A previously removed inbox being connected again: reuse its record so
        # replies to addresses it handed out earlier still trace back to it.
        mb = existing
        mb.owner_user_id = user.id
        mb.label = (body.label or "").strip() or None
        mb.provider_key = body.provider_key
        mb.transport = transport
        mb.status = "pending"
        mb.status_detail = None
        mb.plus_status = mbx.initial_plus_status(address, body.provider_key)
        mb.plus_test_tag = None
    else:
        import secrets
        mb = Mailbox(
            owner_user_id=user.id, label=(body.label or "").strip() or None,
            address=address, address_hash=mbx.address_hash(address),
            provider_key=body.provider_key, transport=transport,
            account_ref=f"pending-{secrets.token_hex(8)}", status="pending",
            plus_status=mbx.initial_plus_status(address, body.provider_key),
        )
    if transport == "app_password":
        mb.smtp_host = body.smtp_host.strip()
        mb.smtp_port = body.smtp_port or 587
        mb.imap_host = body.imap_host.strip()
        mb.imap_port = body.imap_port or 993
        mb.username = (body.username or address).strip()
        mb.password_enc = oe._encrypt(body.password)
        mb.status = "connected"
    if mb.id is None:
        db.add(mb)
        db.flush()
    mb.account_ref = f"mbx-{mb.id}"

    if body.assign_member_id:
        member = assert_can_edit(db, user, body.assign_member_id)
        member.mailbox_id = mb.id
    db.commit()

    out = {"mailbox": _out(mb, db).model_dump()}
    if transport == "oauth":
        out["authorize_url"] = _begin_oauth(mb)
    elif mb.plus_status == "unknown":
        out["plus_check"] = mbx.start_plus_check(db, load_settings(), mb)
    return out


@router.post("/{mailbox_id}/reconnect")
def reconnect(mailbox_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    mb = _own(db, user, mailbox_id)
    if mb.transport != "oauth":
        raise HTTPException(400, "This inbox uses an app password; remove it and add it again to change it.")
    return {"authorize_url": _begin_oauth(mb)}


@router.post("/{mailbox_id}/check-plus")
def check_plus(mailbox_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    mb = _own(db, user, mailbox_id)
    if mb.status != "connected":
        raise HTTPException(400, "Finish connecting this inbox first.")
    return mbx.start_plus_check(db, load_settings(), mb)


class AssignIn(LimitedModel):
    member_id: int
    mailbox_id: Optional[int] = None    # None clears the assignment


@router.post("/assign")
def assign(body: AssignIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    member = assert_can_edit(db, user, body.member_id)
    if body.mailbox_id is not None:
        mb = _own(db, user, body.mailbox_id)
        member.mailbox_id = mb.id
    else:
        member.mailbox_id = None
    db.commit()
    used = mbx.resolve_mailbox(db, member)
    return MemberInbox(member_id=member.id, full_name=member.full_name, mailbox_id=member.mailbox_id,
                       using_mailbox_id=used.id if used else None,
                       using_address=mbx.base_address(used.address) if used else None,
                       how=_how(db, member, used))


@router.delete("/{mailbox_id}", status_code=204)
def remove(mailbox_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Disconnect: forget credentials and tokens, unassign members. The row is
    kept (marked removed) so replies to addresses already given out can still
    be traced in the history."""
    mb = _own(db, user, mailbox_id)
    for m in db.query(FamilyMember).filter(FamilyMember.mailbox_id == mb.id).all():
        m.mailbox_id = None
    mb.status = "removed"
    mb.password_enc = None
    mb.username = None
    s = load_settings()
    creds = s.get("email_credentials") or {}
    if mb.account_ref in creds:
        creds.pop(mb.account_ref, None)
        s["email_credentials"] = creds
        from .email_oauth import _save
        _save(s)
    db.commit()
