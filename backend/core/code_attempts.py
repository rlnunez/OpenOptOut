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


# A valid TOTP code is accepted by `mfa.verify_totp` for any of a few adjacent
# time-steps (clock-drift window), and the MFA *ticket* it's submitted with is
# single-use — but a captured code can still be replayed against a second,
# concurrently-issued ticket for the same user within that window. Track the
# RFC 6238 counter itself, per user, separately from the ticket tracking above.
_totp_seen = {}   # "user_id:counter" -> expires


def _totp_prune(now: float):
    for k in [k for k, exp in _totp_seen.items() if exp < now]:
        _totp_seen.pop(k, None)


def totp_replay_check(user_id: int, counter: int, interval: int = 30, window: int = 1) -> bool:
    """True if this exact TOTP code was already consumed for this user; marks
    it consumed either way. In-memory, like the rest of this file: a restart
    only forgets codes, which expire within the same short window anyway."""
    now = time.time()
    key = f"{user_id}:{counter}"
    with _lock:
        _totp_prune(now)
        if key in _totp_seen:
            return True
        _totp_seen[key] = now + interval * (window + 2)
        return False
