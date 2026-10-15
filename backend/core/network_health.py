"""
Network Health & Outbound Internet Connectivity Monitor.

Provides lightweight, non-blocking reachability probing and error classification
to gracefully halt opt-out workers and schedulers when internet connectivity is lost,
preventing false job failures, wasted retry budgets, and broken broker health stats.
"""

from __future__ import annotations

import logging
import os
import socket
import time
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

# Default fast, reliable anycast DNS targets on port 53 (TCP handshake is lightweight and avoids full DNS query overhead)
DEFAULT_CANARY_TARGETS: List[Tuple[str, int]] = [
    ("1.1.1.1", 53),  # Cloudflare
    ("8.8.8.8", 53),  # Google
    ("9.9.9.9", 53),  # Quad9
]

# Short TTL caching (5 seconds) prevents hammering probe endpoints in rapid loops
_CACHE_TTL_SECONDS = 5.0
_last_probe_time: float = 0.0
_cached_status: bool = True

# Testing hook to simulate internet drops deterministically
_mock_internet_status: Optional[bool] = None


def set_mock_internet_status(status: Optional[bool]) -> None:
    """Set or clear a simulated network reachability state for testing."""
    global _mock_internet_status
    _mock_internet_status = status


def is_mock_active() -> bool:
    """Return True if a mock internet status is currently active."""
    return _mock_internet_status is not None


def _get_canary_targets() -> List[Tuple[str, int]]:
    """Parse configured canary targets from environment or fallback to defaults."""
    env_canaries = os.getenv("NETWORK_CANARY_TARGETS")
    if not env_canaries:
        return DEFAULT_CANARY_TARGETS

    targets: List[Tuple[str, int]] = []
    for item in env_canaries.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            host, port_str = item.split(":", 1)
            try:
                targets.append((host.strip(), int(port_str.strip())))
            except ValueError:
                continue
        else:
            targets.append((item, 53))

    return targets or DEFAULT_CANARY_TARGETS


def is_internet_available(timeout: float = 2.0, force_probe: bool = False) -> bool:
    """
    Check if outbound internet connectivity is currently available.
    Uses cached result if within TTL unless force_probe is True.
    """
    global _last_probe_time, _cached_status

    if _mock_internet_status is not None:
        return _mock_internet_status

    now = time.time()
    if not force_probe and (now - _last_probe_time < _CACHE_TTL_SECONDS):
        return _cached_status

    targets = _get_canary_targets()
    reachable = False

    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                reachable = True
                break
        except (OSError, socket.timeout):
            continue
        except Exception as e:
            log.debug("Canary probe to %s:%d failed: %s", host, port, e)
            continue

    _cached_status = reachable
    _last_probe_time = now

    if not reachable:
        log.warning("Outbound internet connectivity probe failed across all canaries: %s", targets)

    return reachable


def is_network_error(exc: Optional[Exception]) -> bool:
    """
    Inspect an exception to determine if it was caused by network-level
    connectivity loss, DNS failure, or connection reset/timeout.
    """
    if exc is None:
        return False

    # Check for direct socket / network exceptions
    if isinstance(exc, (socket.gaierror, ConnectionRefusedError, ConnectionResetError, socket.timeout)):
        return True

    msg = str(exc).lower()

    # Common Playwright / Chromium / Firefox / OS network failure strings
    network_signatures = (
        "err_internet_disconnected",
        "err_name_not_resolved",
        "err_connection_refused",
        "err_connection_reset",
        "err_connection_timed_out",
        "err_connection_closed",
        "err_address_unreachable",
        "err_network_changed",
        "net::err_",
        "ns_error_net_on_disconnected",
        "ns_error_unknown_host",
        "ns_error_net_timeout",
        "ns_error_connection_refused",
        "getaddrinfo failed",
        "network is unreachable",
        "no route to host",
        "temporary failure in name resolution",
    )

    return any(sig in msg for sig in network_signatures)
