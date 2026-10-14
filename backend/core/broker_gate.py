"""
One answer to "should this removal request run now?", shared by every place
that picks requests to send (scheduler batch, parent-company batch, distributed
queue).

  - Test brokers never run here.
  - Brokers an admin (or the health monitor) turned off don't run — except a
    broker imported from a state registry, for a person who actually found a
    listing about themselves on it. Registry brokers start off because sending
    every family's details to hundreds of companies does more harm than good;
    a real listing is the evidence that makes one worth contacting.
  - A broker known only from California's registry is skipped for a member
    whose California DROP request is more than 90 days old: registered brokers
    must act on DROP requests, so a separate request adds exposure, not removal.
"""


def request_allowed(req, db=None) -> bool:
    b = getattr(req, "broker", None)
    if b is None or getattr(b, "is_test", False):
        return False
    origin = getattr(b, "origin", None) or "curated"
    if not b.enabled:
        return origin == "registry" and bool(getattr(req, "listing_url", None))
    if origin == "registry" and not getattr(req, "listing_url", None) and db is not None:
        try:
            from .state_programs import drop_covers
            if drop_covers(db, req.member, b):
                return False
        except Exception:
            pass
    return True
