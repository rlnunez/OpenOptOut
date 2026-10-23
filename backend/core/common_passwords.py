"""
A bundled list of extremely common/breached passwords, checked at
password-set time so a password protecting other people's personal data
can't literally be "password123" or "qwerty12345". Deliberately not calling
out to an external breach database (k-anonymity or otherwise): this app
runs self-hosted, offline-by-design, and a basic common-password check is
squarely something it can do without a network dependency or sending even
a partial hash of anyone's password off the box.

Two lists, both checked by is_common_password():
  - COMMON_PASSWORDS_WORDLIST: a ~10,000-entry public-domain common-password
    corpus (common_passwords_wordlist.txt, one entry per line, sourced from
    public breach-corpus research — SecLists' 10k-most-common.txt, itself
    derived from the 2009 RockYou breach research published by Mark Burnett).
    Past ASVS's "top 3000" floor (6.2.4/6.2.12-adjacent); not an attempt at a
    full rockyou-sized corpus or a password-strength scorer (that's a much
    bigger dependency — zxcvbn and similar — than this check is trying to be).
  - CONTEXT_SPECIFIC_WORDS: this deployment's own names/terms (ASVS 6.1.2/
    6.2.11 — "a list of context-specific words ... permutations of
    organization names, product names, ... department or role names").
    Documented here rather than in a separate file since it's short and
    specific to this one product.
"""
import os
import re

CONTEXT_SPECIFIC_WORDS = frozenset({
    "openoptout", "privacyshield", "privacy-shield", "optout", "opt-out",
    "admin", "administrator", "superadmin", "super-admin", "libraryadmin",
    "library", "librarian", "patron", "broker", "databroker", "member",
    "family", "parent", "guardian",
})


def _load_wordlist() -> frozenset:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "common_passwords_wordlist.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return frozenset(line.strip().lower() for line in f if line.strip())
    except OSError:
        return frozenset()


COMMON_PASSWORDS_WORDLIST = _load_wordlist()

# Kept as a fallback/overlay: a few extras not necessarily in the bundled
# corpus (e.g. this app's own default-ish strings), still checked even if the
# wordlist file is ever missing.
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
    """True if `password` is one of the bundled common/breached passwords or
    this deployment's context-specific words, or that same word with trailing
    digits/punctuation stripped (catches "password123", "qwerty!!", etc. —
    the overwhelmingly common way people "strengthen" an otherwise-weak base
    word, or turn a short blocked word into a 12+ character one)."""
    norm = _normalize(password)
    if not norm:
        return False
    if norm in COMMON_PASSWORDS or norm in COMMON_PASSWORDS_WORDLIST or norm in CONTEXT_SPECIFIC_WORDS:
        return True
    stripped = re.sub(r"[\d!@#$%^&*._-]+$", "", norm)
    return bool(stripped) and stripped != norm and (
        stripped in COMMON_PASSWORDS or stripped in COMMON_PASSWORDS_WORDLIST
        or stripped in CONTEXT_SPECIFIC_WORDS)
