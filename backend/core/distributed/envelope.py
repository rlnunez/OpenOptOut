"""
Distributed Job Envelope & Secure Payload Serialization (Roadmap Phase 7.1).

Defines the self-contained message envelopes exchanged across the boundary
between the Control Plane and the Stateless Worker Fleet.

Envelopes decouple execution workers from database ORM models entirely:
  - Control plane compiles jobs/queries, wraps them in a signed/encrypted JobEnvelope,
    and enqueues them.
  - Workers receive the serialized envelope, verify HMAC integrity, execute
    Playwright or discovery bots in their sandbox, and return a JobResultEnvelope.
  - Neither worker nor queue requires direct database access or ORM sessions.

Security & Integrity:
  - Canonical JSON serialization with deterministic key ordering.
  - HMAC-SHA256 signature verification preventing tampering or injection in transport.
  - Authenticated payload encryption for PII-at-rest in queues.
  - Memory zeroization on sensitive payload fields (Roadmap Item 15).
  - Expiration / replay protection via TTL and timestamp checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
import uuid
import hmac
import hashlib
import base64
import secrets
from typing import Optional, Any, Dict, List, Union

from ..memory_hygiene import SecureBuffer

# Optional cryptography package support (Fernet)
try:
    from cryptography.fernet import Fernet, InvalidToken
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False
    Fernet = None
    InvalidToken = Exception


# ── Exceptions ────────────────────────────────────────────────────────────────

class EnvelopeError(Exception):
    """Base exception for distributed envelope operations."""
    pass


class EnvelopeTamperedError(EnvelopeError):
    """Raised when an envelope's HMAC signature is invalid or payload was modified."""
    pass


class EnvelopeExpiredError(EnvelopeError):
    """Raised when an envelope has exceeded its time-to-live (TTL)."""
    pass


class EnvelopeInvalidError(EnvelopeError):
    """Raised when envelope fields or structure violate the schema."""
    pass


# ── Canonical Serialization & Cryptographic Helpers ──────────────────────────

def canonical_json(data: Dict[str, Any]) -> str:
    """
    Produce a deterministic, compact JSON string with sorted keys.
    Guarantees bit-for-bit identical representations on both sender and receiver.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_envelope_hmac(data: Dict[str, Any], secret_key: Union[str, bytes]) -> str:
    """
    Compute the HMAC-SHA256 hex digest for an envelope dictionary,
    strictly omitting any existing 'hmac_signature' field.
    """
    if not secret_key:
        raise EnvelopeError("secret_key cannot be empty for HMAC computation")
    key_bytes = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    copy_dict = {k: v for k, v in data.items() if k != "hmac_signature"}
    canonical = canonical_json(copy_dict).encode("utf-8")
    return hmac.new(key_bytes, canonical, hashlib.sha256).hexdigest()


def _derive_symmetric_key(secret_key: Union[str, bytes]) -> bytes:
    """Derive a 32-byte key using SHA-256 for authenticated payload encryption."""
    raw = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    return hashlib.sha256(raw).digest()


def encrypt_payload_bytes(plaintext: bytes, secret_key: Union[str, bytes]) -> str:
    """
    Encrypt plaintext payload bytes. Uses Fernet if cryptography is installed,
    otherwise uses an authenticated pure-Python HMAC-CTR stream cipher.
    """
    key_bytes = _derive_symmetric_key(secret_key)

    if HAS_FERNET and Fernet is not None:
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        f = Fernet(fernet_key)
        return "FNT:" + f.encrypt(plaintext).decode("ascii")

    # Pure-Python authenticated CTR stream cipher (zero external dependencies)
    iv = secrets.token_bytes(16)
    cipher_chunks = []
    chunk_size = 32
    for i in range(0, len(plaintext), chunk_size):
        chunk = plaintext[i:i + chunk_size]
        counter = (i // chunk_size).to_bytes(4, "big")
        keystream = hmac.new(key_bytes, iv + counter, hashlib.sha256).digest()[:len(chunk)]
        cipher_chunks.append(bytes(a ^ b for a, b in zip(chunk, keystream)))

    ciphertext = b"".join(cipher_chunks)
    mac = hmac.new(key_bytes, b"ENC-CTR:" + iv + ciphertext, hashlib.sha256).digest()
    blob = b"CTR1:" + iv + mac + ciphertext
    return base64.b64encode(blob).decode("ascii")


def decrypt_payload_bytes(ciphertext_str: str, secret_key: Union[str, bytes]) -> bytes:
    """
    Decrypt payload ciphertext back to raw bytes.
    """
    key_bytes = _derive_symmetric_key(secret_key)

    if ciphertext_str.startswith("FNT:") and HAS_FERNET and Fernet is not None:
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        f = Fernet(fernet_key)
        token = ciphertext_str[4:].encode("ascii")
        try:
            return f.decrypt(token)
        except Exception as e:
            raise EnvelopeTamperedError(f"Fernet payload decryption failed: {e}")

    try:
        blob = base64.b64decode(ciphertext_str)
    except Exception as e:
        raise EnvelopeInvalidError(f"Malformed base64 ciphertext: {e}")

    if not blob.startswith(b"CTR1:") or len(blob) < 5 + 16 + 32:
        raise EnvelopeInvalidError("Unrecognized ciphertext envelope header or truncated payload")

    iv = blob[5:21]
    expected_mac = blob[21:53]
    ciphertext = blob[53:]

    actual_mac = hmac.new(key_bytes, b"ENC-CTR:" + iv + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_mac, expected_mac):
        raise EnvelopeTamperedError("Authenticated ciphertext MAC mismatch — payload was tampered")

    plain_chunks = []
    chunk_size = 32
    for i in range(0, len(ciphertext), chunk_size):
        chunk = ciphertext[i:i + chunk_size]
        counter = (i // chunk_size).to_bytes(4, "big")
        keystream = hmac.new(key_bytes, iv + counter, hashlib.sha256).digest()[:len(chunk)]
        plain_chunks.append(bytes(a ^ b for a, b in zip(chunk, keystream)))

    return b"".join(plain_chunks)


def _scrub_object_in_place(obj: Any) -> None:
    """Recursively scrub values in memory for sensitive dictionaries/lists."""
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            val = obj[k]
            if isinstance(val, (dict, list)):
                _scrub_object_in_place(val)
            elif isinstance(val, (bytes, bytearray)):
                buf = SecureBuffer(val)
                buf.zeroize()
                obj[k] = b""
            elif isinstance(val, str):
                obj[k] = ""
        obj.clear()
    elif isinstance(obj, list):
        for i in range(len(obj)):
            if isinstance(obj[i], (dict, list)):
                _scrub_object_in_place(obj[i])
            else:
                obj[i] = None
        obj.clear()


# ── JobEnvelope (Dispatch from Control Plane to Worker) ────────────────────────

@dataclass
class JobEnvelope:
    """
    Self-contained, serializable job request sent to worker nodes.
    Supports both 'removal' (opt-out forms/emails) and 'discovery' (profile recon).
    """
    broker_id: str
    broker_name: str
    member_id: str
    action: str = "removal"                           # "removal" | "discovery"
    envelope_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: str = "normal"                          # "high" | "normal" | "low"
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    request_id: Optional[int] = None                  # Control plane database ID (if removal)
    request_key: Optional[str] = None                 # Public tracking UUID
    payload: Dict[str, Any] = field(default_factory=dict)
    encrypted_payload: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    hmac_signature: str = ""
    is_zeroized: bool = False

    @property
    def is_encrypted(self) -> bool:
        """Return True if the envelope payload is encrypted."""
        return bool(self.encrypted_payload)

    def __post_init__(self):
        if self.action not in ("removal", "discovery"):
            raise EnvelopeInvalidError(f"Unsupported action: '{self.action}'")
        if not self.broker_id:
            raise EnvelopeInvalidError("broker_id is required")
        if not self.member_id:
            raise EnvelopeInvalidError("member_id is required")

    def sign(self, secret_key: Union[str, bytes]) -> "JobEnvelope":
        """Compute and set HMAC signature on this envelope."""
        self.hmac_signature = compute_envelope_hmac(self.to_dict(), secret_key)
        return self

    def verify(self, secret_key: Union[str, bytes], allow_expired: bool = False) -> bool:
        """
        Verify the envelope's HMAC signature and expiration timestamp.
        Raises EnvelopeTamperedError on signature mismatch or EnvelopeExpiredError on expiry.
        """
        if not self.hmac_signature:
            raise EnvelopeTamperedError("Envelope has no HMAC signature")

        expected = compute_envelope_hmac(self.to_dict(), secret_key)
        # Compare as bytes: compare_digest() raises TypeError on non-ASCII str,
        # which let a crafted signature crash verification instead of failing it.
        if not hmac.compare_digest(self.hmac_signature.encode("utf-8"), expected.encode("utf-8")):
            raise EnvelopeTamperedError(
                f"HMAC signature mismatch on envelope '{self.envelope_id}' — payload was tampered"
            )

        if not allow_expired and self.expires_at and time.time() > self.expires_at:
            raise EnvelopeExpiredError(
                f"Envelope '{self.envelope_id}' expired at {self.expires_at} (current: {time.time()})"
            )
        return True

    def is_expired(self) -> bool:
        """Return True if envelope has an expiration timestamp and current time exceeds it."""
        return bool(self.expires_at is not None and time.time() > self.expires_at)

    def encrypt_payload(self, secret_key: Union[str, bytes]) -> "JobEnvelope":
        """
        Encrypt the internal plaintext payload into encrypted_payload and
        zeroize the plaintext payload dictionary.
        """
        if not self.payload and self.encrypted_payload:
            return self  # already encrypted

        raw_json = canonical_json(self.payload).encode("utf-8")
        self.encrypted_payload = encrypt_payload_bytes(raw_json, secret_key)
        _scrub_object_in_place(self.payload)
        self.payload = {}
        # Re-sign if signature was already present
        if self.hmac_signature:
            self.sign(secret_key)
        return self

    def decrypt_payload(self, secret_key: Union[str, bytes]) -> "JobEnvelope":
        """
        Decrypt encrypted_payload back into the plaintext payload dictionary.
        """
        if not self.encrypted_payload:
            return self  # already plaintext or empty

        decrypted_bytes = decrypt_payload_bytes(self.encrypted_payload, secret_key)
        self.payload = json.loads(decrypted_bytes.decode("utf-8"))
        self.encrypted_payload = None
        # Re-sign if signature was already present
        if self.hmac_signature:
            self.sign(secret_key)
        return self

    def zeroize(self) -> None:
        """Scrub sensitive patron data from process memory."""
        _scrub_object_in_place(self.payload)
        self.payload = {}
        if self.encrypted_payload:
            buf = SecureBuffer.from_str(self.encrypted_payload)
            buf.zeroize()
            self.encrypted_payload = ""
        self.is_zeroized = True

    def __enter__(self) -> "JobEnvelope":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.zeroize()

    def to_dict(self) -> Dict[str, Any]:
        """Convert envelope to dictionary."""
        d = {
            "envelope_id": self.envelope_id,
            "action": self.action,
            "priority": self.priority,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "broker_id": self.broker_id,
            "broker_name": self.broker_name,
            "member_id": self.member_id,
            "request_id": self.request_id,
            "request_key": self.request_key,
            "payload": self.payload,
            "encrypted_payload": self.encrypted_payload,
            "meta": self.meta,
        }
        if self.hmac_signature:
            d["hmac_signature"] = self.hmac_signature
        return d

    def to_json(self) -> str:
        """Convert envelope to canonical JSON string."""
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(
        cls,
        d: Dict[str, Any],
        secret_key: Optional[Union[str, bytes]] = None,
        verify_signature: bool = True,
        allow_expired: bool = False,
    ) -> "JobEnvelope":
        """Reconstruct JobEnvelope from dictionary, optionally verifying signature."""
        if not isinstance(d, dict):
            raise EnvelopeInvalidError("envelope must be a JSON object")
        try:
            env = cls(
                envelope_id=d.get("envelope_id", str(uuid.uuid4())),
                action=d.get("action", "removal"),
                priority=d.get("priority", "normal"),
                created_at=float(d.get("created_at", time.time())),
                expires_at=float(d["expires_at"]) if d.get("expires_at") is not None else None,
                broker_id=str(d.get("broker_id", "")),
                broker_name=str(d.get("broker_name", "")),
                member_id=str(d.get("member_id", "")),
                request_id=d.get("request_id"),
                request_key=d.get("request_key"),
                payload=dict(d.get("payload", {})),
                encrypted_payload=d.get("encrypted_payload"),
                meta=dict(d.get("meta", {})),
                hmac_signature=str(d.get("hmac_signature", "")),
            )
        except EnvelopeError:
            raise
        except (TypeError, ValueError, AttributeError, OverflowError) as e:
            # Queue contents are untrusted (anyone who can write to Redis):
            # report malformed fields as an invalid envelope, never a crash.
            raise EnvelopeInvalidError(f"Malformed envelope field: {e}") from None
        if verify_signature and secret_key:
            env.verify(secret_key, allow_expired=allow_expired)
        return env

    @classmethod
    def from_json(
        cls,
        json_str: str,
        secret_key: Optional[Union[str, bytes]] = None,
        verify_signature: bool = True,
        allow_expired: bool = False,
    ) -> "JobEnvelope":
        """Reconstruct JobEnvelope from JSON string."""
        try:
            d = json.loads(json_str)
        except Exception as e:
            raise EnvelopeInvalidError(f"Malformed envelope JSON: {e}")
        return cls.from_dict(
            d,
            secret_key=secret_key,
            verify_signature=verify_signature,
            allow_expired=allow_expired,
        )


# ── JobResultEnvelope (Response from Worker to Control Plane) ──────────────────

@dataclass
class JobResultEnvelope:
    """
    Self-contained execution result returned by a worker node to the control plane.
    Captures execution status, trace, screenshot assets, CAPTCHA challenges,
    and discovery search outcomes.
    """
    envelope_id: str
    action: str
    broker_id: str
    member_id: str
    ok: bool
    status: str = "success"                           # "success" | "failure" | "captcha" | "manual" | "timeout" | "error"
    created_at: float = field(default_factory=time.time)
    completed_at: float = field(default_factory=time.time)
    duration_ms: int = 0
    worker_id: str = "worker-default"
    request_id: Optional[int] = None
    request_key: Optional[str] = None
    result: Dict[str, Any] = field(default_factory=dict)
    screenshots: Dict[str, str] = field(default_factory=dict)  # name -> base64
    error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    hmac_signature: str = ""
    is_zeroized: bool = False

    def __post_init__(self):
        if not self.envelope_id:
            raise EnvelopeInvalidError("envelope_id is required")
        if self.action not in ("removal", "discovery"):
            raise EnvelopeInvalidError(f"Unsupported action: '{self.action}'")

    def sign(self, secret_key: Union[str, bytes]) -> "JobResultEnvelope":
        """Compute and set HMAC signature on this result envelope."""
        self.hmac_signature = compute_envelope_hmac(self.to_dict(), secret_key)
        return self

    def verify(self, secret_key: Union[str, bytes]) -> bool:
        """Verify the result envelope's HMAC signature."""
        if not self.hmac_signature:
            raise EnvelopeTamperedError("Result envelope has no HMAC signature")

        expected = compute_envelope_hmac(self.to_dict(), secret_key)
        # Compare as bytes: compare_digest() raises TypeError on non-ASCII str,
        # which let a crafted signature crash verification instead of failing it.
        if not hmac.compare_digest(self.hmac_signature.encode("utf-8"), expected.encode("utf-8")):
            raise EnvelopeTamperedError(
                f"HMAC signature mismatch on result envelope '{self.envelope_id}' — payload was tampered"
            )
        return True

    def zeroize(self) -> None:
        """Scrub memory buffers (including screenshots)."""
        _scrub_object_in_place(self.result)
        self.result = {}
        for k, v in list(self.screenshots.items()):
            buf = SecureBuffer.from_str(v)
            buf.zeroize()
            self.screenshots[k] = ""
        self.screenshots.clear()
        self.is_zeroized = True

    def __enter__(self) -> "JobResultEnvelope":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.zeroize()

    def to_dict(self) -> Dict[str, Any]:
        """Convert result envelope to dictionary."""
        d = {
            "envelope_id": self.envelope_id,
            "action": self.action,
            "broker_id": self.broker_id,
            "member_id": self.member_id,
            "ok": self.ok,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "worker_id": self.worker_id,
            "request_id": self.request_id,
            "request_key": self.request_key,
            "result": self.result,
            "screenshots": self.screenshots,
            "error": self.error,
            "meta": self.meta,
        }
        if self.hmac_signature:
            d["hmac_signature"] = self.hmac_signature
        return d

    def to_json(self) -> str:
        """Convert result envelope to canonical JSON string."""
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(
        cls,
        d: Dict[str, Any],
        secret_key: Optional[Union[str, bytes]] = None,
        verify_signature: bool = True,
    ) -> "JobResultEnvelope":
        """Reconstruct JobResultEnvelope from dictionary."""
        if not isinstance(d, dict):
            raise EnvelopeInvalidError("result envelope must be a JSON object")
        try:
            res = cls(
                envelope_id=str(d.get("envelope_id", "")),
                action=str(d.get("action", "removal")),
                broker_id=str(d.get("broker_id", "")),
                member_id=str(d.get("member_id", "")),
                ok=bool(d.get("ok", False)),
                status=str(d.get("status", "success")),
                created_at=float(d.get("created_at", time.time())),
                completed_at=float(d.get("completed_at", time.time())),
                duration_ms=int(d.get("duration_ms", 0)),
                worker_id=str(d.get("worker_id", "worker-default")),
                request_id=d.get("request_id"),
                request_key=d.get("request_key"),
                result=dict(d.get("result", {})),
                screenshots=dict(d.get("screenshots", {})),
                error=d.get("error"),
                meta=dict(d.get("meta", {})),
                hmac_signature=str(d.get("hmac_signature", "")),
            )
        except EnvelopeError:
            raise
        except (TypeError, ValueError, AttributeError, OverflowError) as e:
            raise EnvelopeInvalidError(f"Malformed result envelope field: {e}") from None
        if verify_signature and secret_key:
            res.verify(secret_key)
        return res

    @classmethod
    def from_json(
        cls,
        json_str: str,
        secret_key: Optional[Union[str, bytes]] = None,
        verify_signature: bool = True,
    ) -> "JobResultEnvelope":
        """Reconstruct JobResultEnvelope from JSON string."""
        try:
            d = json.loads(json_str)
        except Exception as e:
            raise EnvelopeInvalidError(f"Malformed result envelope JSON: {e}")
        return cls.from_dict(d, secret_key=secret_key, verify_signature=verify_signature)


# ── High-Level Construction Factories ─────────────────────────────────────────

def create_removal_envelope(
    job: Any,
    member_fields: Optional[Dict[str, Any]] = None,
    request_id: Optional[int] = None,
    request_key: Optional[str] = None,
    secret_key: Optional[Union[str, bytes]] = None,
    priority: str = "normal",
    meta: Optional[Dict[str, Any]] = None,
    ttl_seconds: Optional[int] = 86400,
    encrypt: bool = False,
) -> JobEnvelope:
    """
    Build a JobEnvelope from a compiled Job (or dict).
    """
    job_dict = job.to_dict() if hasattr(job, "to_dict") else dict(job)
    broker_id = job_dict.get("broker_id", "")
    broker_name = job_dict.get("broker_name", "")
    member_id = job_dict.get("member_id", "")

    now = time.time()
    payload = {
        "job": job_dict,
        "member_fields": member_fields or {},
    }

    env = JobEnvelope(
        action="removal",
        broker_id=broker_id,
        broker_name=broker_name,
        member_id=member_id,
        request_id=request_id,
        request_key=request_key,
        priority=priority,
        created_at=now,
        expires_at=(now + ttl_seconds) if ttl_seconds is not None else None,
        payload=payload,
        meta=meta or {},
    )

    if encrypt and secret_key:
        env.encrypt_payload(secret_key)

    if secret_key:
        env.sign(secret_key)

    return env


def create_discovery_envelope(
    query_criteria: Dict[str, Any],
    broker_id: str,
    broker_name: str,
    member_id: str,
    request_id: Optional[int] = None,
    secret_key: Optional[Union[str, bytes]] = None,
    priority: str = "normal",
    meta: Optional[Dict[str, Any]] = None,
    ttl_seconds: Optional[int] = 86400,
    encrypt: bool = False,
) -> JobEnvelope:
    """
    Build a JobEnvelope for a discovery bot search task.
    """
    now = time.time()
    payload = {
        "query": dict(query_criteria),
    }

    env = JobEnvelope(
        action="discovery",
        broker_id=broker_id,
        broker_name=broker_name,
        member_id=member_id,
        request_id=request_id,
        priority=priority,
        created_at=now,
        expires_at=(now + ttl_seconds) if ttl_seconds is not None else None,
        payload=payload,
        meta=meta or {},
    )

    if encrypt and secret_key:
        env.encrypt_payload(secret_key)

    if secret_key:
        env.sign(secret_key)

    return env


def create_result_envelope(
    request_envelope: JobEnvelope,
    ok: bool,
    status: str = "success",
    exec_result: Optional[Any] = None,
    discovery_result: Optional[Dict[str, Any]] = None,
    worker_id: str = "worker-default",
    screenshots: Optional[Dict[str, str]] = None,
    error: Optional[str] = None,
    secret_key: Optional[Union[str, bytes]] = None,
    duration_ms: Optional[int] = None,
) -> JobResultEnvelope:
    """
    Construct a matching JobResultEnvelope for a handled JobEnvelope.
    """
    completed = time.time()
    computed_duration = duration_ms
    if computed_duration is None:
        computed_duration = int((completed - request_envelope.created_at) * 1000)

    result_data = {}
    if request_envelope.action == "removal":
        if exec_result is not None:
            result_data["exec_result"] = (
                exec_result.to_dict() if hasattr(exec_result, "to_dict") else dict(exec_result)
            )
    elif request_envelope.action == "discovery":
        result_data["discovery"] = discovery_result or {}

    res = JobResultEnvelope(
        envelope_id=request_envelope.envelope_id,
        action=request_envelope.action,
        broker_id=request_envelope.broker_id,
        member_id=request_envelope.member_id,
        ok=ok,
        status=status,
        created_at=request_envelope.created_at,
        completed_at=completed,
        duration_ms=computed_duration,
        worker_id=worker_id,
        request_id=request_envelope.request_id,
        request_key=request_envelope.request_key,
        result=result_data,
        screenshots=screenshots or {},
        error=error,
        meta=dict(request_envelope.meta),
    )

    if secret_key:
        res.sign(secret_key)

    return res
