"""
Limits guesses at an emailed 6-digit code. Each code's token gets
MAX_TRIES wrong guesses, and works once. Kept in memory: a restart only
forgets codes, which expire in minutes anyway.
"""
import hashlib
import threading
import time

MAX_TRIES = 5
_lock = threading.Lock()
_seen = {}   # token hash -> [wrong guesses, used, expires]


def _key(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def _prune(now: float):
    for k in [k for k, v in _seen.items() if v[2] < now]:
        _seen.pop(k, None)


def allowed(token: str, expires: float) -> bool:
    """False once the code was used or guessed wrong too often."""
    now = time.time()
    with _lock:
        _prune(now)
        v = _seen.setdefault(_key(token), [0, False, max(expires, now + 60)])
        return not v[1] and v[0] < MAX_TRIES


def wrong(token: str):
    with _lock:
        v = _seen.get(_key(token))
        if v:
            v[0] += 1


def used(token: str):
    with _lock:
        v = _seen.get(_key(token))
        if v:
            v[1] = True
