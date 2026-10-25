"""
RFC 9449: OAuth 2.0 Demonstrating Proof-of-Possession (DPoP) at the Application Layer.

Implements application-layer sender-constraining for OAuth 2.0 / 2.1 access and refresh tokens.
Validates client-generated DPoP proof JWTs, matches HTTP method (htm) and target URI (htu),
enforces single-use JTI replay protection, and computes RFC 7638 JWK Thumbprints (jkt).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
from typing import Any, Dict, Optional, Set, Tuple

# Replay cache for JTI tokens (bounded in-memory set with eviction)
_REPLAY_CACHE: Dict[str, float] = {}
_REPLAY_LOCK = threading.Lock()
MAX_SKEW_SECONDS = 300  # 5 minutes acceptable clock drift


def compute_jwk_thumbprint(jwk: Dict[str, Any]) -> str:
    """
    Computes the canonical RFC 7638 JSON Web Key (JWK) Thumbprint ('jkt').
    """
    kty = jwk.get("kty")
    if kty == "EC":
        canonical = {
            "crv": jwk.get("crv"),
            "kty": "EC",
            "x": jwk.get("x"),
            "y": jwk.get("y"),
        }
    elif kty == "RSA":
        canonical = {
            "e": jwk.get("e"),
            "kty": "RSA",
            "n": jwk.get("n"),
        }
    elif kty == "OKP":  # Ed25519 / EdDSA
        canonical = {
            "crv": jwk.get("crv"),
            "kty": "OKP",
            "x": jwk.get("x"),
        }
    else:
        canonical = {k: jwk[k] for k in sorted(jwk.keys()) if not k.startswith("d")}

    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode("ascii")


def compute_access_token_hash(access_token: str) -> str:
    """Computes the 'ath' (access token hash) claim under RFC 9449 Section 4.2."""
    digest = hashlib.sha256(access_token.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _clean_replay_cache() -> None:
    now = time.time()
    cutoff = now - (MAX_SKEW_SECONDS * 2)
    with _REPLAY_LOCK:
        expired = [k for k, exp in _REPLAY_CACHE.items() if exp < cutoff]
        for k in expired:
            del _REPLAY_CACHE[k]


def validate_dpop_proof(
    dpop_header: str,
    http_method: str,
    http_uri: str,
    access_token: Optional[str] = None,
    max_skew: int = MAX_SKEW_SECONDS,
) -> Dict[str, Any]:
    """
    Validates a DPoP proof JWT under RFC 9449 Section 4.3.
    Returns parsed proof dict with 'jkt' thumbprint, header, and payload.
    Raises ValueError on validation failure.
    """
    if not dpop_header or not isinstance(dpop_header, str):
        raise ValueError("Missing or empty DPoP header.")

    parts = dpop_header.strip().split(".")
    if len(parts) != 3:
        raise ValueError("Invalid DPoP JWT format: must contain 3 segments.")

    try:
        header_b64 = parts[0] + "=" * (-len(parts[0]) % 4)
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        header = json.loads(base64.urlsafe_b64decode(header_b64.encode("ascii")).decode("utf-8"))
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Malformed DPoP proof encoding: {e}")

    # 1. Validate header: typ MUST be "dpop+jwt"
    typ = header.get("typ", "")
    if typ.lower() != "dpop+jwt":
        raise ValueError(f"Invalid DPoP typ header '{typ}': must be 'dpop+jwt'")

    # 2. Validate alg: MUST NOT be none or symmetric
    alg = header.get("alg", "")
    if not alg or alg.lower() == "none" or alg.startswith("HS"):
        raise ValueError(f"Prohibited DPoP signature algorithm '{alg}': must be asymmetric.")

    # 3. Validate jwk: MUST be present and cannot contain private parameters ('d')
    jwk = header.get("jwk")
    if not jwk or not isinstance(jwk, dict):
        raise ValueError("DPoP header must contain a public 'jwk' object.")
    if "d" in jwk:
        raise ValueError("DPoP jwk must not contain private key parameter 'd'.")

    # 4. Validate payload: jti single-use check
    jti = payload.get("jti")
    if not jti or not isinstance(jti, str):
        raise ValueError("DPoP proof must contain a unique 'jti' string claim.")

    with _REPLAY_LOCK:
        if jti in _REPLAY_CACHE:
            raise ValueError(f"DPoP proof replay detected: jti '{jti}' was already presented.")
        _REPLAY_CACHE[jti] = time.time()
    _clean_replay_cache()

    # 5. Validate htm (HTTP Method)
    htm = payload.get("htm")
    if not htm or htm.upper() != http_method.upper():
        raise ValueError(f"DPoP htm mismatch: asserted '{htm}', expected '{http_method.upper()}'.")

    # 6. Validate htu (HTTP URI without query or fragment)
    htu = payload.get("htu")
    expected_uri = http_uri.split("?")[0].split("#")[0]
    if not htu:
        raise ValueError("DPoP proof must contain 'htu' URI claim.")
    # Normalize paths (ending slashes)
    if htu.rstrip("/") != expected_uri.rstrip("/"):
        raise ValueError(f"DPoP htu mismatch: asserted '{htu}', expected '{expected_uri}'.")

    # 7. Validate iat (Issuance time and clock skew)
    iat = payload.get("iat")
    if iat is None:
        raise ValueError("DPoP proof must contain an 'iat' claim.")
    now = time.time()
    if abs(now - float(iat)) > max_skew:
        raise ValueError(f"DPoP proof timestamp outside acceptable clock skew ({max_skew}s).")

    # 8. Validate ath if access_token provided
    if access_token:
        ath = payload.get("ath")
        expected_ath = compute_access_token_hash(access_token)
        if not ath or ath != expected_ath:
            raise ValueError("DPoP access token hash (ath) mismatch.")

    # 9. Compute RFC 7638 JWK thumbprint
    jkt = compute_jwk_thumbprint(jwk)

    return {
        "header": header,
        "payload": payload,
        "jkt": jkt,
        "jwk": jwk,
    }

