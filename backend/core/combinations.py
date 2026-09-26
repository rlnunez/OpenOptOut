"""
Identity combination matrix generator.

Vault limits are configured by the super admin via Settings → Vault limits.
Defaults: 4 names, 10 addresses, 5 phones, 5 emails.

Two-pass strategy:
  Pass 1 (discovery): name × address  →  find which brokers have listings
  Pass 2 (opt-out):   name × address × phone × email  →  exhaust all removal paths
"""

from dataclasses import dataclass
from typing import Optional
import itertools

from .settings_store import load_settings

# ── Default limits (used when settings file not yet created) ──────────────────

DEFAULT_LIMITS = {
    "name":    4,
    "address": 10,
    "phone":   5,
    "email":   5,
}


def get_vault_limits() -> dict:
    """Load current limits from settings, falling back to defaults."""
    try:
        s = load_settings()
        v = s.get("vault_limits", {})
        return {
            "name":    int(v.get("max_names",     DEFAULT_LIMITS["name"])),
            "address": int(v.get("max_addresses", DEFAULT_LIMITS["address"])),
            "phone":   int(v.get("max_phones",    DEFAULT_LIMITS["phone"])),
            "email":   int(v.get("max_emails",    DEFAULT_LIMITS["email"])),
        }
    except Exception:
        return DEFAULT_LIMITS.copy()


# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class IdentityCombo:
    """One combination of identity fields used for a single search or opt-out."""
    name:    str
    address: Optional[str] = None
    city:    Optional[str] = None
    state:   Optional[str] = None
    zip:     Optional[str] = None
    phone:   Optional[str] = None
    email:   Optional[str] = None

    def label(self) -> str:
        parts = [self.name]
        if self.address: parts.append(self.address[:40])
        if self.phone:   parts.append(self.phone)
        if self.email:   parts.append(self.email)
        return " | ".join(parts)

    def as_dict(self) -> dict:
        return {k: v for k, v in {
            "name": self.name, "address": self.address,
            "city": self.city, "state": self.state,
            "zip": self.zip, "phone": self.phone,
            "email": self.email,
        }.items() if v}


def _parse_address(raw: str) -> dict:
    import re
    parts  = [p.strip() for p in raw.split(",")]
    result = {"address": raw, "city": "", "state": "", "zip": ""}
    if len(parts) >= 3:
        result["address"] = parts[0]
        result["city"]    = parts[1]
        last = parts[-1].strip()
        m = re.match(r'([A-Za-z]{2,})\s*(\d{5}(?:-\d{4})?)?', last)
        if m:
            result["state"] = m.group(1).strip()
            result["zip"]   = (m.group(2) or "").strip()
    elif len(parts) == 2:
        result["city"] = parts[1]
        m = re.search(r',\s*([A-Z]{2})\b', raw)
        if m: result["state"] = m.group(1)
    else:
        m = __import__("re").search(r'\b([A-Z]{2})\s+\d{5}', raw)
        if m: result["state"] = m.group(1)
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_values(member, kind: str, limit: int) -> list[str]:
    """Primaries first, then others, up to limit."""
    primaries = [i.value for i in member.identities if i.kind == kind and i.is_primary]
    others    = [i.value for i in member.identities if i.kind == kind and not i.is_primary]
    return (primaries + others)[:limit]


def _deduplicate(combos: list) -> list:
    seen, unique = set(), []
    for c in combos:
        key = (c.name, c.address, c.phone, c.email)
        if key not in seen:
            seen.add(key); unique.append(c)
    return unique


# ── Matrix builders ───────────────────────────────────────────────────────────

def build_discovery_combos(member) -> list[IdentityCombo]:
    """Pass 1: name × address only."""
    limits    = get_vault_limits()
    names     = _get_values(member, "name",    limits["name"])
    addresses = _get_values(member, "address", limits["address"])
    combos = []
    for name, raw in itertools.product(names, addresses):
        p = _parse_address(raw)
        combos.append(IdentityCombo(
            name=name, address=p["address"],
            city=p["city"], state=p["state"], zip=p["zip"],
        ))
    # Name-only combos catch brokers that don't index by address
    for name in names:
        combos.append(IdentityCombo(name=name))
    return _deduplicate(combos)


def build_optout_combos(member) -> list[IdentityCombo]:
    """Pass 2: full name × address × phone × email matrix."""
    limits    = get_vault_limits()
    names     = _get_values(member, "name",    limits["name"])
    addresses = _get_values(member, "address", limits["address"])
    phones    = _get_values(member, "phone",   limits["phone"])
    emails    = _get_values(member, "email",   limits["email"])

    phones_ext = phones + [None] if phones else [None]
    emails_ext = emails + [None] if emails else [None]

    combos = []
    for name, raw, phone, email in itertools.product(
        names, addresses, phones_ext, emails_ext
    ):
        p = _parse_address(raw)
        combos.append(IdentityCombo(
            name=name, address=p["address"],
            city=p["city"], state=p["state"], zip=p["zip"],
            phone=phone, email=email,
        ))
    return _deduplicate(combos)


def build_email_optout_combos(member) -> list[IdentityCombo]:
    """For email-method brokers: name × address × phone."""
    limits    = get_vault_limits()
    names     = _get_values(member, "name",    limits["name"])
    addresses = _get_values(member, "address", limits["address"])
    phones    = _get_values(member, "phone",   limits["phone"])
    combos = []
    for name, raw in itertools.product(names, addresses):
        p = _parse_address(raw)
        combos.append(IdentityCombo(
            name=name, address=p["address"],
            city=p["city"], state=p["state"], zip=p["zip"],
            phone=phones[0] if phones else None,
        ))
    return _deduplicate(combos)


# ── Stats for the UI ──────────────────────────────────────────────────────────
# (combo_stats is defined further below — the version with property-record
# summary — which is the authoritative one used by the API.)


# ── Property broker matrix builders ──────────────────────────────────────────

def build_property_discovery_combos(member) -> list[IdentityCombo]:
    """
    Property broker Pass 1: formal_name × deed_addresses only.
    Uses the exact legal name as recorded on county documents.
    Falls back to primary name if no formal name set.
    """
    formal = member.formal_name or _get_values(member, "name", 1)[0] if _get_values(member, "name", 1) else member.full_name

    deed_addresses = [
        i.value for i in member.identities
        if i.kind == "address" and i.is_deed
    ]
    # If no deed addresses flagged, fall back to all addresses
    if not deed_addresses:
        limits = get_vault_limits()
        deed_addresses = _get_values(member, "address", limits["address"])

    combos = []
    for addr in deed_addresses:
        p = _parse_address(addr)
        combos.append(IdentityCombo(
            name=formal,
            address=p["address"], city=p["city"],
            state=p["state"], zip=p["zip"],
        ))
    # Name-only combo too
    combos.append(IdentityCombo(name=formal))
    return _deduplicate(combos)


def build_property_optout_combos(member) -> list[IdentityCombo]:
    """
    Property broker Pass 2: formal_name × (deed + mortgage) addresses.
    Covers both ownership records and lender filings.
    """
    formal = member.formal_name or (
        _get_values(member, "name", 1)[0] if _get_values(member, "name", 1) else member.full_name
    )

    property_addresses = [
        i.value for i in member.identities
        if i.kind == "address" and (i.is_deed or i.is_mortgage)
    ]
    if not property_addresses:
        limits = get_vault_limits()
        property_addresses = _get_values(member, "address", limits["address"])

    combos = []
    for addr in property_addresses:
        p = _parse_address(addr)
        combos.append(IdentityCombo(
            name=formal,
            address=p["address"], city=p["city"],
            state=p["state"], zip=p["zip"],
        ))
    # Also try with primary email — some property sites let you opt out by email
    emails = _get_values(member, "email", 1)
    if emails:
        for addr in property_addresses:
            p = _parse_address(addr)
            combos.append(IdentityCombo(
                name=formal, address=p["address"],
                city=p["city"], state=p["state"], zip=p["zip"],
                email=emails[0],
            ))

    return _deduplicate(combos)


def combo_stats(member) -> dict:
    """Return vault counts, matrix sizes, and property record summary."""
    limits    = get_vault_limits()
    names     = _get_values(member, "name",    limits["name"])
    addresses = _get_values(member, "address", limits["address"])
    phones    = _get_values(member, "phone",   limits["phone"])
    emails    = _get_values(member, "email",   limits["email"])

    deed_count     = sum(1 for i in member.identities if i.kind == "address" and i.is_deed)
    mortgage_count = sum(1 for i in member.identities if i.kind == "address" and i.is_mortgage)

    prop_disc  = build_property_discovery_combos(member)
    prop_optout = build_property_optout_combos(member)

    return {
        "names":            len(names),
        "addresses":        len(addresses),
        "phones":           len(phones),
        "emails":           len(emails),
        "discovery_combos": len(build_discovery_combos(member)),
        "optout_combos":    len(build_optout_combos(member)),
        "has_formal_name":  bool(member.formal_name),
        "formal_name":      member.formal_name,
        "deed_addresses":   deed_count,
        "mortgage_addresses": mortgage_count,
        "property_discovery_combos": len(prop_disc),
        "property_optout_combos":    len(prop_optout),
        "limits": {
            "name":    limits["name"],
            "address": limits["address"],
            "phone":   limits["phone"],
            "email":   limits["email"],
        },
    }
