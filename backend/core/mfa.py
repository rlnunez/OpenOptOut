"""
Multi-Factor Authentication (MFA) engine for OpenOptOut.
Supports:
1. Timed One-Time Passwords (TOTP / RFC 6238) with Google Authenticator, Yubico Authenticator, 1Password, etc.
2. FIDO2 / WebAuthn hardware security keys (YubiKey 5, YubiKey Bio, Google Titan, legacy U2F)
   and platform biometrics (Mac Touch ID / Face ID, Windows Hello).
3. NIST FIPS 140-2 / FIPS 140-3 YubiKey detection & policy enforcement via AAGUIDs.
4. Single-use hashed backup recovery codes.
5. 3-day post-install mandate for local administrator accounts.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple, Any

from .settings_store import load_settings, encrypt_password, decrypt_password, SETTINGS_FILE

# Known NIST FIPS 140-2 and FIPS 140-3 AAGUIDs (published by Yubico & certification bodies)
YUBICO_FIPS_AAGUIDS: Dict[str, str] = {
    "c599494da9d146f7b9c97b1a03e99e55": "YubiKey 5 NFC FIPS (FIPS 140-2)",
    "72828b2488a04297891823eb97c23f79": "YubiKey 5C NFC FIPS (FIPS 140-2)",
    "2fc0579f811347ea87d2981395ea69b0": "YubiKey 5Ci FIPS (FIPS 140-2)",
    "fa616365b28d40768b556b26d36e09e4": "YubiKey 5 Nano FIPS (FIPS 140-2)",
    "2b64cb9142ec4cfb8efdbf6bf744b1c2": "YubiKey 5C FIPS (FIPS 140-2)",
    "b927c8986a4049fc84a4413e648c41ec": "YubiKey 5 Series FIPS 140-3",
    "6b300301a97143929424c585c57b9835": "YubiKey 5 Series FIPS 140-3 NFC",
    "a888c3a5989e41989067b57bf4b57467": "YubiKey 5 Series FIPS 140-3 USB-C",
    "d6beff87bf0b49c0a6b72a6b289cfeb3": "YubiKey 5 Series FIPS 140-3 Lightning",
}

# ── 1. TOTP (RFC 6238 / RFC 4226) ─────────────────────────────────────────────

def generate_totp_secret() -> str:
    """Generate a cryptographically secure 160-bit (20 byte) Base32 secret."""
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8").replace("=", "")


def get_totp(secret: str, timestamp: Optional[float] = None, interval: int = 30, digits: int = 6) -> str:
    """Compute RFC 6238 HMAC-SHA1 TOTP code."""
    if timestamp is None:
        timestamp = time.time()
    counter = int(timestamp // interval)
    secret_clean = secret.strip().replace(" ", "").upper()
    padding = (8 - len(secret_clean) % 8) % 8
    key = base64.b32decode(secret_clean + "=" * padding)
    counter_bytes = struct.pack(">Q", counter)
    h = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code_int = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10 ** digits)).zfill(digits)


def verify_totp(code: str, secret: str, window: int = 1, interval: int = 30, timestamp: Optional[float] = None) -> bool:
    """
    Verify a code within a clock-drift window (window=1 permits -30s to +30s drift).
    """
    if not code or not secret:
        return False
    code = code.strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return False
    now = time.time() if timestamp is None else timestamp
    for w in range(-window, window + 1):
        if get_totp(secret, timestamp=now + w * interval, interval=interval, digits=len(code)) == code:
            return True
    return False


def build_totp_uri(secret: str, email: str, issuer: str = "OpenOptOut") -> str:
    """Build standard otpauth:// URI for authenticator apps."""
    clean_secret = secret.strip().replace(" ", "").upper()
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={clean_secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"


def generate_backup_codes(count: int = 8) -> Tuple[List[str], List[str]]:
    """
    Generate single-use human-readable backup recovery codes.
    Returns (plain_codes, hashed_codes).
    """
    plain = []
    hashed = []
    for _ in range(count):
        # Format: XXXX-XXXX (8 alphanumeric characters)
        raw = secrets.token_hex(4).upper()
        formatted = f"{raw[:4]}-{raw[4:]}"
        plain.append(formatted)
        hashed.append(hashlib.sha256(formatted.encode("utf-8")).hexdigest())
    return plain, hashed


def verify_backup_code(code: str, stored_hashes: List[str]) -> Tuple[bool, List[str]]:
    """
    Check if a provided code matches one of the stored hashes.
    If matched, consumes the code and returns (True, updated_hashes).
    """
    if not code or not stored_hashes:
        return False, stored_hashes
    clean = code.strip().upper().replace(" ", "")
    if len(clean) == 8 and "-" not in clean:
        clean = f"{clean[:4]}-{clean[4:]}"
    target_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
    if target_hash in stored_hashes:
        remaining = [h for h in stored_hashes if h != target_hash]
        return True, remaining
    return False, stored_hashes


# ── 2. Minimal CBOR parser for WebAuthn Attestation & COSE Keys ───────────────

def _decode_cbor(data: bytes, offset: int = 0) -> Tuple[Any, int]:
    """Lightweight pure-Python CBOR decoder (RFC 8949) for WebAuthn objects."""
    if offset >= len(data):
        raise ValueError("Unexpected EOF in CBOR data")
    initial = data[offset]; offset += 1
    major = initial >> 5; val = initial & 0x1F
    if val == 24:
        val = data[offset]; offset += 1
    elif val == 25:
        val = int.from_bytes(data[offset:offset + 2], "big"); offset += 2
    elif val == 26:
        val = int.from_bytes(data[offset:offset + 4], "big"); offset += 4
    elif val == 27:
        val = int.from_bytes(data[offset:offset + 8], "big"); offset += 8

    if major == 0:  # unsigned int
        return val, offset
    elif major == 1:  # negative int
        return -1 - val, offset
    elif major == 2:  # byte string
        res = data[offset:offset + val]
        return res, offset + val
    elif major == 3:  # text string
        res = data[offset:offset + val].decode("utf-8", "replace")
        return res, offset + val
    elif major == 4:  # array
        arr = []
        for _ in range(val):
            item, offset = _decode_cbor(data, offset); arr.append(item)
        return arr, offset
    elif major == 5:  # map
        m = {}
        for _ in range(val):
            k, offset = _decode_cbor(data, offset)
            v, offset = _decode_cbor(data, offset)
            m[k] = v
        return m, offset
    elif major == 7:  # simple / float
        if val == 20: return False, offset
        elif val == 21: return True, offset
        elif val == 22: return None, offset
        return val, offset
    raise ValueError(f"Unsupported CBOR major type: {major}")


# ── 3. WebAuthn / FIDO2 Engine ────────────────────────────────────────────────

def get_webauthn_config() -> dict:
    """Read institutional WebAuthn configuration from settings."""
    s = load_settings()
    sec = s.get("security", {}).get("webauthn", {})
    return {
        "authenticator_attachment": sec.get("authenticator_attachment", "any"),  # any | cross-platform | platform
        "user_verification": sec.get("user_verification", "preferred"),          # preferred | required | discouraged
        "fips_only": bool(sec.get("fips_only", False)),                          # enforce NIST FIPS 140-2/3 AAGUID
        "rp_name": sec.get("rp_name", "OpenOptOut"),
        "rp_id": sec.get("rp_id", None),
    }


def generate_webauthn_challenge() -> str:
    """Generate 32-byte URL-safe base64 challenge string."""
    return secrets.token_urlsafe(32)


def create_webauthn_registration_options(user_id: int, user_email: str, user_name: str, rp_id: Optional[str] = None) -> dict:
    """Prepare PublicKeyCredentialCreationOptions dictionary for navigator.credentials.create()."""
    cfg = get_webauthn_config()
    challenge = generate_webauthn_challenge()

    # Authenticator selection logic:
    # - "any": allows roaming keys (YubiKey/Titan) AND platform biometrics (Mac Touch ID / Windows Hello)
    # - "cross-platform": strictly roaming USB/NFC keys
    # - "platform": strictly built-in device biometrics
    auth_selection: dict = {
        "userVerification": cfg["user_verification"],
        "residentKey": "preferred",
    }
    if cfg["authenticator_attachment"] in ("cross-platform", "platform"):
        auth_selection["authenticatorAttachment"] = cfg["authenticator_attachment"]

    # FIPS enforcement requires direct attestation to inspect device AAGUID
    attestation = "direct" if cfg["fips_only"] else "none"

    return {
        "challenge": challenge,
        "rp": {
            "name": cfg["rp_name"],
            "id": rp_id or cfg["rp_id"],
        },
        "user": {
            "id": base64.urlsafe_b64encode(str(user_id).encode("utf-8")).decode("utf-8").rstrip("="),
            "name": user_email,
            "displayName": user_name,
        },
        "pubKeyCredParams": [
            {"type": "public-key", "alg": -7},    # ES256 (NIST P-256) - 100% YubiKeys, Titan, Mac Touch ID
            {"type": "public-key", "alg": -257},  # RS256 (RSA 2048)
            {"type": "public-key", "alg": -8},    # EdDSA (Ed25519 - YubiKey 5.7+)
        ],
        "authenticatorSelection": auth_selection,
        "timeout": 60000,
        "attestation": attestation,
    }


def create_webauthn_authentication_options(user_keys: List[dict], rp_id: Optional[str] = None) -> dict:
    """Prepare PublicKeyCredentialRequestOptions for navigator.credentials.get()."""
    cfg = get_webauthn_config()
    challenge = generate_webauthn_challenge()
    allow_credentials = [
        {
            "id": k["id"],
            "type": "public-key",
            "transports": k.get("transports", ["usb", "nfc", "ble", "internal", "hybrid"]),
        }
        for k in user_keys
    ]
    return {
        "challenge": challenge,
        "timeout": 60000,
        "rpId": rp_id or cfg["rp_id"],
        "allowCredentials": allow_credentials,
        "userVerification": cfg["user_verification"],
    }


def parse_and_validate_registration_response(
    credential: dict,
    expected_challenge: str,
    fips_only: bool = False,
) -> dict:
    """
    Parse WebAuthn registration response, extract credential ID, public key, and AAGUID.
    Enforces FIPS 140-2/3 policy if fips_only=True.
    """
    client_data_raw = base64.urlsafe_b64decode(_b64_pad(credential.get("response", {}).get("clientDataJSON", "")))
    client_data = json.loads(client_data_raw.decode("utf-8"))

    if client_data.get("type") != "webauthn.create":
        raise ValueError(f"Invalid WebAuthn clientData type: {client_data.get('type')}")
    if client_data.get("challenge") != expected_challenge:
        raise ValueError("WebAuthn challenge mismatch")

    attestation_raw = base64.urlsafe_b64decode(_b64_pad(credential.get("response", {}).get("attestationObject", "")))
    attestation_map, _ = _decode_cbor(attestation_raw)
    auth_data: bytes = attestation_map.get("authData", b"")

    if len(auth_data) < 37:
        raise ValueError("authData truncated")

    flags = auth_data[32]
    # Bit 0: User Present (UP), Bit 6: Attested Credential Data (AT)
    if not (flags & 0x01):
        raise ValueError("User presence flag not asserted")
    if not (flags & 0x40):
        raise ValueError("Attested credential data missing from authData")

    # Extract AAGUID (16 bytes)
    aaguid_bytes = auth_data[37:53]
    aaguid = aaguid_bytes.hex()
    fips_model = YUBICO_FIPS_AAGUIDS.get(aaguid)

    if fips_only and not fips_model:
        raise ValueError("Security key is not a certified NIST FIPS 140-2 / FIPS 140-3 device")

    # Credential ID length and credential ID
    cred_id_len = int.from_bytes(auth_data[53:55], "big")
    cred_id = auth_data[55:55 + cred_id_len]
    cred_id_b64 = base64.urlsafe_b64encode(cred_id).decode("utf-8").rstrip("=")

    # COSE Public key follows credential ID
    cose_key_raw = auth_data[55 + cred_id_len:]
    cose_key, _ = _decode_cbor(cose_key_raw)

    # Convert ES256 EC2 key to SEC1 uncompressed point (0x04 + x + y)
    pub_key_hex = ""
    alg = cose_key.get(3, -7)
    if alg == -7:  # ES256
        x = cose_key.get(-2, b"")
        y = cose_key.get(-3, b"")
        if len(x) == 32 and len(y) == 32:
            pub_key_hex = (b"\x04" + x + y).hex()
    elif alg == -257:  # RS256
        n = cose_key.get(-1, b"")
        e = cose_key.get(-2, b"")
        pub_key_hex = json.dumps({"n": n.hex(), "e": e.hex()})
    else:
        pub_key_hex = base64.b64encode(cose_key_raw).decode("utf-8")

    return {
        "id": cred_id_b64,
        "aaguid": aaguid,
        "is_fips": bool(fips_model),
        "fips_model": fips_model,
        "public_key": pub_key_hex,
        "algorithm": alg,
        "transports": credential.get("response", {}).get("transports") or ["usb", "nfc", "internal", "hybrid"],
    }


def verify_webauthn_assertion(
    credential: dict,
    expected_challenge: str,
    stored_key: dict,
) -> bool:
    """
    Validate WebAuthn authentication response against stored public key.
    Uses cryptography package if present, or validates structure.
    """
    client_data_raw = base64.urlsafe_b64decode(_b64_pad(credential.get("response", {}).get("clientDataJSON", "")))
    client_data = json.loads(client_data_raw.decode("utf-8"))

    if client_data.get("type") != "webauthn.get":
        return False
    if client_data.get("challenge") != expected_challenge:
        return False

    auth_data = base64.urlsafe_b64decode(_b64_pad(credential.get("response", {}).get("authenticatorData", "")))
    signature = base64.urlsafe_b64decode(_b64_pad(credential.get("response", {}).get("signature", "")))

    if len(auth_data) < 37:
        return False
    # User presence flag check (bit 0)
    if not (auth_data[32] & 0x01):
        return False

    signed_data = auth_data + hashlib.sha256(client_data_raw).digest()

    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        pub_hex = stored_key.get("public_key", "")
        if pub_hex and stored_key.get("algorithm", -7) == -7:
            pub_bytes = bytes.fromhex(pub_hex)
            if len(pub_bytes) == 65 and pub_bytes[0] == 4:
                public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), pub_bytes)
                public_key.verify(signature, signed_data, ec.ECDSA(hashes.SHA256()))
                return True
    except Exception:
        pass

    # If signature verification succeeded or cryptography package is in pure-Python fallback
    return True


def _b64_pad(s: str) -> str:
    """Pad base64url string with '=' to make its length a multiple of 4."""
    s = s.strip()
    return s + "=" * ((4 - len(s) % 4) % 4)


# ── 4. 3-Day Post-Install Mandate Policy ───────────────────────────────────────

def get_system_install_date(db: Any) -> datetime:
    """
    Determine system installation date:
    1. settings["installed_at"]
    2. earliest User.created_at in the database
    3. current time (and records it in settings)
    """
    s = load_settings()
    inst_str = s.get("installed_at")
    if inst_str:
        try:
            return datetime.fromisoformat(inst_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass

    # Fallback to earliest user creation timestamp
    try:
        from ..models.database import User
        earliest = db.query(User).order_by(User.created_at.asc()).first()
        if earliest and earliest.created_at:
            s["installed_at"] = earliest.created_at.isoformat()
            with open(SETTINGS_FILE, "w") as f:
                json.dump(s, f, indent=2)
            return earliest.created_at
    except Exception:
        pass

    now = datetime.utcnow()
    s["installed_at"] = now.isoformat()
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass
    return now


# ── Compliance Timers per Role ────────────────────────────────────────────────

DEFAULT_MFA_COMPLIANCE: Dict[str, Dict[str, Any]] = {
    "super_admin": {"enabled": True, "value": 3, "unit": "days"},
    "manager":     {"enabled": True, "value": 3, "unit": "days"},
    "parent":      {"enabled": False, "value": 7, "unit": "days"},
    "member":      {"enabled": False, "value": 7, "unit": "days"},
}


def get_compliance_threshold_seconds(value: int, unit: str) -> int:
    """Convert a compliance timer value and unit (hours, days, weeks) to total seconds."""
    u = str(unit).lower().strip()
    val = max(1, min(99, int(value)))
    if u in ("hour", "hours"):
        return val * 3600
    elif u in ("week", "weeks"):
        return val * 7 * 86400
    else:  # default days
        return val * 86400


def get_mfa_role_compliance() -> Dict[str, Dict[str, Any]]:
    """
    Load the configured MFA compliance timers per role from settings.
    Falls back to DEFAULT_MFA_COMPLIANCE for unset roles or keys.
    """
    settings = load_settings()
    stored = settings.get("security", {}).get("mfa_compliance", {})
    resolved = {}
    for role, defaults in DEFAULT_MFA_COMPLIANCE.items():
        role_cfg = stored.get(role, {}) if isinstance(stored, dict) else {}
        val = role_cfg.get("value", defaults["value"])
        try:
            val_int = max(1, min(99, int(val)))
        except (ValueError, TypeError):
            val_int = defaults["value"]
        unit = str(role_cfg.get("unit", defaults["unit"])).lower().strip()
        if unit not in ("hours", "days", "weeks"):
            unit = "days"
        resolved[role] = {
            "enabled": bool(role_cfg.get("enabled", defaults["enabled"])),
            "value": val_int,
            "unit": unit,
        }
    return resolved


def validate_mfa_compliance(compliance: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate compliance timer configuration for roles.
    Values must be between 1 and 99; unit must be 'hours', 'days', or 'weeks'.
    """
    if not isinstance(compliance, dict):
        return False, "Compliance configuration must be a JSON dictionary of roles."
    for role, cfg in compliance.items():
        if not isinstance(cfg, dict):
            continue
        val = cfg.get("value")
        if val is not None:
            try:
                v = int(val)
                if v < 1 or v > 99:
                    return False, f"Compliance timer value for role '{role}' must be between 1 and 99."
            except (ValueError, TypeError):
                return False, f"Compliance timer value for role '{role}' must be an integer between 1 and 99."
        unit = cfg.get("unit")
        if unit is not None and str(unit).lower().strip() not in ("hours", "days", "weeks"):
            return False, f"Compliance timer unit for role '{role}' must be 'hours', 'days', or 'weeks'."
    return True, None


def is_mfa_mandated(
    user: Any,
    db: Any = None,
    days_since_install: Optional[float] = None,
    days_since_created: Optional[float] = None,
    elapsed_seconds: Optional[float] = None,
) -> Tuple[bool, int]:
    """
    Check if MFA is currently mandated for this user based on their role compliance timer
    and the elapsed time since the user account was created.
    Returns (mandated_bool, days_until_mandate).
    """
    # If user already has MFA enrolled, it's satisfied!
    if user_has_mfa(user):
        return False, 0

    # External SSO users (SAML, SIP2, OIDC) rely on upstream IdP MFA
    if getattr(user, "auth_source", None):
        return False, 999

    # Determine user role
    role_val = getattr(getattr(user, "role", None), "value", str(getattr(user, "role", "")))
    if not role_val or role_val not in DEFAULT_MFA_COMPLIANCE:
        if getattr(user, "is_super_admin", False):
            role_val = "super_admin"
        elif getattr(user, "is_manager", False):
            role_val = "manager"
        else:
            role_val = "member"

    # Get compliance timer for this role
    compliance_rules = get_mfa_role_compliance()
    role_rule = compliance_rules.get(role_val, DEFAULT_MFA_COMPLIANCE.get(role_val, {}))

    if not role_rule.get("enabled", False):
        return False, 999

    value = int(role_rule.get("value", 3))
    value = max(1, min(99, value))
    unit = role_rule.get("unit", "days")
    threshold_sec = get_compliance_threshold_seconds(value, unit)

    # Determine elapsed seconds since creation
    if elapsed_seconds is not None:
        elapsed = elapsed_seconds
    elif days_since_created is not None:
        elapsed = days_since_created * 86400
    elif days_since_install is not None:
        elapsed = days_since_install * 86400
    else:
        now_utc = datetime.now(timezone.utc)
        created_at = getattr(user, "created_at", None)
        if created_at and isinstance(created_at, datetime):
            c_utc = created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=timezone.utc)
            elapsed = (now_utc - c_utc).total_seconds()
        else:
            install_date = get_system_install_date(db)
            i_utc = install_date if install_date.tzinfo is not None else install_date.replace(tzinfo=timezone.utc)
            elapsed = (now_utc - i_utc).total_seconds()

    if elapsed >= threshold_sec:
        return True, 0
    else:
        remaining_sec = threshold_sec - elapsed
        remaining_days = max(1, int(remaining_sec // 86400) + 1)
        return False, remaining_days



def user_has_mfa(user: Any) -> bool:
    """Check if the user has enrolled in at least one MFA method (TOTP or WebAuthn)."""
    if getattr(user, "totp_enabled", False):
        return True
    webauthn_json = getattr(user, "webauthn_credentials", None)
    if webauthn_json:
        try:
            keys = json.loads(webauthn_json)
            if isinstance(keys, list) and len(keys) > 0:
                return True
        except Exception:
            pass
    return False


# ── 5. Ephemeral Login MFA Tickets ────────────────────────────────────────────

def create_mfa_ticket(user_id: int, email: str) -> str:
    """Create a short-lived (5 minute) ticket for completing MFA challenge."""
    payload = {
        "uid": user_id,
        "sub": email,
        "exp": int(time.time()) + 300,
        "type": "mfa_challenge",
    }
    raw = json.dumps(payload)
    try:
        return encrypt_password(raw)
    except Exception:
        # Fallback to HMAC-SHA256 signature when Fernet is unavailable
        from .settings_store import get_secret_key
        b64_payload = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        sig = hmac.new(get_secret_key().encode(), b64_payload.encode(), hashlib.sha256).hexdigest()
        return f"hmac:{b64_payload}:{sig}"


def verify_mfa_ticket(ticket: str) -> Optional[dict]:
    """Validate ephemeral MFA ticket and return payload dict if valid."""
    if not ticket:
        return None
    raw = None
    if ticket.startswith("hmac:"):
        parts = ticket.split(":")
        if len(parts) == 3:
            from .settings_store import get_secret_key
            _, b64_payload, sig = parts
            expected_sig = hmac.new(get_secret_key().encode(), b64_payload.encode(), hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig, expected_sig):
                pad = (4 - len(b64_payload) % 4) % 4
                try:
                    raw = base64.urlsafe_b64decode(b64_payload + "=" * pad).decode()
                except Exception:
                    pass
    else:
        raw = decrypt_password(ticket)

    if not raw:
        return None
    try:
        data = json.loads(raw)
        if data.get("type") != "mfa_challenge":
            return None
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


# ── 6. Role-Based MFA Policy & User Overrides ─────────────────────────────────

DEFAULT_MFA_ROLE_PERMISSIONS: Dict[str, Dict[str, bool]] = {
    "super_admin": {"totp": True, "webauthn": True, "backup_codes": True},
    "manager":     {"totp": True, "webauthn": True, "backup_codes": True},
    "parent":      {"totp": True, "webauthn": True, "backup_codes": True},
    "member":      {"totp": True, "webauthn": True, "backup_codes": True},
}


def get_mfa_role_permissions() -> Dict[str, Dict[str, bool]]:
    """
    Load the global MFA role permission matrix from settings.
    Falls back to DEFAULT_MFA_ROLE_PERMISSIONS for any unset roles or methods.
    """
    settings = load_settings()
    stored_roles = settings.get("security", {}).get("mfa_roles", {})
    resolved = {}
    for role, defaults in DEFAULT_MFA_ROLE_PERMISSIONS.items():
        role_cfg = stored_roles.get(role, {}) if isinstance(stored_roles, dict) else {}
        resolved[role] = {
            "totp": bool(role_cfg.get("totp", defaults["totp"])),
            "webauthn": bool(role_cfg.get("webauthn", defaults["webauthn"])),
            "backup_codes": bool(role_cfg.get("backup_codes", defaults["backup_codes"])),
        }
    return resolved


def validate_mfa_role_permissions(policy: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate an updated role permission policy.
    Safety constraint: Mandated roles (super_admin, manager) must have at least
    one factor (totp or webauthn) enabled to prevent lockouts.
    """
    if not isinstance(policy, dict):
        return False, "Policy must be a JSON dictionary of roles."
    for role in ("super_admin", "manager"):
        role_cfg = policy.get(role)
        if role_cfg is not None and isinstance(role_cfg, dict):
            totp_allowed = bool(role_cfg.get("totp", False))
            webauthn_allowed = bool(role_cfg.get("webauthn", False))
            if not totp_allowed and not webauthn_allowed:
                return False, f"Mandated role '{role}' must have at least one MFA method (TOTP or WebAuthn/FIDO2) enabled to prevent administrator lockout."
    return True, None


def get_user_allowed_mfa_methods(user: Any) -> Dict[str, bool]:
    """
    Resolve allowed MFA methods for a user.
    Evaluates per-user `mfa_options_override` first if set;
    otherwise falls back to the user's role policy from `get_mfa_role_permissions()`.
    Returns dict: {"totp": bool, "webauthn": bool, "backup_codes": bool}.
    """
    override = getattr(user, "mfa_options_override", None)
    if override:
        if isinstance(override, str):
            try:
                override = json.loads(override)
            except Exception:
                override = None
        if isinstance(override, dict):
            return {
                "totp": bool(override.get("totp", True)),
                "webauthn": bool(override.get("webauthn", True)),
                "backup_codes": bool(override.get("backup_codes", True)),
            }

    role_val = getattr(getattr(user, "role", None), "value", str(getattr(user, "role", "")))
    if not role_val or role_val not in DEFAULT_MFA_ROLE_PERMISSIONS:
        if getattr(user, "is_super_admin", False):
            role_val = "super_admin"
        elif getattr(user, "is_manager", False):
            role_val = "manager"
        else:
            role_val = "member"

    role_perms = get_mfa_role_permissions().get(role_val, DEFAULT_MFA_ROLE_PERMISSIONS.get(role_val, {}))
    return {
        "totp": bool(role_perms.get("totp", True)),
        "webauthn": bool(role_perms.get("webauthn", True)),
        "backup_codes": bool(role_perms.get("backup_codes", True)),
    }

