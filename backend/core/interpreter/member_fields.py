"""
Resolve a member (and optionally one identity combination) into the values a
broker spec's fields refer to (broker_spec.KNOWN_FIELDS).

Kept separate from the engine so the same values are used for local runs, the
worker fleet and plugin dry runs, and so it can be tested without a browser.
"""

from datetime import date

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico",
}
_BY_NAME = {v.lower(): k for k, v in US_STATES.items()}


def state_code(state: str) -> str:
    s = (state or "").strip()
    if s.upper() in US_STATES:
        return s.upper()
    return _BY_NAME.get(s.lower(), s)


def state_name(state: str) -> str:
    return US_STATES.get(state_code(state), state or "")


def phone_digits(phone: str) -> str:
    d = "".join(c for c in (phone or "") if c.isdigit())
    return d[1:] if len(d) == 11 and d.startswith("1") else d


def _split_name(name: str):
    parts = (name or "").split()
    return (parts[0] if parts else ""), (" ".join(parts[1:]) if len(parts) > 1 else "")


def resolve(member, combo=None, today=None) -> dict:
    """Values for every KNOWN_FIELDS name we can fill for this member."""
    from ..combinations import _get_values, _parse_address

    def first(kind):
        vals = _get_values(member, kind, 1)
        return vals[0] if vals else ""

    formal = getattr(member, "formal_name", "") or ""
    if combo is not None:
        name = combo.name or member.full_name or ""
        street, city, state, zip_ = combo.address or "", combo.city or "", combo.state or "", combo.zip or ""
        email, phone = combo.email or first("email"), combo.phone or first("phone")
    else:
        name = member.full_name or first("name")
        raw = first("address")
        p = _parse_address(raw) if raw else {"address": "", "city": "", "state": "", "zip": ""}
        street, city, state, zip_ = p.get("address") or raw, p.get("city", ""), p.get("state", ""), p.get("zip", "")
        email, phone = first("email"), first("phone")

    first_name, last_name = _split_name(name)
    age = getattr(member, "age", None)
    year = (today or date.today()).year
    out = {
        "full_name": name,
        "formal_name": formal or name,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "phone_digits": phone_digits(phone),
        "address": street,
        "street": street,
        "city": city,
        "state": state_code(state) if state else "",
        "state_name": state_name(state) if state else "",
        "zip": zip_,
        "age": str(age) if age else None,
        "birth_year": str(year - int(age)) if age else None,
    }
    # Missing values are None, so required steps fail at compile time with a
    # clear message instead of typing an empty string into a form.
    return {k: (v if v not in ("",) else None) for k, v in out.items()}
