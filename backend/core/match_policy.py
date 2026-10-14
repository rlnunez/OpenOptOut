"""
Unclear matches: what to do when a site shows a name but nothing to confirm it.

People-search sites often list several people with your name and hide the
city, age or phone that would tell them apart, which makes the right listing
hard to find and remove. Each possible match is sorted into:

  yours    something besides the name matches (phone, street, email, city or age)
  not_you  the page shows something that rules you out (a different age or birth year)
  unclear  the name matches and nothing else is shown

What happens to unclear ones is a setting:

  ask         show them to the person, with whatever the site did show, to pick (default)
  skip        leave them alone and mark them skipped
  remove_all  send a removal for every one (may include other people with the same name)

An admin sets the default (settings["matching"]["unclear_listings"]) and
whether people may choose their own (settings["matching"]["users_choose"]).
A person's own choice is kept on their account (users.optout_prefs).
"""
from __future__ import annotations

import json
from typing import Optional

CHOICES = ("ask", "skip", "remove_all")
DEFAULT = "ask"
LABELS = {
    "ask": "Ask me which ones are me",
    "skip": "Skip them",
    "remove_all": "Remove all of them",
}
MAX_REMOVE_ALL = 10      # never more than this many unclear listings per site and person


def classify(profile: dict, text: str) -> tuple:
    """(verdict, why) for one possible match: verdict is yours | unclear | not_you."""
    from .web_search import score
    from .age import ages_in, years_in
    strength, matched = score(profile, text or "")
    if strength in ("strong", "medium"):
        return "yours", matched
    if matched != "name":
        return "not_you", "the name doesn't match"
    ages, years = set(profile.get("ages") or ()), set(profile.get("birth_years") or ())
    shown_ages, shown_years = ages_in(text), years_in(text)
    if (ages and shown_ages and not ages & shown_ages) or (years and shown_years and not years & shown_years):
        return "not_you", "the age shown is different"
    return "unclear", "only the name matches; the site shows no city, age or phone"


# ── settings ──────────────────────────────────────────────────────────────────

def global_settings(cfg: dict) -> dict:
    m = (cfg or {}).get("matching") or {}
    choice = m.get("unclear_listings", DEFAULT)
    return {"unclear_listings": choice if choice in CHOICES else DEFAULT,
            "users_choose": bool(m.get("users_choose", True))}


def user_choice(user) -> Optional[str]:
    try:
        v = json.loads(getattr(user, "optout_prefs", None) or "{}").get("unclear_listings")
    except Exception:
        return None
    return v if v in CHOICES else None


def for_member(db, member, cfg: dict) -> str:
    """The choice that applies to this person: theirs (or a parent's), if allowed, else the default."""
    g = global_settings(cfg)
    if not g["users_choose"] or member is None:
        return g["unclear_listings"]
    own = user_choice(getattr(member, "user", None))
    if own:
        return own
    from ..models.database import ProfileAccess, User
    for grant in db.query(ProfileAccess).filter(ProfileAccess.managed_id == member.user_id).all():
        mgr = db.query(User).filter(User.id == grant.manager_id).first()
        c = user_choice(mgr)
        if c:
            return c
    return g["unclear_listings"]


def save_global(choice: str, users_choose: bool) -> dict:
    """Admin: set the default and whether people may choose their own."""
    from .settings_store import load_settings, save_settings
    if choice not in CHOICES:
        raise ValueError("Choose ask, skip or remove all.")
    cfg = load_settings()
    cfg["matching"] = {**(cfg.get("matching") or {}), "unclear_listings": choice, "users_choose": bool(users_choose)}
    save_settings(cfg)
    return global_settings(cfg)


def save_user(user, choice: Optional[str]) -> None:
    """A person's own choice; None goes back to the default."""
    if choice is not None and choice not in CHOICES:
        raise ValueError("Choose ask, skip or remove all.")
    try:
        prefs = json.loads(user.optout_prefs or "{}")
    except Exception:
        prefs = {}
    if choice is None:
        prefs.pop("unclear_listings", None)
    else:
        prefs["unclear_listings"] = choice
    user.optout_prefs = json.dumps(prefs) if prefs else None
