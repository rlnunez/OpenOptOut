"""
Thin helpers used by scheduler.py to read settings and decrypt passwords
without importing the full FastAPI router (avoids circular imports).
"""

import json, os, base64
from cryptography.fernet import Fernet

SETTINGS_FILE = os.getenv("SETTINGS_FILE", "./privacyshield_settings.json")


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    with open(SETTINGS_FILE) as f:
        return json.load(f)


def _fernet() -> Fernet:
    raw    = os.getenv("SECRET_KEY", "change-me-in-production-use-a-long-random-string")
    padded = (raw * 4)[:32].encode()
    return Fernet(base64.urlsafe_b64encode(padded))


def decrypt_password(enc: str) -> str:
    try:
        return _fernet().decrypt(enc.encode()).decode()
    except Exception:
        return ""
