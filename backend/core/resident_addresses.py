"""
Residents-only sign-up: a community's list of addresses.

A management district, apartment complex, senior living community or other
housing community uploads its addresses. With the check turned on
(settings: registration.address_check), people can only create an account
at an address on the list.

Matching works on a cleaned-up form of each address, so "123 Main Street,
Apt 4" and "123 MAIN ST #4" are the same:
  - upper case, punctuation removed;
  - street types and directions shortened as the USPS does
    (STREET -> ST, NORTH -> N);
  - the unit is the part after APT / UNIT / # / STE / LOT / SPACE ...,
    without leading zeros or dashes;
  - the first five digits of the ZIP code.
City and state aren't part of the match (the ZIP is), because people write
unincorporated areas differently.

A row with no unit stands for the whole building: any unit there matches.
If the list has units for a building, the person must give one of them.

The list is stored encrypted (ResidentAddress.address); `key` and
`building_key` are hashes used only for lookup. Nothing here logs an
address.
"""
import csv
import hashlib
import io
import re
from datetime import datetime
from typing import Optional

STREET_TYPES = {
    "ALLEY": "ALY", "ALLY": "ALY", "AVENUE": "AVE", "AV": "AVE", "AVEN": "AVE", "AVNUE": "AVE",
    "BEND": "BND", "BOULEVARD": "BLVD", "BOUL": "BLVD", "BRANCH": "BR", "BRIDGE": "BRG",
    "BROOK": "BRK", "BYPASS": "BYP", "CANYON": "CYN", "CAUSEWAY": "CSWY", "CENTER": "CTR",
    "CENTRE": "CTR", "CIRCLE": "CIR", "CIRCL": "CIR", "CLIFF": "CLF", "CLUB": "CLB",
    "COMMON": "CMN", "CORNER": "COR", "COURSE": "CRSE", "COURT": "CT", "COVE": "CV",
    "CREEK": "CRK", "CRESCENT": "CRES", "CROSSING": "XING", "DALE": "DL", "DRIVE": "DR",
    "DRIV": "DR", "ESTATE": "EST", "ESTATES": "ESTS", "EXPRESSWAY": "EXPY", "EXTENSION": "EXT",
    "FIELD": "FLD", "FIELDS": "FLDS", "FOREST": "FRST", "FORK": "FRK", "FREEWAY": "FWY",
    "GARDEN": "GDN", "GARDENS": "GDNS", "GATEWAY": "GTWY", "GLEN": "GLN", "GREEN": "GRN",
    "GROVE": "GRV", "HARBOR": "HBR", "HAVEN": "HVN", "HEIGHTS": "HTS", "HIGHWAY": "HWY",
    "HIGHWY": "HWY", "HILL": "HL", "HILLS": "HLS", "HOLLOW": "HOLW", "ISLAND": "IS",
    "JUNCTION": "JCT", "KNOLL": "KNL", "LAKE": "LK", "LAKES": "LKS", "LANDING": "LNDG",
    "LANE": "LN", "MANOR": "MNR", "MEADOW": "MDW", "MEADOWS": "MDWS", "MILL": "ML",
    "MOUNT": "MT", "MOUNTAIN": "MTN", "ORCHARD": "ORCH", "PARKWAY": "PKWY", "PARKWY": "PKWY",
    "PKY": "PKWY", "PINES": "PNES", "PLACE": "PL", "PLAIN": "PLN", "PLAZA": "PLZ",
    "POINT": "PT", "PORT": "PRT", "PRAIRIE": "PR", "RANCH": "RNCH", "RIDGE": "RDG",
    "RIVER": "RIV", "ROAD": "RD", "ROUTE": "RTE", "SHORE": "SHR", "SHORES": "SHRS",
    "SPRING": "SPG", "SPRINGS": "SPGS", "SQUARE": "SQ", "STATION": "STA", "STREET": "ST",
    "STR": "ST", "STRT": "ST", "SUMMIT": "SMT", "TERRACE": "TER", "TRACE": "TRCE",
    "TRAIL": "TRL", "TURNPIKE": "TPKE", "VALLEY": "VLY", "VIEW": "VW", "VILLAGE": "VLG",
    "VILLAS": "VLS", "VISTA": "VIS",
}
DIRECTIONS = {
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW",
}
# Words that start the unit part of an address line.
UNIT_WORDS = {
    "APT", "APARTMENT", "UNIT", "STE", "SUITE", "LOT", "SPC", "SPACE", "TRLR", "TRAILER",
    "RM", "ROOM", "BLDG", "BUILDING",
}

MAX_ROWS = 500_000
MAX_BYTES = 30 * 1024 * 1024


class AddressError(ValueError):
    """An address that can't be used, with a plain reason."""


def _words(text: str) -> list:
    t = (text or "").upper().replace("#", " # ")
    t = re.sub(r"[.,;:'\"()]", " ", t)
    return [w for w in t.split() if w]


def _clean_unit(words: list) -> str:
    parts = []
    for w in words:
        if w in UNIT_WORDS or w == "#":
            continue
        w = w.replace("-", "")
        if w.isdigit():
            w = w.lstrip("0") or "0"
        parts.append(w)
    return " ".join(parts)


def split_street(line: str, unit: str = "") -> tuple:
    """'123 Main Street Apt 4' -> ('123 MAIN ST', '4'). A separate unit
    field wins over a unit written in the street line."""
    words = _words(line)
    cut = next((i for i, w in enumerate(words) if i > 0 and (w in UNIT_WORDS or w == "#")), None)
    street_words, unit_words = (words[:cut], words[cut:]) if cut is not None else (words, [])
    street = " ".join(STREET_TYPES.get(w, DIRECTIONS.get(w, w)) for w in street_words)
    u = _clean_unit(_words(unit)) if (unit or "").strip() else _clean_unit(unit_words)
    return street, u


def clean_zip(z: str) -> str:
    m = re.search(r"\d{5}", z or "")
    return m.group(0) if m else ""


def clean(street: str, unit: str = "", city: str = "", state: str = "", zip_code: str = "") -> dict:
    """The cleaned-up parts of an address. Raises AddressError."""
    s, u = split_street(street, unit)
    z = clean_zip(zip_code)
    if not s or not re.match(r"^\d", s):
        raise AddressError("Start the street address with the house or building number.")
    if len(s.split()) < 2:
        raise AddressError("Add the street name after the number.")
    if not z:
        raise AddressError("Add the 5-digit ZIP code.")
    return {"street": s, "unit": u, "city": " ".join(_words(city)), "state": " ".join(_words(state)), "zip": z}


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def keys(c: dict) -> tuple:
    """(key, building_key) for a cleaned address."""
    building = f"{c['street']}|{c['zip']}"
    return _h(f"{building}|{c['unit']}"), _h(building)


def one_line(c: dict) -> str:
    """'123 MAIN ST #4, HOUSTON, TX 77060' (the form brokers' sites expect)."""
    street = c["street"] + (f" #{c['unit']}" if c["unit"] else "")
    place = " ".join(x for x in (c.get("state", ""), c["zip"]) if x)
    return ", ".join(x for x in (street, c.get("city", ""), place) if x)


def parse_one_line(line: str) -> dict:
    """'123 Main St Apt 4, Houston, TX 77060' -> clean() parts. Also takes
    '123 Main St, #4, Houston, TX, 77060' and '123 Main St 77060'."""
    parts = [p.strip() for p in (line or "").split(",") if p.strip()]
    if not parts:
        raise AddressError("The address is empty.")
    z = state = city = unit = ""
    m = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", parts[-1])
    if m and (len(parts) > 1 or m.start() > 0):
        z = m.group(1)
        rest = parts[-1][:m.start()].strip()
        if len(parts) > 1:
            parts.pop()
            if rest:
                state = rest
                w = rest.split()
                if len(w) > 1 and len(w[-1]) == 2 and w[-1].isalpha():
                    city, state = " ".join(w[:-1]), w[-1]   # "Houston TX 77060"
            elif len(parts) > 1 and re.fullmatch(r"[A-Za-z]{2}", parts[-1]):
                state = parts.pop()
        else:
            parts[-1] = rest            # "123 Main St 77060"
    if len(parts) > 1:
        first = _words(parts[1])[:1]
        if first and (first[0] in UNIT_WORDS or first[0] == "#"):
            unit = parts.pop(1)
    if len(parts) > 1 and not city:
        city = parts[-1]
    return clean(parts[0], unit, city, state, z)


# ── The list ──────────────────────────────────────────────────────────────────

_COLS = {
    "line": ("address", "full_address", "street_address", "address1", "address_1", "line1",
             "address_line_1", "site_address", "situs_address", "property_address", "street"),
    "number": ("house_number", "street_number", "number", "addr_num", "address_number", "house_no", "site_number"),
    "predir": ("prefix", "street_prefix", "predir", "pre_dir", "prefix_direction", "dir"),
    "name": ("street_name", "name", "st_name"),
    "suffix": ("suffix", "street_suffix", "street_type", "type", "sfx"),
    "postdir": ("postdir", "post_dir", "suffix_direction"),
    "unit": ("unit", "apt", "apartment", "suite", "address2", "address_2", "line2", "address_line_2", "unit_number"),
    "city": ("city", "town", "municipality", "site_city"),
    "state": ("state", "st", "state_code"),
    "zip": ("zip", "zipcode", "zip_code", "postal", "postal_code", "zip5", "site_zip"),
    "branch": ("branch", "branch_code"),
}


def _columns(header: list) -> dict:
    norm = [re.sub(r"[^a-z0-9]+", "_", (h or "").strip().lower()).strip("_") for h in header]
    found = {}
    for field, names in _COLS.items():
        for n in names:
            if n in norm and norm.index(n) not in found.values():
                found[field] = norm.index(n)
                break
    # "street" next to a house number column is the street NAME
    if "number" in found and "line" in found and "name" not in found and norm[found["line"]] == "street":
        found["name"] = found.pop("line")
    return found


def read_csv(data: bytes) -> tuple:
    """Rows of cleaned addresses from a CSV. Returns (rows, problems) where
    problems are {"line": n, "reason": ...} (line numbers only, never the
    address). Accepts a one-line address column, or separate number /
    street name / unit / city / state / ZIP columns, or a file with one
    address per line and no header."""
    if len(data) > MAX_BYTES:
        raise AddressError("The file is too big. Split it into files under 30 MB.")
    text = data.decode("utf-8-sig", errors="replace")
    reader = list(csv.reader(io.StringIO(text)))
    if not reader:
        raise AddressError("The file is empty.")
    cols = _columns(reader[0])
    has_header = bool(cols) and ("line" in cols or ("number" in cols and "name" in cols))
    if not has_header and cols:
        raise AddressError("Couldn't find the address columns. Name them address, unit, city, state "
                           "and zip (or house_number and street_name), or download the example file.")
    body = reader[1:] if has_header else reader
    if len(body) > MAX_ROWS:
        raise AddressError(f"The file has more than {MAX_ROWS:,} addresses. Split it into smaller files.")
    rows, problems = [], []
    for i, r in enumerate(body, start=2 if has_header else 1):
        if not any((c or "").strip() for c in r):
            continue
        get = lambda f: (r[cols[f]] if f in cols and cols[f] < len(r) else "").strip()
        try:
            if not has_header:
                c = parse_one_line(",".join(r))
                branch = ""
            else:
                if "line" in cols:
                    street = get("line")
                else:
                    street = " ".join(x for x in (get("number"), get("predir"), get("name"),
                                                  get("suffix"), get("postdir")) if x)
                if get("zip") or get("city") or get("state"):
                    c = clean(street, get("unit"), get("city"), get("state"), get("zip"))
                else:
                    c = parse_one_line(street + (f", {get('unit')}" if get("unit") else ""))
                branch = get("branch")
            rows.append((c, branch[:30] or None))
        except AddressError as e:
            if len(problems) < 50:
                problems.append({"line": i, "reason": str(e)})
            else:
                problems.append(None)
    return rows, [p for p in problems if p]


def import_rows(db, rows: list, replace: bool) -> dict:
    """Save cleaned rows. Returns counts."""
    from ..models.database import ResidentAddress
    if replace:
        db.query(ResidentAddress).delete()
        db.flush()
        existing = set()
    else:
        existing = {k for (k,) in db.query(ResidentAddress.key).all()}
    added = dupes = 0
    for c, branch in rows:
        key, bkey = keys(c)
        if key in existing:
            dupes += 1
            continue
        existing.add(key)
        db.add(ResidentAddress(key=key, building_key=bkey, has_unit=bool(c["unit"]),
                               address=one_line(c), branch_code=branch))
        added += 1
        if added % 5000 == 0:
            db.flush()
    db.commit()
    return {"added": added, "already_listed": dupes}


def match(db, c: dict):
    """(status, row) for a cleaned address. status: ok | unit_needed |
    unit_not_found | not_found."""
    from ..models.database import ResidentAddress
    key, bkey = keys(c)
    row = db.query(ResidentAddress).filter(ResidentAddress.key == key).first()
    if row:
        return "ok", row
    same_building = db.query(ResidentAddress).filter(ResidentAddress.building_key == bkey)
    whole = same_building.filter(ResidentAddress.has_unit == False).first()  # noqa: E712
    if whole and c["unit"]:
        return "ok", whole
    if same_building.filter(ResidentAddress.has_unit == True).first():  # noqa: E712
        return ("unit_not_found" if c["unit"] else "unit_needed"), None
    return "not_found", None


def accounts_at(db, person_key: str) -> int:
    from ..models.database import User
    return db.query(User).filter(User.resident_key == person_key).count()


def summary(db) -> dict:
    from sqlalchemy import func
    from ..models.database import ResidentAddress, User
    total = db.query(func.count(ResidentAddress.id)).scalar() or 0
    units = db.query(func.count(ResidentAddress.id)).filter(ResidentAddress.has_unit == True).scalar() or 0  # noqa: E712
    buildings = db.query(func.count(func.distinct(ResidentAddress.building_key))).scalar() or 0
    last = db.query(func.max(ResidentAddress.created_at)).scalar()
    branches = dict(db.query(ResidentAddress.branch_code, func.count(ResidentAddress.id))
                    .filter(ResidentAddress.branch_code.isnot(None))
                    .group_by(ResidentAddress.branch_code).all())
    accounts = db.query(func.count(User.id)).filter(User.resident_key.isnot(None)).scalar() or 0
    return {"addresses": total, "with_units": units, "buildings": buildings,
            "updated_at": last.isoformat() + "Z" if isinstance(last, datetime) else None,
            "accounts": accounts, "branches": branches}


def config() -> dict:
    from .settings_store import load_settings
    reg = load_settings().get("registration", {}) or {}
    return {
        "signup_page": bool(reg.get("signup_page") or reg.get("address_check")),
        "address_check": bool(reg.get("address_check")),
        "address_limit": max(0, int(reg.get("address_limit") or 0)),
        "help": str(reg.get("signup_help") or "")[:300],
    }


EXAMPLE_CSV = (
    "address,unit,city,state,zip,branch\n"
    "100 Example Street,,Exampleville,TX,77000,\n"
    "200 Sample Avenue,Apt 1,Exampleville,TX,77000,\n"
    "200 Sample Avenue,Apt 2,Exampleville,TX,77000,\n"
)


def find_branch(db, code: Optional[str]):
    if not code:
        return None
    from ..models.database import Branch
    return db.query(Branch).filter(Branch.code == code).first()
