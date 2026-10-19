"""
A small, bundled list of extremely common/breached passwords, checked at
password-set time so a password protecting other people's personal data
can't literally be "password123" or "qwerty12345". Deliberately not calling
out to an external breach database (k-anonymity or otherwise): this app
runs self-hosted, offline-by-design, and a basic common-password check is
squarely something it can do without a network dependency or sending even
a partial hash of anyone's password off the box.

This is a small, curated set of passwords known (from public breach-corpus
reporting) to be among the most commonly chosen — not an attempt at a full
rockyou-sized corpus. It exists to catch the overwhelmingly common case (a
bare dictionary word, keyboard-walk, or "word+digits" pattern), not to
score password strength in general; that's a much bigger dependency
(zxcvbn and similar) than this check is trying to be.
"""
import re

COMMON_PASSWORDS = frozenset({
    "password", "123456", "123456789", "12345678", "12345", "1234567890",
    "qwerty", "qwerty123", "qwertyuiop", "abc123", "111111", "123123",
    "admin", "administrator", "letmein", "welcome", "welcome1", "monkey",
    "dragon", "football", "baseball", "basketball", "iloveyou", "trustno1",
    "sunshine", "princess", "flower", "superman", "batman", "master",
    "shadow", "michael", "jennifer", "jordan", "hunter", "ranger", "soccer",
    "hockey", "killer", "george", "charlie", "andrew", "michelle",
    "starwars", "whatever", "freedom", "ginger", "nicole", "chelsea",
    "biteme", "matthew", "access", "yankees", "dallas", "austin",
    "thunder", "taylor", "matrix", "monitor", "monster", "cookie",
    "secret", "summer", "internet", "service", "canada", "hello",
    "test123", "qazwsx", "passw0rd", "p@ssw0rd", "p@ssword", "password1",
    "password123", "password1234", "letmein123", "changeme", "changeme123",
    "default", "guest", "root", "toor", "123qwe", "qwe123", "asdfghjkl",
    "zxcvbnm", "1q2w3e4r", "1qaz2wsx", "aaaaaaaa", "11111111", "00000000",
    "87654321", "123321", "696969", "qwerty1", "qwerty12", "qwerty1234",
    "iloveyou1", "loveme", "football1", "baseball1", "login", "letmein1",
    "welcome123", "abcd1234", "a1b2c3d4", "temp1234", "temppass",
    "changethis", "opensesame", "correcthorsebatterystaple",
})


def _normalize(password: str) -> str:
    return (password or "").strip().lower()


def is_common_password(password: str) -> bool:
    """True if `password` is one of a small set of extremely common/breached
    passwords, or that same word with trailing digits/punctuation stripped
    (catches "password123", "qwerty!!", etc. — the overwhelmingly common
    way people "strengthen" an otherwise-weak base word)."""
    norm = _normalize(password)
    if not norm:
        return False
    if norm in COMMON_PASSWORDS:
        return True
    stripped = re.sub(r"[\d!@#$%^&*._-]+$", "", norm)
    return bool(stripped) and stripped != norm and stripped in COMMON_PASSWORDS
