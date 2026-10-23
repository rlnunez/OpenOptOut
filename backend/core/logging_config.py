"""
Operational visibility & diagnostic logging infrastructure.

Provides:
- Persistent rotating log file (default /data/logs/openoptout.log, configurable via LOGS_DIR)
- In-memory ring buffer (default 2,000 entries) for fast in-app filtering and live streaming
- Automatic PII and credential sanitization (Bearer tokens, SIP2 credentials, passwords, secrets)
- Dynamic runtime log verbosity management (DEBUG, INFO, WARNING, ERROR)
"""

import collections
import datetime
import glob
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import threading
from typing import List, Optional, Dict, Any

# ── Paths & Defaults ──────────────────────────────────────────────────────────

DEFAULT_CAPACITY = 2000
MAX_QUERY_LIMIT  = 1000

# Base directory for log files
if os.path.exists("/data"):
    LOGS_DIR = os.getenv("LOGS_DIR", "/data/logs")
else:
    LOGS_DIR = os.getenv(
        "LOGS_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"),
    )

LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", os.path.join(LOGS_DIR, "openoptout.log"))

# Standard log format
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

VALID_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


# ── Sanitization Patterns ────────────────────────────────────────────────────

_RE_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-_=.]+", re.IGNORECASE)

# key=value, key: value, "key": "value" and 'key': 'value' for any key that has
# a secret-ish word as one of its dash/underscore-separated parts, so
# access_token, refresh_token, X-API-Key, session_id, Set-Cookie and
# client_secret are all caught, not only a bare "token". The value keeps its
# quote marks so JSON-looking lines stay readable.
_SECRET_WORDS = (
    r"password|passwd|passphrase|pin|secret|token|api[-_]?key|apikey|credentials?|"
    r"cookie|session(?:[-_]?id)?|signature|private[-_]?key"
)
# The dash/underscore-separated-word prefix/suffix (e.g. "my_app_client_secret")
# used to be (?:[a-z0-9]+[_-])*/(?:[_-][a-z0-9]+)* — an unbounded quantifier
# nested inside another unbounded quantifier. Scanned unanchored across a log
# line with no matching secret word, that backtracks catastrophically: ~1s for
# a 4,000-character input, growing quadratically (ASVS 1.3.12 ReDoS). Bounding
# both the inner word length and the repetition count removes the blowup
# (worst case becomes a small constant per scan position) while still matching
# every realistic key name.
_RE_KV_SECRETS = re.compile(
    r"(?i)(\b(?:[a-z0-9]{1,20}[_-]){0,4}(?:" + _SECRET_WORDS + r")(?:[_-][a-z0-9]{1,20}){0,4}[\"']?\s*[=:]\s*)"
    r"(?!\[REDACTED)(\"[^\"]*\"|'[^']*'|[^&\s,;}\]]+)"
)

# Personal details that come with a label: first_name=..., dob: 1990-01-01
_RE_KV_PERSONAL = re.compile(
    r"(?i)(\b(?:first|last|middle|full|maiden|given|family)[_ -]?name|surname|"
    r"dob|date[_ -]?of[_ -]?birth|birth[_ -]?date|birthday)([\"']?\s*[=:]\s*)"
    r"(?!\[)(\"[^\"]*\"|'[^']*'|[^&\s,;}\]]+)"
)

# Secrets that sit in a URL: the query string and the password part of
# scheme://user:password@host. OIDC/OAuth callbacks put a one-time code and a
# state in the query; both are credentials while they're live.
_RE_URL_QUERY_SECRETS = re.compile(
    r"(?i)([?&](?:code|state|id_token|access_token|refresh_token|samlresponse|relaystate|"
    r"sig|signature|key|sid)=)[^&\s\"']+"
)
_RE_URL_CREDENTIALS = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^/\s:@]*:)[^@\s/]+@")
# The calendar feed address is itself the password to a family's schedule.
_RE_FEED_TOKEN = re.compile(r"(?i)(/feed/)[A-Za-z0-9_\-]{16,}(\.ics)")

_RE_SIP2_AUTH = re.compile(r"\|(AD|CO)([^|\r\n]+)")
_RE_AUTH_HEADER = re.compile(r"(?i)\b(Authorization(?::\s*|=))([^\r\n]+)")

# Proactive PII heuristic patterns. Names and addresses can't be found by
# shape alone, so this is a net under the rule "don't log them" (AGENTS.md),
# not a replacement for it.
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+(?:@|%40)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_RE_PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")
_RE_PHONE_INTL = re.compile(r"(?<![\w+])\+\d{1,3}[ .-]?\(?\d{1,4}\)?(?:[ .-]?\d{2,4}){2,4}(?!\d)")
_RE_SSN = re.compile(r"(?<!\d)\d{3}[- ]\d{2}[- ]\d{4}(?!\d)")
_RE_STREET = re.compile(
    r"\b\d{1,6}\s+(?:[A-Za-z0-9.'-]+\s+){1,4}"
    r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Ct|Court|Way|Pl|Place|"
    r"Ter|Terrace|Cir|Circle|Hwy|Highway|Pkwy|Parkway)\b\.?",
    re.IGNORECASE,
)

# Colour codes uvicorn adds on a terminal; removed so the next rule doesn't
# turn the escape character into a stray space.
_RE_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# Every C0 control character, including \r and \n. Run LAST, on the whole
# formatted line: anything upstream (a route handler, a plugin, a future
# log.warning() nobody thought to sanitize) can put attacker-controlled text
# straight into a log call, and this is the one place every log line passes
# through (SanitizingFormatter.format(), below) regardless. Without this, an
# embedded \r/\n lets that text forge what looks like a second, separate,
# fully-timestamped log entry (CWE-117) to anyone or anything reading the
# log file or the admin's Logs page later.
_RE_CONTROL_CHARS = re.compile(r"[\x00-\x1f]")


def _quote_like(value: str) -> str:
    """[REDACTED] inside the same quote marks the value had."""
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return value[0] + "[REDACTED]" + value[0]
    return "[REDACTED]"


def _redact_value(m: "re.Match") -> str:
    return m.group(1) + _quote_like(m.group(2))


def sanitize_log_message(msg: str) -> str:
    """
    Scrub credentials, tokens, and sensitive parameters from log strings
    before they are written to disk or stored in memory buffers.
    """
    if not isinstance(msg, str):
        msg = str(msg)
    msg = _RE_ANSI.sub("", msg)
    msg = _RE_BEARER.sub("Bearer [REDACTED]", msg)
    msg = _RE_AUTH_HEADER.sub(r"\1[REDACTED]", msg)
    msg = _RE_URL_CREDENTIALS.sub(r"\1[REDACTED]@", msg)
    msg = _RE_URL_QUERY_SECRETS.sub(r"\1[REDACTED]", msg)
    msg = _RE_FEED_TOKEN.sub(r"\1[REDACTED]\2", msg)
    msg = _RE_KV_SECRETS.sub(_redact_value, msg)
    msg = _RE_KV_PERSONAL.sub(lambda m: m.group(1) + m.group(2) + _quote_like(m.group(3)), msg)
    msg = _RE_SIP2_AUTH.sub(r"|\1[REDACTED]", msg)
    msg = _RE_SSN.sub("[ssn]", msg)
    msg = _RE_EMAIL.sub("[email]", msg)
    msg = _RE_PHONE.sub("[number]", msg)
    msg = _RE_PHONE_INTL.sub("[number]", msg)
    msg = _RE_STREET.sub("[address]", msg)
    msg = _RE_CONTROL_CHARS.sub(" ", msg)
    return msg


class SanitizingFormatter(logging.Formatter):
    """Logging formatter that applies credential and PII sanitization to all outputs."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return sanitize_log_message(formatted)


class _SanitizingWrapper(logging.Formatter):
    """Wraps a handler's existing formatter (uvicorn's access formatter, a
    basicConfig one) so its output is scrubbed the same way ours is."""

    def __init__(self, inner: Optional[logging.Formatter]):
        super().__init__()
        self.inner = inner or logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)

    def format(self, record: logging.LogRecord) -> str:
        return sanitize_log_message(self.inner.format(record))


def sanitize_handler(handler: logging.Handler) -> None:
    """Make one handler scrub what it writes. Safe to call twice."""
    fmt = handler.formatter
    if isinstance(fmt, (SanitizingFormatter, _SanitizingWrapper)):
        return
    handler.setFormatter(_SanitizingWrapper(fmt))


def sanitize_all_handlers() -> None:
    """Every handler on the root logger and on every named logger, which takes
    in uvicorn.access and uvicorn.error. uvicorn gives those their own stdout
    handlers and doesn't pass their records to the root logger, so without this
    request lines (with their query strings) reach `docker compose logs`
    unscrubbed. Call it again after anything that adds handlers."""
    seen = set()
    loggers = [logging.getLogger()] + [
        l for l in list(logging.root.manager.loggerDict.values()) if isinstance(l, logging.Logger)
    ]
    for lg in loggers:
        for h in list(lg.handlers):
            if id(h) not in seen:
                seen.add(id(h))
                sanitize_handler(h)


# Libraries that print URLs, headers, request bodies or SQL parameters when the
# root level is DEBUG. Pinned to WARNING so turning on debug for OpenOptOut's
# own messages doesn't also print a family's details from underneath it.
_CHATTY_LIBRARIES = (
    "sqlalchemy.engine", "sqlalchemy.pool", "httpx", "httpcore", "urllib3", "hpack",
    "asyncio", "multipart", "python_multipart", "PIL", "playwright", "websockets",
)


def quiet_chatty_libraries() -> None:
    for name in _CHATTY_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)


class _SecureRotatingFileHandler(RotatingFileHandler):
    """A log file only its owner can read (0600), including every rotated copy."""

    def _open(self):
        old = os.umask(0o077)
        try:
            stream = super()._open()
        finally:
            os.umask(old)
        try:
            os.chmod(self.baseFilename, 0o600)
        except OSError:
            pass
        return stream

    def doRollover(self):
        super().doRollover()
        for path in glob.glob(self.baseFilename + ".*"):
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass


def _make_log_dir() -> None:
    """Create the log directory as 0700. A directory that already exists is
    left alone: the admin's file-permission alert shows the command to tighten
    it, so nothing changes under an operator's feet."""
    if os.path.isdir(LOGS_DIR):
        return
    old = os.umask(0o077)
    try:
        os.makedirs(LOGS_DIR, mode=0o700, exist_ok=True)
    finally:
        os.umask(old)


# ── In-Memory Ring Buffer Handler ─────────────────────────────────────────────

class MemoryRingBufferHandler(logging.Handler):
    """
    Thread-safe in-memory ring buffer holding recent structured log records
    for high-speed querying and live UI streaming.
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY):
        super().__init__()
        self.capacity = capacity
        self.buffer: collections.deque = collections.deque(maxlen=capacity)
        self._counter = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            # Scrub individual message text if formatting didn't already
            msg = sanitize_log_message(msg)
            with self._lock:
                self._counter += 1
                entry = {
                    "id": self._counter,
                    "timestamp": datetime.datetime.fromtimestamp(
                        record.created, tz=datetime.timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "epoch": record.created,
                    "level": record.levelname,
                    "logger": record.name,
                    "message": msg,
                }
                self.buffer.append(entry)
        except Exception:
            self.handleError(record)

    def query(
        self,
        level: Optional[str] = None,
        logger_filter: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
        cursor: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query buffered logs with filtering.
        - level: minimum log level name (e.g. 'WARNING' returns WARNING, ERROR, CRITICAL)
        - logger_filter: substring match on logger name (e.g. 'plugins', 'scheduler', 'auth')
        - search: case-insensitive keyword search in message or logger
        - limit: max records to return (capped at MAX_QUERY_LIMIT)
        - cursor: returns only entries with id > cursor (for polling updates)
        """
        limit = max(1, min(limit, MAX_QUERY_LIMIT))
        min_level_no = getattr(logging, level.upper(), 0) if level else 0
        search_lower = search.strip().lower() if search else None
        logger_lower = logger_filter.strip().lower() if logger_filter else None

        with self._lock:
            items = list(self.buffer)

        results = []
        for entry in items:
            if cursor and entry["id"] <= cursor:
                continue

            entry_level_no = getattr(logging, entry["level"], 0)
            if min_level_no and entry_level_no < min_level_no:
                continue

            if logger_lower and logger_lower not in entry["logger"].lower():
                continue

            if search_lower:
                text_to_search = f"{entry['logger']} {entry['message']}".lower()
                if search_lower not in text_to_search:
                    continue

            results.append(entry)

        # Return latest entries up to limit
        if len(results) > limit:
            results = results[-limit:]
        return results

    def clear(self):
        with self._lock:
            self.buffer.clear()


# ── Global Instances & State ──────────────────────────────────────────────────

_ring_buffer_handler: Optional[MemoryRingBufferHandler] = None
_file_handler: Optional[RotatingFileHandler] = None
_init_lock = threading.RLock()  # re-entrant: init_logging() holds it while calling get_ring_buffer()


def get_ring_buffer() -> MemoryRingBufferHandler:
    global _ring_buffer_handler
    if _ring_buffer_handler is None:
        with _init_lock:
            if _ring_buffer_handler is None:
                _ring_buffer_handler = MemoryRingBufferHandler(capacity=DEFAULT_CAPACITY)
                _ring_buffer_handler.setFormatter(
                    SanitizingFormatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
                )
    return _ring_buffer_handler


def init_logging():
    """
    Initialize logging handlers (file handler + ring buffer handler) and attach
    them to the root logger. Idempotent.
    """
    global _file_handler, _ring_buffer_handler
    with _init_lock:
        root = logging.getLogger()

        # Ring buffer handler
        rb = get_ring_buffer()
        if rb not in root.handlers:
            root.addHandler(rb)

        # File handler
        if _file_handler is None:
            try:
                _make_log_dir()
                _file_handler = _SecureRotatingFileHandler(
                    LOG_FILE_PATH,
                    maxBytes=10 * 1024 * 1024,  # 10 MB
                    backupCount=5,
                    encoding="utf-8",
                )
                _file_handler.setFormatter(
                    SanitizingFormatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
                )
                if _file_handler not in root.handlers:
                    root.addHandler(_file_handler)
            except Exception as e:
                # If disk is read-only or dir cannot be created, keep running with buffer
                root.warning("Could not initialize file log handler at %s: %s", LOG_FILE_PATH, e)

        quiet_chatty_libraries()
        sanitize_all_handlers()


def get_log_level() -> str:
    """Return the name of the active root logging level."""
    level_no = logging.getLogger().getEffectiveLevel()
    return logging.getLevelName(level_no)


def set_log_level(level_name: str) -> str:
    """
    Dynamically update the active root logging level at runtime.
    Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
    """
    level_name = level_name.upper().strip()
    if level_name not in VALID_LEVELS:
        raise ValueError(f"Invalid log level: {level_name}. Must be one of {VALID_LEVELS}")
    level_no = getattr(logging, level_name)
    logging.getLogger().setLevel(level_no)

    # Also sync attached handlers to capture records matching the new level
    for handler in logging.getLogger().handlers:
        handler.setLevel(level_no)

    quiet_chatty_libraries()
    return level_name


def get_log_file_info() -> Dict[str, Any]:
    """Get metadata about the persistent log file on disk."""
    exists = os.path.exists(LOG_FILE_PATH)
    size = os.path.getsize(LOG_FILE_PATH) if exists else 0
    return {
        "path": LOG_FILE_PATH,
        "exists": exists,
        "size_bytes": size,
        "logs_dir": LOGS_DIR,
    }
