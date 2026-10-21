"""
Age and date of birth.

Many broker forms and search pages ask for an age, a birth year, an age range
or a full date of birth, and people-search pages show an age next to each
name. Knowing it lets OpenOptOut fill those forms and tell a person's listing
from a namesake's.

A date of birth is optional and encrypted at rest (FamilyMember.dob). When
only an age is known, everything here works from that, approximately.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

_FORMATS = (
    re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"),          # 1983-04-09
    re.compile(r"^(\d{4})(\d{2})(\d{2})$"),                # 19830409 (SIP2)
    re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$"),          # 04/09/1983 (US) or 25/04/1983 (intl)
    re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"),        # 09.04.1983 (European dot order)
    re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$"),          # 09-04-1983
)


def parse_dob(value) -> Optional[date]:
    """A date from YYYY-MM-DD, YYYYMMDD, MM/DD/YYYY, DD/MM/YYYY or DD.MM.YYYY; None if invalid."""
    if isinstance(value, date):
        d = value
    else:
        s = str(value or "").strip()
        d = None
        for i, rx in enumerate(_FORMATS):
            m = rx.match(s)
            if not m:
                continue
            try:
                if i in (0, 1):
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:
                    n1, n2, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    if i == 3:  # dot notation is always DD.MM.YYYY
                        d = date(yr, n2, n1)
                    elif n1 > 12 and n2 <= 12:  # unambiguously DD/MM/YYYY (e.g. 25/04/1983)
                        d = date(yr, n2, n1)
                    elif n2 > 12 and n1 <= 12:  # unambiguously MM/DD/YYYY (e.g. 04/25/1983)
                        d = date(yr, n1, n2)
                    else:
                        # Ambiguous (both <= 12): check regional setting if available
                        use_dmy = False
                        try:
                            from . import settings_store
                            reg = settings_store.load_settings().get("regional", {}).get("region")
                            if reg and reg.upper() != "US":
                                use_dmy = True
                        except Exception:
                            pass
                        d = date(yr, n2, n1) if use_dmy else date(yr, n1, n2)
            except ValueError:
                return None
            break
        if d is None:
            return None
    today = date.today()
    if d > today or today.year - d.year > 120:
        return None
    return d


def age_on(dob: date, today: Optional[date] = None) -> int:
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def member_dob(member) -> Optional[date]:
    return parse_dob(getattr(member, "dob", None)) if getattr(member, "dob", None) else None


def current_age(member, today: Optional[date] = None) -> Optional[int]:
    """Exact from the date of birth when saved, otherwise the age typed in."""
    d = member_dob(member)
    if d:
        return age_on(d, today)
    a = getattr(member, "age", None)
    return int(a) if a not in (None, "") else None


def age_range(age: Optional[int], width: int = 10) -> str:
    """'40-49' style range some forms ask for."""
    if age is None:
        return ""
    lo = (age // width) * width
    return f"{lo}-{lo + width - 1}"


def plausible_ages(member, today: Optional[date] = None) -> set:
    """
    Ages a listing could show for this person. Sites update ages at different
    times, so allow one year either side (two below when only an age is known,
    since a typed age goes stale).
    """
    a = current_age(member, today)
    if a is None:
        return set()
    spread = (-1, 0, 1) if member_dob(member) else (-1, 0, 1, 2)
    return {a + s for s in spread if a + s >= 0}


def birth_years(member, today: Optional[date] = None) -> set:
    d = member_dob(member)
    if d:
        return {d.year}
    a = current_age(member, today)
    if a is None:
        return set()
    y = (today or date.today()).year
    return {y - a, y - a - 1}


_AGE_RX = re.compile(r"\b(?:age|aged)\s*:?\s*(\d{1,3})\b|\b(\d{1,3})\s*(?:years old|yrs old|y/o)\b", re.I)
_BORN_RX = re.compile(r"\b(?:born|birth\s*year|b\.)\s*:?\s*(?:in\s+)?(?:[A-Za-z]{3,9}\.?\s+(?:\d{1,2},?\s+)?)?(19\d\d|20\d\d)\b", re.I)


def ages_in(text: str) -> set:
    return {int(a or b) for a, b in _AGE_RX.findall(text or "")}


def years_in(text: str) -> set:
    return {int(y) for y in _BORN_RX.findall(text or "")}


def age_matches(profile: dict, text: str) -> bool:
    """Does the text show this person's age or birth year?"""
    ages, years = set(profile.get("ages") or ()), set(profile.get("birth_years") or ())
    return bool((ages and ages & ages_in(text)) or (years and years & years_in(text)))
