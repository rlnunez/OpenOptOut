"""
Regional formats: how dates, times and numbers are shown.

An admin sets these once for the whole system (Settings -> Regional formats).
The default is the United States: "Oct 11, 2026", "3:05 PM", "1,234.5",
weeks starting on Sunday.

The screens combine the region with each person's language, so a Spanish
speaker in the US sees "11 oct 2026" written the US way for numbers, and the
browser's own date tables (Intl) do the work. Server-written text (notice
emails, the PDF report) is English, so there only the order of day, month and
year follows the region.

Letters to brokers and credit bureaus are NOT formatted this way: they follow
the law and the place they're sent to.
"""

from datetime import date, datetime
from typing import Optional
import re

DEFAULTS = {
    "region": "US",        # ISO 3166 country code
    "hour_cycle": "auto",  # auto | h12 | h23
    "week_start": "auto",  # auto | sun | mon | sat
    "time_zone": "",       # "" = each person's own device; else an IANA name
    "digits": "latn",      # latn = 0-9 everywhere; native = the language's own digits
}

# The regions offered in the picker; names come from the browser in the
# person's own language (Intl.DisplayNames). US first: it's the main market.
REGIONS = ["US", "CA", "MX", "PR", "GB", "IE", "AU", "NZ", "IN", "PH", "ZA",
           "DE", "AT", "CH", "FR", "BE", "NL", "ES", "IT", "PT", "BR", "AR", "CO",
           "SE", "NO", "DK", "FI", "PL", "RU", "UA", "TR", "IL", "SA", "AE", "EG",
           "CN", "TW", "HK", "JP", "KR", "VN", "SG"]

HOUR_CYCLES = ("auto", "h12", "h23")
WEEK_STARTS = ("auto", "sun", "mon", "sat")
DIGITS = ("latn", "native")

# Day/month/year order for server-written English text.
_MDY = {"US", "PR", "PH", "CA", "FM", "MH", "PW", "AS", "GU", "MP", "VI", "UM"}
_YMD = {"CN", "TW", "HK", "JP", "KR", "HU", "LT", "MN", "IR", "KP", "SE"}


def _valid_tz(name: str) -> bool:
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
        return True
    except Exception:
        return False


def clean(data: Optional[dict]) -> dict:
    """Validated settings, defaults filled in. Raises ValueError with a
    message a person can act on."""
    out = dict(DEFAULTS)
    for k, v in (data or {}).items():
        if k in out and v is not None:
            out[k] = v.strip() if isinstance(v, str) else v
    out["region"] = str(out["region"]).upper()
    if not re.fullmatch(r"[A-Z]{2}", out["region"]):
        raise ValueError("Choose a country or region from the list.")
    if out["hour_cycle"] not in HOUR_CYCLES:
        raise ValueError("Choose 12-hour or 24-hour time.")
    if out["week_start"] not in WEEK_STARTS:
        raise ValueError("Choose the day weeks start on.")
    if out["digits"] not in DIGITS:
        raise ValueError("Choose which digits to show.")
    if out["time_zone"] and not _valid_tz(out["time_zone"]):
        raise ValueError("That time zone isn't recognised. Use a name like America/Chicago.")
    return out


_cache = {"at": 0.0, "value": None}


def get(settings: Optional[dict] = None) -> dict:
    if settings is None:
        import time
        if _cache["value"] is not None and time.monotonic() - _cache["at"] < 5:
            return _cache["value"]
        from .settings_store import load_settings
        try:
            _cache["value"] = get(load_settings())
        except Exception:
            _cache["value"] = dict(DEFAULTS)
        _cache["at"] = time.monotonic()
        return _cache["value"]
    try:
        return clean(settings.get("regional"))
    except ValueError:
        return dict(DEFAULTS)


def format_date(v, settings: Optional[dict] = None, long: bool = False) -> str:
    """A date in English for server-written text: "Oct 11, 2026" (US),
    "11 Oct 2026" (most places) or "2026-10-11" (year-first places)."""
    if not v:
        return "—"
    if isinstance(v, str):
        v = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if isinstance(v, datetime):
        v = v.date()
    if not isinstance(v, date):
        return str(v)
    region = get(settings)["region"]
    month = f"{v:%B}" if long else f"{v:%b}"
    if region in _MDY:
        return f"{month} {v.day}, {v.year}"
    if region in _YMD:
        return v.isoformat()
    return f"{v.day} {month} {v.year}"
