"""
Two-layer database encryption:

Layer 1 — SQLCipher (file level):
  The entire SQLite database file is AES-256 encrypted.
  Activated when DB_ENCRYPTION_KEY env var is set.
  Falls back to plain SQLite if sqlcipher3 is not installed.

Layer 2 — Field level (application level):
  Sensitive PII columns are Fernet-encrypted before writing to the DB.
  This protects against SQL injection and unauthorized DB read access
  even when the file-level encryption key is known.
  Activated when FIELD_ENCRYPTION_KEY env var is set (defaults to SECRET_KEY).

Encrypted fields:
  Identity.value         — names, addresses, phones, emails
  FamilyMember.formal_name — legal name on deeds
  User.email             — stored encrypted; looked up via SHA-256 hash index

Migration from unencrypted to SQLCipher:
  Run: python -m privacyshield.core.encryption migrate
  This creates a new encrypted copy using sqlcipher_export().
"""

import os, base64, hashlib, logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import types

log = logging.getLogger(__name__)

# ── Key derivation ────────────────────────────────────────────────────────────

def _derive_fernet_key(raw: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary string via SHA-256."""
    digest = hashlib.sha256(raw.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def get_field_encryption_key() -> Optional[bytes]:
    """
    Return the Fernet key used for field-level encryption.
    Priority: FIELD_ENCRYPTION_KEY env var → SECRET_KEY env var → None (disabled).
    """
    raw = os.getenv("FIELD_ENCRYPTION_KEY") or os.getenv("SECRET_KEY")
    if not raw or raw == "change-me-in-production-use-a-long-random-string":
        return None
    return _derive_fernet_key(raw)


def get_db_encryption_key() -> Optional[str]:
    """
    Return the SQLCipher passphrase.
    Priority: DB_ENCRYPTION_KEY env var → SECRET_KEY env var → None (disabled).
    Returns raw string (SQLCipher accepts hex or passphrase).
    """
    return os.getenv("DB_ENCRYPTION_KEY") or os.getenv("SECRET_KEY") or None


# ── Fernet helpers ────────────────────────────────────────────────────────────

_fernet_instance: Optional[Fernet] = None


def _get_fernet() -> Optional[Fernet]:
    global _fernet_instance
    if _fernet_instance is None:
        key = get_field_encryption_key()
        if key:
            _fernet_instance = Fernet(key)
    return _fernet_instance


def encrypt_field(value: Optional[str]) -> Optional[str]:
    """Encrypt a string field value. Returns None if value is None."""
    if value is None:
        return None
    f = _get_fernet()
    if f is None:
        return value   # encryption disabled — store plaintext
    return f.encrypt(value.encode()).decode()


def decrypt_field(value: Optional[str]) -> Optional[str]:
    """Decrypt a field value. Returns plaintext if not encrypted (graceful degradation)."""
    if value is None:
        return None
    f = _get_fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        # Value was stored before encryption was enabled — return as-is
        return value


def hash_for_index(value: str) -> str:
    """
    SHA-256 hash of a value for use as a searchable index.
    Emails are stored encrypted but looked up via their hash.
    """
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()


# ── SQLAlchemy TypeDecorator for transparent field encryption ─────────────────

class EncryptedString(types.TypeDecorator):
    """
    Drop-in replacement for String/Text that transparently encrypts on write
    and decrypts on read. Use exactly like Column(String).

    Example:
        value = Column(EncryptedText)
    """
    impl            = types.Text
    cache_ok        = True

    def process_bind_param(self, value, dialect):
        """Called before writing to DB — encrypt."""
        return encrypt_field(value)

    def process_result_value(self, value, dialect):
        """Called after reading from DB — decrypt."""
        return decrypt_field(value)


EncryptedText = EncryptedString   # alias


# ── SQLCipher engine factory ──────────────────────────────────────────────────

def create_encrypted_engine(database_url: str, **kwargs):
    """
    Create a SQLAlchemy engine.

    Connection priority:
      1. Structured Postgres config (SSL / client cert / IAM / Kerberos) if enabled
      2. SQLCipher-encrypted SQLite (when DB_ENCRYPTION_KEY set + sqlcipher3 installed)
      3. Plain DATABASE_URL (SQLite or Postgres)

    Falls back gracefully at each stage.
    """
    from sqlalchemy import create_engine, event

    # ── Stage 1: structured enterprise Postgres connection ──
    try:
        from .db_connection import build_postgres_connection
        structured = build_postgres_connection()
        if structured:
            url, connect_args = structured
            log.info("Using structured PostgreSQL connection (enterprise auth)")
            return create_engine(
                url,
                connect_args=connect_args,
                pool_pre_ping=True,
                pool_recycle=1800,   # recycle connections every 30 min (IAM tokens expire)
                **kwargs,
            )
    except Exception as e:
        log.warning(f"Structured Postgres config not used: {e}")

    db_key = get_db_encryption_key()

    if not database_url.startswith("sqlite") or not db_key:
        # Plain Postgres URL or encryption disabled — use standard engine
        pg_kwargs = {"pool_pre_ping": True} if database_url.startswith("postgresql") else {}
        return create_engine(database_url, **{**pg_kwargs, **kwargs})

    try:
        from sqlcipher3 import dbapi2 as sqlcipher

        engine = create_engine(
            database_url,
            module=sqlcipher,
            connect_args={"check_same_thread": False},
            **kwargs,
        )

        @event.listens_for(engine, "connect")
        def set_sqlcipher_pragma(dbapi_connection, connection_record):
            # Set the encryption key on every new connection
            # Use hex key format for deterministic key derivation
            hex_key = hashlib.sha256(db_key.encode()).hexdigest()
            cursor = dbapi_connection.cursor()
            cursor.execute(f"PRAGMA key = \"x'{hex_key}'\"")
            # Use SQLCipher 4 defaults (AES-256-CBC, PBKDF2-HMAC-SHA512)
            cursor.execute("PRAGMA cipher_page_size = 4096")
            cursor.execute("PRAGMA kdf_iter = 256000")
            cursor.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
            cursor.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512")
            cursor.close()

        log.info("SQLCipher encryption enabled for SQLite database")
        return engine

    except ImportError:
        log.warning(
            "sqlcipher3 not installed — falling back to unencrypted SQLite. "
            "Install sqlcipher3-binary to enable file-level encryption."
        )
        return create_engine(database_url, connect_args={"check_same_thread": False}, **kwargs)


# ── Migration: plain SQLite → SQLCipher ──────────────────────────────────────

def migrate_to_encrypted(source_path: str, dest_path: str, key: str):
    """
    Migrate an existing unencrypted SQLite database to SQLCipher.

    Usage:
        from privacyshield.core.encryption import migrate_to_encrypted
        migrate_to_encrypted(
            "/data/privacy_pipeline.db",
            "/data/privacy_pipeline_encrypted.db",
            os.getenv("DB_ENCRYPTION_KEY"),
        )

    After migration:
        1. Stop the server
        2. Back up the original .db file
        3. Replace it with the encrypted version
        4. Set DB_ENCRYPTION_KEY in your .env
        5. Restart
    """
    import sqlite3

    try:
        from sqlcipher3 import dbapi2 as sqlcipher
    except ImportError:
        raise RuntimeError("sqlcipher3 not installed — cannot migrate")

    hex_key = hashlib.sha256(key.encode()).hexdigest()

    # Open the source (unencrypted)
    source_conn = sqlite3.connect(source_path)

    # Open the destination (encrypted)
    dest_conn = sqlcipher.connect(dest_path)
    dest_cursor = dest_conn.cursor()
    dest_cursor.execute(f"PRAGMA key = \"x'{hex_key}'\"")
    dest_cursor.execute("PRAGMA cipher_page_size = 4096")
    dest_cursor.execute("PRAGMA kdf_iter = 256000")
    dest_cursor.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
    dest_cursor.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512")
    dest_cursor.close()

    # Use SQLite's built-in backup API to copy all data
    source_conn.backup(dest_conn)
    source_conn.close()
    dest_conn.close()

    log.info(f"Migration complete: {source_path} → {dest_path}")
    return dest_path


# ── CLI helper ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "migrate":
        src  = os.getenv("DATABASE_URL", "sqlite:///./privacy_pipeline.db").replace("sqlite:///","")
        key  = get_db_encryption_key()
        if not key:
            print("ERROR: DB_ENCRYPTION_KEY not set"); sys.exit(1)
        dest = src.replace(".db", "_encrypted.db")
        print(f"Migrating {src} → {dest} ...")
        migrate_to_encrypted(src, dest, key)
        print(f"Done. Review {dest}, then replace the original and restart with DB_ENCRYPTION_KEY set.")
    else:
        print("Usage: python -m privacyshield.core.encryption migrate")
