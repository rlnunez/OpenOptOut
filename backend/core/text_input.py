"""Cleaning for people's names typed into the app or sent by a sign-in provider.

Names are stored and shown to other people (admins, parents, managers), and
they are copied into opt-out requests sent to data brokers. A name can legally
contain almost anything, so this module is deliberately permissive about what
it ACCEPTS (accents, non-Latin scripts, apostrophes, hyphens, emoji) and strict
only about things that are never part of a real name:

  * control characters (NUL, backspace, escape, ...) — PostgreSQL rejects a
    string containing NUL outright, which turned a sign-up into a server
    error; the others can corrupt logs, CSV exports and email headers
  * right-to-left / left-to-right override characters — they make text
    display in a different order than it is stored, so "Bob<RLO>evil" can
    be shown to an admin as something it isn't
  * lone surrogates — not valid text; they cannot be encoded as UTF-8 and
    crash anything that tries
  * unlimited length — a name is capped at MAX_NAME_CHARS

Note: SQL injection is not this module's job. Every database query goes
through SQLAlchemy with bound parameters, so a name like
"Robert'); DROP TABLE users;--" is stored as an ordinary (odd) name. Nothing
here strips quotes or SQL words, because real names contain apostrophes.

Pure standard library on purpose: the fuzz target in fuzz/ imports it with no
third-party packages installed.
"""
import unicodedata
from typing import Optional

# Generous for any real name (the longest legal names on record are well under
# this), matches the limit already used for family members (MemberCreate).
MAX_NAME_CHARS = 200

# Unicode "bidi" formatting characters that reorder how text is displayed.
# Written as \u escapes so static scanners (Bandit / CodeQL Trojan-Source check)
# never see raw bidirectional control characters in the source file.
_BIDI_CONTROLS = frozenset(
    "\u061c"                             # Arabic letter mark
    "\u200e\u200f"                       # LTR / RTL marks
    "\u202a\u202b\u202c\u202d\u202e"     # embeddings / overrides / pop
    "\u2066\u2067\u2068\u2069"           # isolates
)


def _clean(value: str) -> str:
    """Normalize, drop characters that are never part of a name, and tidy
    whitespace. Never raises. Keeps zero-width joiners (U+200D): emoji like
    family and flag sequences need them.

    Characters are filtered BEFORE normalizing: a dropped character between a
    letter and its accent ("e<NUL>\u0301") would otherwise leave them
    uncombined until a second pass, making the result depend on how many
    times it was cleaned."""
    out = []
    for ch in value:
        cat = unicodedata.category(ch)
        if cat == "Cc":                      # control characters, incl. NUL / tab / newline
            out.append(" " if ch in "\t\n\r\x0b\x0c" else "")
        elif cat == "Cs":                    # lone surrogates
            continue
        elif ch in _BIDI_CONTROLS or ch == "\ufeff":   # reordering marks, byte-order mark
            continue
        elif cat == "Zs" or ch in "\u2028\u2029":      # every kind of space / line break
            out.append(" ")
        else:
            out.append(ch)
    value = unicodedata.normalize("NFC", "".join(out))
    return " ".join(value.split())           # collapse runs of spaces, trim ends


def clean_text(value: Optional[str], *, required: bool = True, label: str = "Value",
               max_chars: Optional[int] = None) -> Optional[str]:
    """Validate free text typed into the app, or taken from an external
    sign-in/library system, that isn't necessarily a person's name — an
    address, phone number, or email address identifying a family member.
    Same cleaning as clean_name (control characters, bidi overrides, lone
    surrogates), for use as a pydantic field_validator or called directly.

    This text is stored and later copied, unescaped, into opt-out emails and
    letters sent to data brokers (see core.optout_engine.render_template) —
    an embedded \\r or \\n here can't forge another mail header (the stdlib
    email package itself rejects that at send time), but it can silently
    break that one send, or throw off anything else that renders the value
    as a single line (logs, CSV exports). Stripped here instead, so a typo
    or a copy-paste artifact fails as a clear form error, not as a mystery
    downstream.

    required=True  — the cleaned text must not be empty.
    required=False — None and "" pass through unchanged (an optional field,
                     or "" meaning "clear this value").
    max_chars=None — no length cap of its own; callers that already cap
                     length elsewhere (e.g. LimitedModel's TEXT_MAX) can
                     leave this unset."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    cleaned = _clean(value)
    if not cleaned:
        if required:
            raise ValueError(f"Please enter a {label.lower()}.")
        return ""
    if max_chars is not None and len(cleaned) > max_chars:
        raise ValueError(
            f"{label} is too long ({len(cleaned)} characters). "
            f"Please keep it to {max_chars} characters or fewer."
        )
    return cleaned


def clean_name(value: Optional[str], *, required: bool = True,
               label: str = "Name") -> Optional[str]:
    """Validate a name a person typed. For use as a pydantic field_validator:
    a ValueError becomes a clean 422 with this plain-English message.

    required=True  — the cleaned name must not be empty.
    required=False — None and "" pass through unchanged (an optional field,
                     or "" meaning "clear this value")."""
    return clean_text(value, required=required, label=label, max_chars=MAX_NAME_CHARS)


def clean_name_lenient(value: Optional[str], fallback: str = "") -> str:
    """Clean a name that came from somewhere the person can't easily fix — a
    sign-in provider (Google, SAML, LDAP) or a library system. Never raises:
    an over-long name is shortened instead of blocking the sign-in, and an
    empty result falls back to `fallback` (usually the email address)."""
    cleaned = _clean(value) if isinstance(value, str) else ""
    if len(cleaned) > MAX_NAME_CHARS:
        cleaned = cleaned[:MAX_NAME_CHARS].rstrip()
    if not cleaned and fallback:
        cleaned = _clean(fallback)[:MAX_NAME_CHARS].rstrip()
    return cleaned


def clean_text_lenient(value: Optional[str], max_chars: int = 4000) -> str:
    """Clean an address, phone number, or email address that came from
    somewhere the person can't easily fix — a sign-in provider's demographic
    attributes, or a library ILS's patron record. Never raises: an over-long
    value is shortened instead of blocking the sign-in or import."""
    cleaned = _clean(value) if isinstance(value, str) else ""
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip()
    return cleaned
