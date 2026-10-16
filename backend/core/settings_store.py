"""
Thin helpers used by scheduler.py to read settings and decrypt passwords
without importing the full FastAPI router (avoids circular imports).
"""

import json, os, base64
try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None

_DEFAULT_SETTINGS_FILE = "./openoptout_settings.json"
_LEGACY_SETTINGS_FILE = "./privacyshield_settings.json"
SETTINGS_FILE = os.getenv("SETTINGS_FILE") or (
    _LEGACY_SETTINGS_FILE if os.path.exists(_LEGACY_SETTINGS_FILE) and not os.path.exists(_DEFAULT_SETTINGS_FILE) else _DEFAULT_SETTINGS_FILE
)


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    with open(SETTINGS_FILE) as f:
        return json.load(f)


def save_settings(data: dict) -> None:
    """Atomically write settings JSON to disk using a temporary file."""
    import tempfile
    dir_name = os.path.dirname(os.path.abspath(SETTINGS_FILE))
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="settings_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, SETTINGS_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


# Values published in this project's own files. A server using one of these
# is as good as keyless: anyone can forge sign-ins and decrypt stored secrets.
PUBLIC_PLACEHOLDER_KEYS = frozenset({
    "change-me-in-production-use-a-long-random-string",
    "change-me-to-a-long-random-string",
    "change-me-please",
    "change-me-please-32-chars-minimum",
    "change-me",
})


def insecure_secret_key_reason() -> str:
    """Why the configured SECRET_KEY is unsafe, or "" if it's fine."""
    key = os.getenv("SECRET_KEY", "")
    if not key.strip():
        return "SECRET_KEY is not set."
    if key.strip() in PUBLIC_PLACEHOLDER_KEYS:
        return "SECRET_KEY is still the example value from this project's files."
    return ""


def get_secret_key() -> str:
    key = os.getenv("SECRET_KEY")
    if not key:
        return "change-me-in-production-use-a-long-random-string"
    return key


def _fernet():
    if Fernet is None:
        raise RuntimeError("cryptography package is required for password encryption")
    raw    = get_secret_key()
    # Repeat the key until it fills 32 bytes. Identical to the old
    # `(raw * 4)[:32]` for keys of 8+ chars (existing data still decrypts),
    # but no longer crashes on a shorter SECRET_KEY.
    _kb = raw.encode() or b"\0"
    padded = (_kb * (32 // len(_kb) + 1))[:32]
    return Fernet(base64.urlsafe_b64encode(padded))


def encrypt_password(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_password(enc: str) -> str:
    try:
        return _fernet().decrypt(enc.encode()).decode()
    except Exception:
        return ""
