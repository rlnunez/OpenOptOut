"""URL-safe base64 encoding and decoding utilities.

Centralizes RFC 4648 base64url padding handling, JWT segment decoding,
and string conversion to avoid duplicate b + '=' * (-len(b) % 4) logic across modules.
"""

import base64
import json
from typing import Any, Union


def b64url_pad(s: str) -> str:
    """Pad a base64url string with '=' to make its length a multiple of 4."""
    s = s.strip()
    return s + "=" * ((4 - len(s) % 4) % 4)


def b64url_decode(s: Union[str, bytes]) -> bytes:
    """Decode a base64url string or bytes with automatic '=' padding."""
    if isinstance(s, bytes):
        s = s.decode("ascii", "replace")
    padded = b64url_pad(s)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def b64url_encode(data: Union[str, bytes], strip_padding: bool = True) -> str:
    """Encode bytes or string into a base64url string, stripped of '=' by default."""
    if isinstance(data, str):
        raw = data.encode("utf-8")
    else:
        raw = data
    encoded = base64.urlsafe_b64encode(raw).decode("ascii")
    return encoded.rstrip("=") if strip_padding else encoded


def b64url_decode_str(s: Union[str, bytes], encoding: str = "utf-8", errors: str = "strict") -> str:
    """Decode a base64url string directly into a text string."""
    return b64url_decode(s).decode(encoding, errors)


def b64url_decode_json(s: Union[str, bytes]) -> Any:
    """Decode a base64url encoded JSON payload (e.g., JWT header or claim set)."""
    return json.loads(b64url_decode_str(s))
