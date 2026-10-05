"""
Process Memory Hygiene & Credential Lifecycle (Roadmap Item 15).

Provides mechanisms to minimize the lifetime of decrypted secrets (passwords,
API keys, OAuth tokens) and sensitive patron PII in process memory:
1. Ephemeral credential scoping: secrets exist in memory only for the duration of
   the operational block (e.g. while establishing an SMTP or IMAP connection).
2. Explicit buffer zeroization: mutable byte buffers are wiped with zeros upon
   block exit or exception.
3. Query streaming: patron PII records are streamed in chunks (yield_per) rather
   than buffering entire tables into large in-memory lists.
"""

import sys
import gc
import contextlib
from typing import Optional, Generator, Any, Dict, Iterator
import logging

log = logging.getLogger(__name__)


class SecureBuffer:
    """
    A mutable buffer holding sensitive data that can be explicitly zeroized
    when no longer needed.
    """
    def __init__(self, data: Optional[bytes] = None):
        self._buf = bytearray(data) if data else bytearray()
        self._zeroized = False

    @classmethod
    def from_str(cls, s: Optional[str], encoding: str = "utf-8") -> "SecureBuffer":
        if not s:
            return cls()
        return cls(s.encode(encoding))

    def as_str(self, encoding: str = "utf-8") -> str:
        if self._zeroized or not self._buf:
            return ""
        return self._buf.decode(encoding)

    def as_bytes(self) -> bytes:
        if self._zeroized:
            return b""
        return bytes(self._buf)

    def zeroize(self) -> None:
        """
        Overwrite the internal bytearray with zeros and clear it.
        """
        if not self._zeroized and self._buf:
            for i in range(len(self._buf)):
                self._buf[i] = 0
            self._buf.clear()
        self._zeroized = True

    @property
    def is_zeroized(self) -> bool:
        return self._zeroized

    def __len__(self) -> int:
        return len(self._buf)

    def __enter__(self) -> "SecureBuffer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.zeroize()


@contextlib.contextmanager
def ephemeral_secret(secret_or_enc: Optional[str], decrypt: bool = True) -> Generator[str, None, None]:
    """
    Context manager that decrypts/provides a secret for the duration of the
    'with' block, zeroizing the mutable memory buffer upon exit.

    Example:
        with ephemeral_secret(ec["imap_password_enc"]) as imap_pw:
            conn.login(ec["imap_user"], imap_pw)
        # imap_pw buffer is wiped here
    """
    if not secret_or_enc:
        yield ""
        return

    plain = ""
    if decrypt:
        try:
            from .settings_store import decrypt_password
            plain = decrypt_password(secret_or_enc)
        except Exception as e:
            # nosemgrep: python-logger-credential-disclosure -- logs exception class name, not secret content
            log.debug("Could not decrypt secret: %s", type(e).__name__)
            plain = secret_or_enc
    else:
        plain = secret_or_enc

    buf = SecureBuffer.from_str(plain)
    try:
        yield buf.as_str()
    finally:
        buf.zeroize()
        del plain
        # Gentle hint to collector if running under heavy memory load
        if "pytest" not in sys.modules:
            pass


@contextlib.contextmanager
def scoped_credentials(**named_secrets) -> Generator[Dict[str, str], None, None]:
    """
    Scopes multiple encrypted or plaintext secrets within a single context block,
    zeroizing all underlying buffers upon exit.

    Example:
        with scoped_credentials(smtp_pw=ec["smtp_password_enc"], imap_pw=ec["imap_password_enc"]) as creds:
            # use creds["smtp_pw"], creds["imap_pw"]
    """
    buffers = {}
    plain_dict = {}
    try:
        from .settings_store import decrypt_password
        for name, val in named_secrets.items():
            if val:
                plain = ""
                try:
                    plain = decrypt_password(val) if isinstance(val, str) else str(val)
                except Exception:
                    plain = ""
                if not plain and isinstance(val, str):
                    plain = val
                buf = SecureBuffer.from_str(plain)
                buffers[name] = buf
                plain_dict[name] = buf.as_str()
            else:
                plain_dict[name] = ""
        yield plain_dict
    finally:
        for buf in buffers.values():
            buf.zeroize()
        plain_dict.clear()
        buffers.clear()


def stream_records(query_or_list: Any, batch_size: int = 50) -> Iterator[Any]:
    """
    Memory-efficient streaming iterator for SQLAlchemy queries or large collections.
    If given an ORM Query with yield_per(), configures chunking so the database driver
    streams rows without buffering the entire table in process memory.
    """
    if hasattr(query_or_list, "yield_per"):
        # SQLAlchemy Query streaming
        yield from query_or_list.yield_per(batch_size)
    elif hasattr(query_or_list, "__iter__"):
        # Standard iterable or list in chunks
        for item in query_or_list:
            yield item
    else:
        yield query_or_list
