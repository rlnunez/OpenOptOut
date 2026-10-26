"""Standardized UTC date and time utilities.

Centralizes timezone-aware and naive UTC datetime handling across the backend,
eliminating deprecated datetime.utcnow() calls and inconsistent ISO-8601 formats.
"""

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_naive() -> datetime:
    """Return current naive UTC datetime (tzinfo=None).

    Use this for database DateTime columns and legacy interfaces that expect
    naive UTC timestamps, avoiding Python 3.12+ datetime.utcnow() deprecation warnings.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_iso(dt: Optional[datetime] = None) -> str:
    """Return an ISO 8601 formatted UTC timestamp string ending with 'Z'.

    If dt is None, uses current UTC time.
    """
    if dt is None:
        dt = utc_now()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    iso = dt.isoformat()
    if iso.endswith("+00:00"):
        return iso[:-6] + "Z"
    if not iso.endswith("Z"):
        return iso + "Z"
    return iso


def parse_utc_iso(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp string into a timezone-aware UTC datetime."""
    cleaned = ts.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def epoch_seconds(dt: Optional[datetime] = None) -> int:
    """Return integer seconds since the UNIX epoch for dt (or now)."""
    if dt is None:
        dt = utc_now()
    return int(dt.timestamp())
