"""
Per-client-IP request limits.

client_ip(): the API sits behind proxies, and each one appends the address it
received the request from to X-Forwarded-For. The real client is therefore
TRUSTED_PROXY_HOPS entries from the right; anything further left was sent by
the client and can be forged.

  Docker, plain HTTP (nginx -> API)            1  (default)
  Docker, HTTPS (Caddy/Traefik -> nginx -> API) 2  (scripts/enable-https.* set it)
  Native install (nginx terminates TLS)        1
  Nothing in front (API reached directly)      0

IPv6 clients are grouped by /64, since one host can cycle through the
addresses in its /64.

limit(name, per_minute): a FastAPI dependency allowing each client IP
per_minute requests (token bucket, bursts up to per_minute) to the routes that
share `name`; over the limit it answers 429 with Retry-After. State is in
memory and per process (both Docker and native service run one uvicorn worker
by default to keep rate limits and SSO state consistent; multi-worker requires
an external store), capped at MAX_KEYS entries.
"""

import ipaddress
import math
import os
import threading
import time
from typing import Optional

try:
    from fastapi import HTTPException, Request
except ImportError:
    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int = 400, detail: str = "", headers: Optional[dict] = None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
            self.headers = headers or {}
    Request = object  # type: ignore

MAX_KEYS = 50_000

_buckets: dict = {}              # (name, ip) -> [tokens, last, idle_after]; LRU order
_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def _hops() -> int:
    try:
        return max(0, int(os.getenv("TRUSTED_PROXY_HOPS", "1")))
    except ValueError:
        return 1


def _normalize(addr: str) -> Optional[str]:
    try:
        ip = ipaddress.ip_address(addr.strip())
    except ValueError:
        return None
    if ip.version == 6:
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


def client_ip(request: Optional[Request]) -> Optional[str]:
    """The client's address as seen by the outermost trusted proxy, or None
    without a request (e.g. a direct call in tests)."""
    if request is None:
        return None
    client_obj = getattr(request, "client", None)
    peer = client_obj.host if client_obj else ""
    hops = _hops()
    chain = [p for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if hops > 0 and len(chain) >= hops:
        addr = chain[-hops]
        return _normalize(addr) or _normalize(peer) or peer
    return _normalize(peer) or peer


def _prune(now: float):
    while _buckets:
        key, entry = next(iter(_buckets.items()))
        if now < entry[2] and len(_buckets) < MAX_KEYS:
            break
        del _buckets[key]


def limit(name: str, per_minute: int):
    """FastAPI dependency: at most per_minute requests per client IP across the
    routes sharing `name`."""
    capacity = float(per_minute)
    rate = per_minute / 60.0            # tokens per second
    refill = capacity / rate            # seconds from empty to full

    def dependency(request: Request):
        ip = client_ip(request)
        if ip is None:
            return
        now = _now()
        with _lock:
            _prune(now)
            tokens, last, _ = _buckets.pop((name, ip), (capacity, now, 0))
            tokens = min(capacity, tokens + (now - last) * rate)
            allowed = tokens >= 1
            if allowed:
                tokens -= 1
            _buckets[(name, ip)] = [tokens, now, now + refill]
        if not allowed:
            wait = math.ceil((1 - tokens) / rate)
            raise HTTPException(429, f"Too many requests. Try again in {wait} seconds.",
                                headers={"Retry-After": str(wait)})

    dependency.rate_limit = (name, per_minute)     # lets tests audit which routes are limited
    return dependency


def limit_value(name: str, value: str, capacity: int, per_seconds: float = 60.0) -> None:
    """Rate-limit by an arbitrary value instead of client IP. Call this
    directly from inside a route body (not as a FastAPI dependency) to cap a
    sensitive action against one target — e.g. one email address, for a
    magic-link/sign-in-code request — across however many source IPs an
    attacker rotates through, in addition to the IP-keyed `limit()`
    dependency already on the route (that one protects the server from one
    IP; this one protects one account from the whole internet). Raises the
    same 429 + Retry-After as `limit()`. Shares the same bucket store, keyed
    so it never collides with an IP-keyed bucket of the same `name`."""
    capacity = float(capacity)
    rate = capacity / per_seconds
    refill = capacity / rate
    now = _now()
    bucket_key = (f"value:{name}", value)
    with _lock:
        _prune(now)
        tokens, last, _ = _buckets.pop(bucket_key, (capacity, now, 0))
        tokens = min(capacity, tokens + (now - last) * rate)
        allowed = tokens >= 1
        if allowed:
            tokens -= 1
        _buckets[bucket_key] = [tokens, now, now + refill]
    if not allowed:
        wait = math.ceil((1 - tokens) / rate)
        raise HTTPException(429, f"Too many requests. Try again in {wait} seconds.",
                            headers={"Retry-After": str(wait)})
