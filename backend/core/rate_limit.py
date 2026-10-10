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
memory and per process (the Docker image runs one uvicorn process; the native
service runs two workers, which doubles the effective limit), capped at
MAX_KEYS entries.
"""

import ipaddress
import math
import os
import threading
import time
from typing import Optional

from fastapi import HTTPException, Request

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
    if hops and chain:
        addr = chain[-hops] if len(chain) >= hops else chain[0]
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
