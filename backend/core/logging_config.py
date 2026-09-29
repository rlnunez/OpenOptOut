"""
Operational visibility & diagnostic logging infrastructure.

Provides:
- Persistent rotating log file (default /data/logs/privacyshield.log, configurable via LOGS_DIR)
- In-memory ring buffer (default 2,000 entries) for fast in-app filtering and live streaming
- Automatic PII and credential sanitization (Bearer tokens, SIP2 credentials, passwords, secrets)
- Dynamic runtime log verbosity management (DEBUG, INFO, WARNING, ERROR)
"""

import collections
import datetime
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

LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", os.path.join(LOGS_DIR, "privacyshield.log"))

# Standard log format
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

VALID_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


# ── Sanitization Patterns ────────────────────────────────────────────────────

_RE_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-_=.]+", re.IGNORECASE)
_RE_PARAM_SECRETS = re.compile(
    r"(?i)\b(password|passwd|pin|secret|client_secret|token|api_key)=([^&\s]+)"
)
_RE_JSON_SECRETS = re.compile(
    r'(?i)("(?:password|passwd|pin|secret|client_secret|token|api_key)"\s*:\s*)"([^"]+)"'
)
_RE_SIP2_AUTH = re.compile(r"\|(AD|CO)([^|\r\n]+)")
_RE_AUTH_HEADER = re.compile(r"(?i)\b(Authorization:\s*)([^\r\n]+)")


def sanitize_log_message(msg: str) -> str:
    """
    Scrub credentials, tokens, and sensitive parameters from log strings
    before they are written to disk or stored in memory buffers.
    """
    if not isinstance(msg, str):
        msg = str(msg)
    msg = _RE_BEARER.sub("Bearer [REDACTED]", msg)
    msg = _RE_PARAM_SECRETS.sub(r"\1=[REDACTED]", msg)
    msg = _RE_JSON_SECRETS.sub(r'\1"[REDACTED]"', msg)
    msg = _RE_SIP2_AUTH.sub(r"|\1[REDACTED]", msg)
    msg = _RE_AUTH_HEADER.sub(r"\1[REDACTED]", msg)
    return msg


class SanitizingFormatter(logging.Formatter):
    """Logging formatter that applies credential and PII sanitization to all outputs."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return sanitize_log_message(formatted)


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
_init_lock = threading.Lock()


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
                os.makedirs(LOGS_DIR, exist_ok=True)
                _file_handler = RotatingFileHandler(
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
