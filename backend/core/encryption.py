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
  Run (in the container): python -m app.core.encryption migrate
  This creates a new encrypted copy using sqlcipher_export().
"""

import os, base64, hashlib, logging, shutil, sys, argparse
from typing import Optional, Dict, Any

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    class InvalidToken(Exception):
        pass

try:
    from sqlalchemy import types
except ImportError:
    class _FakeTypes:
        class TypeDecorator:
            impl = None
            cache_ok = True
        Text = None
    types = _FakeTypes()

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
    Priority: DB_ENCRYPTION_KEY env var → SECRET_KEY env var → None.
    If DISABLE_DB_ENCRYPTION is true, returns None (explicit opt-out).
    Returns raw string (SQLCipher accepts hex or passphrase).
    """
    if os.getenv("DISABLE_DB_ENCRYPTION", "false").lower() in ("true", "1", "yes"):
        return None
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

def extract_sqlite_path(database_url: str) -> Optional[str]:
    """Extract local filesystem path from a sqlite:/// URL."""
    if not database_url or not database_url.startswith("sqlite"):
        return None
    if database_url.startswith("sqlite:////"):
        return "/" + database_url[len("sqlite:////"):].lstrip("/")
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///"): ]
    if database_url.startswith("sqlite://"):
        return database_url[len("sqlite://"): ]
    return None


def is_sqlite_plaintext(db_path: str) -> bool:
    """
    Check if a file is an unencrypted SQLite database.
    Every unencrypted SQLite database starts with the 16-byte magic header:
    b"SQLite format 3\\x00".
    """
    if not db_path or not os.path.isfile(db_path) or os.path.getsize(db_path) < 16:
        return False
    try:
        with open(db_path, "rb") as f:
            header = f.read(16)
        return header == b"SQLite format 3\x00"
    except Exception:
        return False


def create_encrypted_engine(database_url: str, **kwargs):
    """
    Create a SQLAlchemy engine.

    Connection priority:
      1. Structured Postgres config (SSL / client cert / IAM / Kerberos) if enabled
      2. SQLCipher-encrypted SQLite (when DB_ENCRYPTION_KEY or SECRET_KEY set + sqlcipher3 installed)
         - Auto-migrates existing plaintext SQLite databases to SQLCipher in-place with safety backup.
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
        # Plain Postgres URL or encryption explicitly disabled — use standard engine
        pg_kwargs = {"pool_pre_ping": True} if database_url.startswith("postgresql") else {}
        return create_engine(database_url, **{**pg_kwargs, **kwargs})

    # ── Stage 2: SQLCipher-encrypted SQLite ──
    try:
        from sqlcipher3 import dbapi2 as sqlcipher

        # Check if an existing database file is unencrypted SQLite
        db_file = extract_sqlite_path(database_url)
        if db_file and os.path.isfile(db_file) and is_sqlite_plaintext(db_file):
            log.warning(
                "Unencrypted SQLite database detected at %s with SQLCipher enabled. "
                "Automatically migrating to encrypted SQLCipher database...",
                db_file,
            )
            try:
                auto_encrypt_database_inplace(db_file, db_key)
            except Exception as e:
                log.error("Failed to auto-encrypt database %s: %s. Continuing with unencrypted fallback.", db_file, e)
                return create_engine(database_url, connect_args={"check_same_thread": False}, **kwargs)

        engine = create_engine(
            database_url,
            module=sqlcipher,
            connect_args={"check_same_thread": False},
            **kwargs,
        )

        @event.listens_for(engine, "connect")
        def set_sqlcipher_pragma(dbapi_connection, connection_record):
            # Set the encryption key on every new connection
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
            "Install sqlcipher3-binary or build with WITH_ENCRYPTION=true to enable file-level encryption."
        )
        return create_engine(database_url, connect_args={"check_same_thread": False}, **kwargs)


# ── Encryption, Decryption & Rekey Operations ─────────────────────────────────

def encrypt_database(source_path: str, dest_path: str, key: str) -> str:
    """
    Encrypt an existing unencrypted SQLite database using SQLCipher sqlcipher_export().
    """
    try:
        from sqlcipher3 import dbapi2 as sqlcipher
    except ImportError:
        raise RuntimeError("sqlcipher3 not installed — cannot encrypt database")

    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Source database file not found: {source_path}")

    if os.path.exists(dest_path):
        os.remove(dest_path)

    hex_key = hashlib.sha256(key.encode()).hexdigest()

    # Open unencrypted source with sqlcipher
    conn = sqlcipher.connect(source_path)
    cursor = conn.cursor()
    safe_dest = dest_path.replace("'", "''")
    cursor.execute(f"ATTACH DATABASE '{safe_dest}' AS encrypted KEY \"x'{hex_key}'\";")
    cursor.execute("PRAGMA encrypted.cipher_page_size = 4096;")
    cursor.execute("PRAGMA encrypted.kdf_iter = 256000;")
    cursor.execute("PRAGMA encrypted.cipher_hmac_algorithm = HMAC_SHA512;")
    cursor.execute("PRAGMA encrypted.cipher_kdf_algorithm = PBKDF2_HMAC_SHA512;")
    cursor.execute("SELECT sqlcipher_export('encrypted');")
    cursor.execute("DETACH DATABASE encrypted;")
    cursor.close()
    conn.close()

    log.info("Successfully encrypted database: %s → %s", source_path, dest_path)
    return dest_path


def decrypt_database(source_path: str, dest_path: str, key: str) -> str:
    """
    Decrypt an existing SQLCipher database back to standard plaintext SQLite using sqlcipher_export().
    """
    try:
        from sqlcipher3 import dbapi2 as sqlcipher
    except ImportError:
        raise RuntimeError("sqlcipher3 not installed — cannot decrypt database")

    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Source database file not found: {source_path}")

    if os.path.exists(dest_path):
        os.remove(dest_path)

    hex_key = hashlib.sha256(key.encode()).hexdigest()

    conn = sqlcipher.connect(source_path)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA key = \"x'{hex_key}'\";")

    # Verify key works before export
    try:
        cursor.execute("SELECT count(*) FROM sqlite_master;")
        cursor.fetchone()
    except Exception as e:
        cursor.close()
        conn.close()
        raise ValueError(f"Invalid key or database is not encrypted with this key: {e}")

    safe_dest = dest_path.replace("'", "''")
    cursor.execute(f"ATTACH DATABASE '{safe_dest}' AS plaintext KEY '';")
    cursor.execute("SELECT sqlcipher_export('plaintext');")
    cursor.execute("DETACH DATABASE plaintext;")
    cursor.close()
    conn.close()

    log.info("Successfully decrypted database: %s → %s", source_path, dest_path)
    return dest_path


def rekey_database(db_path: str, old_key: str, new_key: str) -> bool:
    """
    Change the encryption passphrase of an existing SQLCipher database in-place.
    """
    try:
        from sqlcipher3 import dbapi2 as sqlcipher
    except ImportError:
        raise RuntimeError("sqlcipher3 not installed — cannot rekey database")

    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")

    backup_path = f"{db_path}.rekey_backup"
    shutil.copy2(db_path, backup_path)

    try:
        hex_old = hashlib.sha256(old_key.encode()).hexdigest()
        hex_new = hashlib.sha256(new_key.encode()).hexdigest()

        conn = sqlcipher.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA key = \"x'{hex_old}'\";")
        cursor.execute("SELECT count(*) FROM sqlite_master;")
        cursor.fetchone()
        cursor.execute(f"PRAGMA rekey = \"x'{hex_new}'\";")
        cursor.close()
        conn.close()

        if os.path.exists(backup_path):
            os.remove(backup_path)
        log.info("Successfully re-keyed database %s", db_path)
        return True
    except Exception as e:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, db_path)
            os.remove(backup_path)
        raise RuntimeError(f"Rekeying failed: {e}")


def auto_encrypt_database_inplace(db_path: str, key: str) -> None:
    """
    Safely encrypt a plaintext SQLite database in place, preserving a .plaintext_backup file.
    """
    backup_path = f"{db_path}.plaintext_backup"
    tmp_encrypted = f"{db_path}.tmp_encrypted"

    log.info("Creating plaintext safety backup at %s", backup_path)
    shutil.copy2(db_path, backup_path)

    try:
        encrypt_database(db_path, tmp_encrypted, key)
        os.replace(tmp_encrypted, db_path)
        log.info("In-place encryption complete for %s. Original saved to %s", db_path, backup_path)
    except Exception as e:
        if os.path.exists(tmp_encrypted):
            os.remove(tmp_encrypted)
        log.error("In-place encryption failed: %s. Preserved original database.", e)
        raise


def decrypt_database_inplace(db_path: str, key: str) -> None:
    """
    Safely decrypt an encrypted SQLCipher database in place, preserving an .encrypted_backup file.
    """
    backup_path = f"{db_path}.encrypted_backup"
    tmp_decrypted = f"{db_path}.tmp_decrypted"

    log.info("Creating encrypted safety backup at %s", backup_path)
    shutil.copy2(db_path, backup_path)

    try:
        decrypt_database(db_path, tmp_decrypted, key)
        os.replace(tmp_decrypted, db_path)
        log.info("In-place decryption complete for %s. Original saved to %s", db_path, backup_path)
    except Exception as e:
        if os.path.exists(tmp_decrypted):
            os.remove(tmp_decrypted)
        log.error("In-place decryption failed: %s. Preserved original database.", e)
        raise


def check_db_encryption_status(db_path: str, key: Optional[str] = None) -> Dict[str, Any]:
    """
    Inspect the encryption posture of a SQLite database file.
    """
    if not os.path.isfile(db_path):
        return {"status": "missing", "path": db_path, "is_encrypted": False, "message": "File does not exist"}

    if os.path.getsize(db_path) == 0:
        return {"status": "empty", "path": db_path, "is_encrypted": False, "message": "Database file is empty"}

    if is_sqlite_plaintext(db_path):
        return {
            "status": "plaintext",
            "path": db_path,
            "is_encrypted": False,
            "message": "Standard unencrypted SQLite database",
        }

    test_key = key or get_db_encryption_key()
    try:
        from sqlcipher3 import dbapi2 as sqlcipher
        if test_key:
            hex_key = hashlib.sha256(test_key.encode()).hexdigest()
            conn = sqlcipher.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA key = \"x'{hex_key}'\";")
            cursor.execute("SELECT count(*) FROM sqlite_master;")
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return {
                "status": "encrypted",
                "path": db_path,
                "is_encrypted": True,
                "key_valid": True,
                "tables_count": count,
                "message": "SQLCipher AES-256 encrypted database (key verified)",
            }
        else:
            return {
                "status": "encrypted_locked",
                "path": db_path,
                "is_encrypted": True,
                "key_valid": False,
                "message": "Database is encrypted (no encryption key provided to open it)",
            }
    except ImportError:
        return {
            "status": "encrypted_unsupported",
            "path": db_path,
            "is_encrypted": True,
            "message": "Database is encrypted, but sqlcipher3 is not installed on this system",
        }
    except Exception as e:
        return {
            "status": "encrypted_invalid_key",
            "path": db_path,
            "is_encrypted": True,
            "key_valid": False,
            "message": f"Database is encrypted and provided key failed: {e}",
        }


# Backwards compatibility alias
migrate_to_encrypted = encrypt_database


# ── CLI Entrypoint ────────────────────────────────────────────────────────────

def cli_main():
    default_db = extract_sqlite_path(os.getenv("DATABASE_URL", "sqlite:///./privacy_pipeline.db")) or "./privacy_pipeline.db"

    parser = argparse.ArgumentParser(description="OpenOptOut SQLite / SQLCipher Database Encryption Tool")
    subparsers = parser.add_subparsers(dest="command")

    # status
    p_status = subparsers.add_parser("status", help="Check database encryption posture")
    p_status.add_argument("path", nargs="?", default=default_db, help="Path to SQLite database file")
    p_status.add_argument("--key", default=None, help="Passphrase to test (defaults to DB_ENCRYPTION_KEY/SECRET_KEY)")

    # encrypt
    p_enc = subparsers.add_parser("encrypt", help="Encrypt a plaintext SQLite database with SQLCipher")
    p_enc.add_argument("path", nargs="?", default=default_db, help="Source database file")
    p_enc.add_argument("dest", nargs="?", default=None, help="Destination database file (omitted if --inplace)")
    p_enc.add_argument("--key", default=None, help="Encryption passphrase")
    p_enc.add_argument("--inplace", action="store_true", help="Encrypt in place (creates .plaintext_backup)")

    # decrypt
    p_dec = subparsers.add_parser("decrypt", help="Decrypt an encrypted SQLCipher database to plaintext SQLite")
    p_dec.add_argument("path", nargs="?", default=default_db, help="Encrypted database file")
    p_dec.add_argument("dest", nargs="?", default=None, help="Destination plaintext file (omitted if --inplace)")
    p_dec.add_argument("--key", default=None, help="Current encryption passphrase")
    p_dec.add_argument("--inplace", action="store_true", help="Decrypt in place (creates .encrypted_backup)")

    # rekey
    p_rekey = subparsers.add_parser("rekey", help="Change the passphrase of an encrypted SQLCipher database")
    p_rekey.add_argument("path", nargs="?", default=default_db, help="Database file")
    p_rekey.add_argument("--old-key", required=True, help="Current passphrase")
    p_rekey.add_argument("--new-key", required=True, help="New passphrase")

    # migrate (legacy alias)
    p_mig = subparsers.add_parser("migrate", help="Legacy alias to encrypt existing database")
    p_mig.add_argument("path", nargs="?", default=default_db)
    p_mig.add_argument("dest", nargs="?", default=None)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmd = args.command
    if cmd == "status":
        info = check_db_encryption_status(args.path, key=args.key)
        print(f"\nDatabase: {info['path']}")
        print(f"Status:   {info['status']}")
        print(f"Details:  {info['message']}")
        sys.exit(0)

    key = getattr(args, "key", None) or get_db_encryption_key()

    if cmd in ("encrypt", "migrate"):
        if not key:
            print("ERROR: Encryption key not provided. Set DB_ENCRYPTION_KEY / SECRET_KEY or pass --key.", file=sys.stderr)
            sys.exit(1)
        if getattr(args, "inplace", False) or not args.dest:
            if not getattr(args, "inplace", False) and not args.dest:
                print(f"Encrypting {args.path} in place...")
            auto_encrypt_database_inplace(args.path, key)
            print(f"Success! {args.path} is now AES-256 encrypted with SQLCipher.")
        else:
            encrypt_database(args.path, args.dest, key)
            print(f"Success! Encrypted copy created at {args.dest}.")

    elif cmd == "decrypt":
        if not key:
            print("ERROR: Encryption key not provided. Set DB_ENCRYPTION_KEY / SECRET_KEY or pass --key.", file=sys.stderr)
            sys.exit(1)
        if getattr(args, "inplace", False) or not args.dest:
            if not getattr(args, "inplace", False) and not args.dest:
                print(f"Decrypting {args.path} in place...")
            decrypt_database_inplace(args.path, key)
            print(f"Success! {args.path} is now unencrypted standard SQLite.")
        else:
            decrypt_database(args.path, args.dest, key)
            print(f"Success! Decrypted copy created at {args.dest}.")

    elif cmd == "rekey":
        rekey_database(args.path, args.old_key, args.new_key)
        print(f"Success! Passphrase for {args.path} has been changed.")


if __name__ == "__main__":
    cli_main()
