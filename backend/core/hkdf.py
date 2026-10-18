"""
RFC 5869 HMAC-based Extract-and-Expand Key Derivation Function (HKDF).

Pure Python standard-library implementation using hmac and hashlib.sha256.
Guarantees cryptographic key separation across independent subsystems
(settings encryption, OAuth tokens, MFA tickets, envelope HMAC/encryption)
derived from the primary master SECRET_KEY.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Union


def hkdf_extract(salt: Union[bytes, str], ikm: Union[bytes, str]) -> bytes:
    """
    HKDF-Extract(salt, IKM) -> PRK (Pseudorandom Key).
    If salt is empty or omitted, a string of HashLen zeros is used (RFC 5869 Section 2.2).
    """
    salt_bytes = salt.encode("utf-8") if isinstance(salt, str) else salt
    ikm_bytes = ikm.encode("utf-8") if isinstance(ikm, str) else ikm

    if not salt_bytes:
        salt_bytes = bytes([0] * 32)  # SHA-256 block / hash len is 32 bytes

    return hmac.new(salt_bytes, ikm_bytes, hashlib.sha256).digest()


def hkdf_expand(prk: Union[bytes, str], info: Union[bytes, str], length: int = 32) -> bytes:
    """
    HKDF-Expand(PRK, info, L) -> OKM (Output Keying Material).
    L is the number of output bytes (max 255 * HashLen for SHA-256 = 8160 bytes).
    """
    prk_bytes = prk.encode("utf-8") if isinstance(prk, str) else prk
    info_bytes = info.encode("utf-8") if isinstance(info, str) else info

    if length > 255 * 32:
        raise ValueError("Cannot expand beyond 255 * HashLen bytes")

    okm = b""
    t = b""
    counter = 1

    while len(okm) < length:
        t = hmac.new(prk_bytes, t + info_bytes + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1

    return okm[:length]


def hkdf_derive(
    ikm: Union[bytes, str],
    info: Union[bytes, str],
    salt: Union[bytes, str] = b"",
    length: int = 32,
) -> bytes:
    """
    Convenience wrapper executing HKDF-Extract then HKDF-Expand.
    Derives cryptographically isolated subkeys for specific subsystems.
    """
    prk = hkdf_extract(salt, ikm)
    return hkdf_expand(prk, info, length)
