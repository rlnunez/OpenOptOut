"""
Failed sign-in throttling.

After MAX_FAILURES failed attempts on a key (e.g. "password:jane@example.org"
or "mfa:42") further attempts are refused with 429 until a lockout expires.
The lockout starts at BASE_LOCKOUT seconds and doubles with each failure past
the limit, up to MAX_LOCKOUT. Failures are forgotten after FORGET_AFTER quiet
seconds, and a successful sign-in clears them.

Keys are built from what the caller submitted, whether or not that account
exists, so a locked response never reveals which accounts are real. check()
runs before credentials are verified, so a locked key can't be used to keep
testing passwords.

State is in memory: the API runs as a single uvicorn process. With several
worker processes each keeps its own counts, which loosens the limits by the
number of workers. Memory is bounded by MAX_KEYS (least recently failed keys
are dropped first).
"""

import math
import threading
import time

from fastapi import HTTPException

MAX_FAILURES = 5                 # failures allowed before a key is locked
BASE_LOCKOUT = 30                # seconds; doubles per failure past the limit
MAX_LOCKOUT = 15 * 60
FORGET_AFTER = 15 * 60           # quiet seconds before failures are forgotten
MAX_KEYS = 50_000

_state: dict = {}                # key -> [failures, locked_until, last_failure]; LRU order
_lock = threading.Lock()


def _now() -> float:
    return time.time()


def account_key(kind: str, identifier) -> str:
    return f"{kind}:{str(identifier or '').strip().lower()}"


def _stale(entry, now: float) -> bool:
    failures, locked_until, last = entry
    return now - last > FORGET_AFTER and now >= locked_until


def _prune(now: float):
    """Drop forgotten keys, and the least recently failed beyond MAX_KEYS.
    Entries are kept in last-failure order, so stop at the first live one."""
    while _state:
        key, entry = next(iter(_state.items()))
        if not _stale(entry, now) and len(_state) < MAX_KEYS:
            break
        del _state[key]


def _wait_text(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = math.ceil(seconds / 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def check(*keys: str):
    """Raise 429 if any of the keys is locked."""
    now = _now()
    with _lock:
        wait = max((_state[k][1] - now for k in keys if k in _state), default=0)
    if wait > 0:
        seconds = math.ceil(wait)
        raise HTTPException(
            429, f"Too many failed sign-in attempts. Try again in {_wait_text(seconds)}.",
            headers={"Retry-After": str(seconds)})


def failure(*keys: str):
    """Record a failed attempt against each key."""
    now = _now()
    with _lock:
        _prune(now)
        for k in keys:
            entry = _state.pop(k, None)           # re-inserted below: keeps LRU order
            if entry is None or _stale(entry, now):
                entry = [0, 0.0, now]
            failures = entry[0] + 1
            locked_until = entry[1]
            if failures >= MAX_FAILURES:
                over = min(failures - MAX_FAILURES, 10)
                locked_until = now + min(BASE_LOCKOUT * 2 ** over, MAX_LOCKOUT)
            _state[k] = [failures, locked_until, now]


def success(*keys: str):
    """Clear the failures recorded against each key."""
    with _lock:
        for k in keys:
            _state.pop(k, None)
