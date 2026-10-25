"""
W3C Trace Context Implementation (W3C Recommendation 23 November 2021).

Provides standardized distributed tracing headers (traceparent and tracestate)
across control plane API routes, message queues (Redis), worker daemons, and browser runners.
Enables end-to-end distributed audit correlation without proprietary SDKs or third-party tracking.
"""

from __future__ import annotations

import re
import secrets
from typing import Dict, Optional, Tuple

# W3C traceparent regex: 00-32hex-16hex-02hex
TRACEPARENT_REGEX = re.compile(
    r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)


def generate_traceparent(
    trace_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    sampled: bool = True,
) -> str:
    """
    Generate a compliant W3C traceparent header.
    Format: 00-{trace_id}-{parent_id}-{trace_flags}
    """
    if not trace_id:
        # 16 random bytes (32 hex characters)
        trace_id = secrets.token_hex(16)
        while trace_id == "0" * 32:
            trace_id = secrets.token_hex(16)

    if not parent_id:
        # 8 random bytes (16 hex characters)
        parent_id = secrets.token_hex(8)
        while parent_id == "0" * 16:
            parent_id = secrets.token_hex(8)

    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{parent_id}-{flags}"


def parse_traceparent(header: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Parse and validate a W3C traceparent header string.
    Returns a dict with version, trace_id, parent_id, flags if valid, else None.
    """
    if not header or not isinstance(header, str):
        return None
    header = header.strip()
    m = TRACEPARENT_REGEX.match(header)
    if not m:
        return None
    version, trace_id, parent_id, flags = m.groups()
    if version == "ff":
        return None
    # Trace ID and Parent ID cannot be all zeros
    if trace_id == "0" * 32 or parent_id == "0" * 16:
        return None
    return {
        "version": version,
        "trace_id": trace_id,
        "parent_id": parent_id,
        "flags": flags,
        "sampled": (int(flags, 16) & 1) == 1,
    }


def is_valid_traceparent(header: Optional[str]) -> bool:
    """Check whether a traceparent string conforms to W3C specification."""
    return parse_traceparent(header) is not None


def child_traceparent(parent_header: Optional[str], sampled: Optional[bool] = None) -> str:
    """
    Derives a child span traceparent preserving trace_id and generating a new span_id.
    If parent_header is invalid or missing, initializes a new trace context.
    """
    parsed = parse_traceparent(parent_header)
    if not parsed:
        return generate_traceparent(sampled=True if sampled is None else sampled)
    is_sampled = parsed["sampled"] if sampled is None else sampled
    return generate_traceparent(trace_id=parsed["trace_id"], sampled=is_sampled)
