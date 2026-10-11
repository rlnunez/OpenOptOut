"""
Government deletion services — currently California's DROP (Delete Request
and Opt-out Platform).

Since August 1, 2026, a California resident can ask every broker registered in
California to delete their data with one request at the state's DROP site.
Brokers must check DROP and have 90 days to delete. The person has to confirm
their own residency (by entering their details or signing in with
Login.gov), so OpenOptOut can't submit it for them. Instead:

  - every member with a California address gets ONE checklist item with plain
    instructions and the link,
  - when they mark it done, the date is recorded on that request,
  - 90 days later, brokers OpenOptOut knows ONLY from California's registry are
    skipped for that member (broker_gate.request_allowed): a separate request
    there would add exposure, not removal. People-search sites where they're
    actually listed still get direct opt-outs, since DROP's reach over those
    listings isn't something we can confirm.
"""

import logging
import uuid
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

DROP_NAME = "California DROP (state deletion request)"
DROP_URL = "https://privacy.ca.gov/drop/"
DROP_WAIT = timedelta(days=90)

DROP_INSTRUCTIONS = (
    "California lets residents ask every registered data broker to delete their information "
    "with one free request. Go to {url}, confirm that you live in California (by entering your "
    "details or signing in with Login.gov), and give the email address or phone number brokers "
    "should use. When you've submitted it, mark this item done. Brokers have 90 days to act."
)


def is_california_member(member) -> bool:
    from .combinations import _get_values, _parse_address
    for raw in _get_values(member, "address", 10):
        st = (_parse_address(raw).get("state") or "").strip().upper()
        if st in ("CA", "CALIFORNIA"):
            return True
    return False


def _drop_broker(db, create: bool = True):
    from ..models.database import Broker, OptOutMethod, Difficulty, BrokerStatus
    b = db.query(Broker).filter(Broker.origin == "state_program", Broker.name == DROP_NAME).first()
    if b is None and create:
        b = Broker(name=DROP_NAME, opt_out_url=DROP_URL, method=OptOutMethod.manual,
                   difficulty=Difficulty.easy, status=BrokerStatus.compliant, enabled=True,
                   priority=5, origin="state_program",
                   notes="California's free one-stop deletion request. Residents submit it themselves.")
        db.add(b)
        db.flush()
    return b


def ensure_drop_items(db) -> int:
    """Give every California member a DROP checklist item, once. Returns how many were added."""
    from ..models.database import FamilyMember, RemovalRequest, RequestStatus
    added = 0
    drop = None
    for m in db.query(FamilyMember).all():
        if not is_california_member(m):
            continue
        drop = drop or _drop_broker(db)
        exists = db.query(RemovalRequest).filter(RemovalRequest.member_id == m.id,
                                                 RemovalRequest.broker_id == drop.id).first()
        if exists:
            continue
        db.add(RemovalRequest(member_id=m.id, broker_id=drop.id, request_key=str(uuid.uuid4()),
                              status=RequestStatus.needs_manual,
                              notes=DROP_INSTRUCTIONS.format(url=DROP_URL)))
        added += 1
    if added:
        db.commit()
        log.info("Added California DROP checklist items for %d member(s)", added)
    return added


def drop_done_at(db, member):
    from ..models.database import RemovalRequest, RequestStatus
    drop = _drop_broker(db, create=False)
    if drop is None or member is None:
        return None
    r = db.query(RemovalRequest).filter(RemovalRequest.member_id == member.id,
                                        RemovalRequest.broker_id == drop.id).first()
    if r is None or r.status not in (RequestStatus.sent, RequestStatus.confirmed):
        return None
    return r.confirmed_at or r.sent_at or r.updated_at


def drop_covers(db, member, broker, now=None) -> bool:
    """True when this broker is known only from California's registry and the
    member's DROP request is older than the brokers' 90-day window."""
    states = {s for s in (getattr(broker, "registry_states", "") or "").split(",") if s}
    if (getattr(broker, "origin", None) or "curated") != "registry" or states != {"CA"}:
        return False
    done = drop_done_at(db, member)
    return bool(done and (now or datetime.utcnow()) - done >= DROP_WAIT)
