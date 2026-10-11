"""
Per-member inboxes and per-opt-out contact addresses.

Opt-outs are sent from, and broker replies arrive at, an inbox belonging to the
family — never the system inbox, which is only for notifications. Each opt-out
gets its own address where the inbox allows it:

    jane@gmail.com  ->  jane+oo7f3k2a9@gmail.com

The tag is random (it reveals nothing about the broker) and is recorded in a
ContactAddress row, so:

  - a broker's reply is matched to its exact request by the To: address,
  - brokers that allow one opt-out per email address get a fresh address
    for every listing,
  - mail that later arrives at a tag from anyone other than that broker shows
    the address was passed on.

Which inbox a member uses (resolve_mailbox):
  1. the inbox assigned to the member,
  2. otherwise an inbox the member's own user connected,
  3. otherwise an inbox owned by a parent who manages the member — but only
     one that supports +addresses, so replies for different family members
     stay separable.
No usable inbox means no opt-out: the request goes on the checklist with a
plain-language instruction instead.
"""

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

log = logging.getLogger(__name__)

TAG_PREFIX = "oo"
_TAG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # no look-alikes (0/o, 1/l/i)
TAG_RE = re.compile(r"\+(" + TAG_PREFIX + r"[a-z0-9]{6,16})@", re.IGNORECASE)

# Domains whose mail service is known to deliver user+anything@domain to
# user@domain. Google Workspace and Microsoft 365 custom domains are handled by
# provider_key below; everything else is checked with a test email.
PLUS_DOMAINS = {
    "gmail.com", "googlemail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com",
    "fastmail.com", "fastmail.fm",
    "proton.me", "protonmail.com", "pm.me",
}
# Known not to: Yahoo uses separate "disposable addresses" instead.
NO_PLUS_DOMAINS = {"yahoo.com", "ymail.com", "rocketmail.com", "aol.com"}
# Providers whose hosted service supports +addresses on custom domains too.
# Microsoft 365 admins can turn it off, so those still get a test email.
PLUS_PROVIDERS_TRUSTED = {"gmail"}

PLUS_TEST_WAIT = timedelta(hours=24)


def address_hash(address: str) -> str:
    return hashlib.sha256((address or "").strip().lower().encode()).hexdigest()


def split_address(address: str) -> Tuple[str, str]:
    local, _, domain = (address or "").strip().rpartition("@")
    return local, domain.lower()


def base_address(address: str) -> str:
    """Strip any existing +tag: jane+old@x.com -> jane@x.com."""
    local, domain = split_address(address)
    return f"{local.split('+', 1)[0]}@{domain}" if local else address


def plus_support(address: str, provider_key: str = "") -> str:
    """
    What we know before testing: 'supported', 'unsupported', or 'unknown'
    (unknown means: send a test email to find out).
    """
    _, domain = split_address(address)
    if domain in NO_PLUS_DOMAINS or provider_key == "yahoo":
        return "unsupported"
    if domain in PLUS_DOMAINS:
        return "supported"
    if provider_key in PLUS_PROVIDERS_TRUSTED:
        return "supported"          # Google Workspace on a custom domain
    return "unknown"                # incl. Microsoft 365 custom domains (admins can disable it)


def initial_plus_status(address: str, provider_key: str = "") -> str:
    known = plus_support(address, provider_key)
    return {"supported": "verified", "unsupported": "unsupported"}.get(known, "unknown")


def new_tag() -> str:
    return TAG_PREFIX + "".join(secrets.choice(_TAG_ALPHABET) for _ in range(8))


def tagged(address: str, tag: str) -> str:
    local, domain = split_address(base_address(address))
    return f"{local}+{tag}@{domain}"


def tags_in(text: str) -> set:
    """Every OpenOptOut tag appearing in an address list or header."""
    return {t.lower() for t in TAG_RE.findall(text or "")}


def uses_plus(mailbox) -> bool:
    return getattr(mailbox, "plus_status", "") == "verified"


# ── Which inbox a member uses ─────────────────────────────────────────────────

def _usable(mb) -> bool:
    return mb is not None and mb.status == "connected"


def resolve_mailbox(db, member):
    """
    The connected inbox opt-outs for this member go through, or None.
    See the module docstring for the order.
    """
    from ..models.database import Mailbox, ProfileAccess

    if member.mailbox_id:
        mb = db.query(Mailbox).filter(Mailbox.id == member.mailbox_id).first()
        if _usable(mb):
            return mb

    own = db.query(Mailbox).filter(Mailbox.owner_user_id == member.user_id,
                                   Mailbox.status == "connected") \
            .order_by(Mailbox.id).all()
    if own:
        return own[0]

    manager_ids = [g.manager_id for g in db.query(ProfileAccess).filter(
        ProfileAccess.managed_id == member.user_id).all()]
    if manager_ids:
        for mb in db.query(Mailbox).filter(Mailbox.owner_user_id.in_(manager_ids),
                                           Mailbox.status == "connected") \
                    .order_by(Mailbox.id).all():
            if uses_plus(mb):
                return mb
    return None


def missing_mailbox_instruction(member) -> str:
    return (f"{member.full_name} needs an email inbox before opt-outs can be sent. "
            f"Go to Email inboxes and connect one for them, or connect a Gmail or other "
            f"inbox that supports +addresses to a parent's account.")


# ── Contact addresses ─────────────────────────────────────────────────────────

def issue_contact_address(db, mailbox, member, broker=None, parent=None,
                          request_key: str = "", combo_label: str = "",
                          one_optout_per_email: bool = False):
    """
    The address to give a broker for one opt-out. Returns (ContactAddress, None)
    or (None, reason) when the opt-out has to wait for a person.

    With a +address inbox every call returns a new, unique address. Without
    one, the plain address is used — unless the broker allows only one
    opt-out per email address and that address was already used there.
    """
    from ..models.database import ContactAddress

    base = base_address(mailbox.address)
    if uses_plus(mailbox):
        for _ in range(5):
            tag = new_tag()
            if not db.query(ContactAddress).filter(ContactAddress.tag == tag).first():
                break
        addr = tagged(base, tag)
    else:
        tag = None
        addr = base
        if one_optout_per_email and broker is not None:
            used = db.query(ContactAddress).filter(
                ContactAddress.broker_id == broker.id,
                ContactAddress.address_hash == address_hash(addr),
            ).first()
            if used and not (used.member_id == member.id and used.combo_label == combo_label):
                name = getattr(broker, "name", "This broker")
                return None, (f"{name} accepts only one opt-out per email address, and {addr} "
                              f"has already been used there. Assign {member.full_name} an inbox "
                              f"that supports +addresses (like Gmail), or a different inbox.")

    ca = ContactAddress(
        tag=tag, address=addr, address_hash=address_hash(addr),
        mailbox_id=mailbox.id, member_id=member.id,
        broker_id=getattr(broker, "id", None), parent_company_id=getattr(parent, "id", None),
        request_key=request_key or None, combo_label=combo_label or None,
    )
    db.add(ca)
    db.flush()
    return ca, None


# ── Sending through a member's inbox ──────────────────────────────────────────

def mailbox_send_cfg(settings: dict, mailbox) -> dict:
    """
    A settings dict whose "email" section points at this inbox, for
    core.email_send.send_email. Everything else (tokens, OAuth clients) is the
    real settings, so OAuth refresh finds this inbox's tokens.
    """
    cfg = dict(settings)
    if mailbox.transport == "oauth":
        cfg["email"] = {"provider": mailbox.provider_key, "from_address": base_address(mailbox.address)}
    else:
        cfg["email"] = {
            "provider": "smtp",
            "smtp_host": mailbox.smtp_host, "smtp_port": mailbox.smtp_port or 587,
            "smtp_username": mailbox.username or base_address(mailbox.address),
            "smtp_user": mailbox.username or base_address(mailbox.address),
            "smtp_password_enc": mailbox.password_enc,
            "smtp_tls": "starttls",
            "from_address": base_address(mailbox.address),
        }
    return cfg


def send_from_mailbox(settings: dict, mailbox, to: list, subject: str, body: str,
                      reply_to: str = "", cc: Optional[list] = None) -> dict:
    from .email_send import send_email
    cfg = mailbox_send_cfg(settings, mailbox)
    return send_email(cfg, to=list(to), cc=list(cc or []), subject=subject, body=body,
                      account_ref=mailbox.account_ref,
                      from_address=base_address(mailbox.address), reply_to=reply_to)


# ── +address check ────────────────────────────────────────────────────────────

def start_plus_check(db, settings: dict, mailbox) -> dict:
    """
    Send one email from the inbox to a tagged copy of itself. When the inbox
    poll sees it arrive, the inbox is marked as supporting +addresses.
    """
    known = plus_support(mailbox.address, mailbox.provider_key)
    if known == "unsupported":
        mailbox.plus_status = "unsupported"
        db.commit()
        return {"ok": True, "plus_status": "unsupported", "sent": False}
    tag = new_tag()
    to = tagged(mailbox.address, tag)
    res = send_from_mailbox(
        settings, mailbox, [to],
        subject=f"OpenOptOut inbox check {tag}",
        body=("OpenOptOut sent this message to check that your inbox accepts addresses "
              "with a + in them. You can delete it.\n"),
    )
    if not res.get("ok"):
        mailbox.status_detail = f"Test email could not be sent: {res.get('error') or 'unknown error'}"
        db.commit()
        return {"ok": False, "plus_status": mailbox.plus_status, "error": mailbox.status_detail}
    mailbox.plus_status = "checking"
    mailbox.plus_test_tag = tag
    mailbox.plus_test_sent_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "plus_status": "checking", "sent": True}


def expire_plus_checks(db, now: Optional[datetime] = None) -> int:
    """Checks that never arrived mean the inbox drops +addresses."""
    from ..models.database import Mailbox
    now = now or datetime.utcnow()
    n = 0
    for mb in db.query(Mailbox).filter(Mailbox.plus_status == "checking").all():
        if mb.plus_test_sent_at and now - mb.plus_test_sent_at > PLUS_TEST_WAIT:
            mb.plus_status = "unsupported"
            mb.status_detail = ("The test email to a +address never arrived, so this inbox "
                                "will use its plain address for opt-outs.")
            n += 1
    if n:
        db.commit()
    return n


# ── Inbound mail ──────────────────────────────────────────────────────────────

def _domain_of(header: str) -> str:
    m = re.search(r"@([A-Za-z0-9.\-]+)", header or "")
    return (m.group(1).lower().rstrip(".>") if m else "")


def _broker_domains(broker) -> set:
    out = set()
    from urllib.parse import urlparse
    for v in (getattr(broker, "opt_out_url", "") or "", getattr(broker, "name", "") or ""):
        host = urlparse(v if "://" in v else f"https://{v}").hostname or ""
        host = host.lower()
        if host.startswith("www."):
            host = host[4:]
        if "." in host:
            out.add(host)
    return out


def _sender_matches(sender_domain: str, domains: set) -> bool:
    return any(sender_domain == d or sender_domain.endswith("." + d) for d in domains)


def match_inbound(db, mailbox, to_header: str, from_header: str) -> dict:
    """
    Look at one inbound message's To/Delivered-To and From. Returns
    {"plus_check": bool, "request_keys": [...], "unexpected": [(tag, domain)]}.
    Records the hit on each ContactAddress. Never reads or stores the body.
    """
    from ..models.database import ContactAddress, Broker, ParentCompany
    out = {"plus_check": False, "request_keys": [], "unexpected": []}
    tags = tags_in(to_header)
    if not tags:
        return out
    test_tag = (getattr(mailbox, "plus_test_tag", None) or "").lower()
    if test_tag and test_tag in tags:
        mailbox.plus_status = "verified"
        mailbox.plus_test_tag = None
        mailbox.status_detail = None
        out["plus_check"] = True
        tags.discard(test_tag)

    sender = _domain_of(from_header)
    now = datetime.utcnow()
    for tag in tags:
        ca = db.query(ContactAddress).filter(ContactAddress.tag == tag).first()
        if not ca:
            continue
        ca.inbound_count = (ca.inbound_count or 0) + 1
        ca.last_inbound_at = now
        domains = set()
        if ca.broker_id:
            b = db.query(Broker).filter(Broker.id == ca.broker_id).first()
            if b:
                domains |= _broker_domains(b)
        if ca.parent_company_id:
            p = db.query(ParentCompany).filter(ParentCompany.id == ca.parent_company_id).first()
            if p:
                domains |= _broker_domains(type("P", (), {"opt_out_url": p.website or "", "name": ""})())
                for child in (p.children or []):
                    domains |= _broker_domains(child)
        if sender and domains and not _sender_matches(sender, domains):
            seen = set(filter(None, (ca.unexpected_senders or "").split(",")))
            if sender not in seen:
                seen.add(sender)
                ca.unexpected_senders = ",".join(sorted(seen))
            out["unexpected"].append((tag, sender))
            log.warning("Mail to an opt-out address came from %s, not the broker it was given to "
                        "(contact address id=%s)", sender, ca.id)
            continue
        if ca.request_key:
            out["request_keys"].append(ca.request_key)
    db.commit()
    return out


def purge_for_user(db, user_id: int) -> None:
    """
    When an account is deleted: forget every inbox it connected (and their
    tokens) and every opt-out address issued from them or for its member.
    Members it managed fall back to their own or another parent's inbox.
    """
    from ..models.database import Mailbox, ContactAddress, FamilyMember
    from .settings_store import load_settings, SETTINGS_FILE
    import json

    boxes = db.query(Mailbox).filter(Mailbox.owner_user_id == user_id).all()
    box_ids = [b.id for b in boxes]
    member = db.query(FamilyMember).filter(FamilyMember.user_id == user_id).first()
    q = db.query(ContactAddress)
    conds = []
    if box_ids:
        conds.append(ContactAddress.mailbox_id.in_(box_ids))
    if member:
        conds.append(ContactAddress.member_id == member.id)
    if conds:
        from sqlalchemy import or_
        q.filter(or_(*conds)).delete(synchronize_session=False)
    if box_ids:
        for m in db.query(FamilyMember).filter(FamilyMember.mailbox_id.in_(box_ids)).all():
            m.mailbox_id = None
        try:
            s = load_settings()
            creds = s.get("email_credentials") or {}
            changed = False
            for b in boxes:
                if creds.pop(b.account_ref, None) is not None:
                    changed = True
            if changed:
                s["email_credentials"] = creds
                with open(SETTINGS_FILE, "w") as f:
                    json.dump(s, f, indent=2)
        except Exception as e:
            log.warning("Could not remove inbox tokens for deleted user: %s", e)
        for b in boxes:
            db.delete(b)
    db.flush()
