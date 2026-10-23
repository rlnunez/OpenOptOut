"""Size limits for everything a browser or API client can send.

Two layers, so a forgotten field can never mean "unlimited":

1. Whole request (RequestSizeLimitMiddleware, wired in main.py): every request
   body is capped at MAX_BODY_BYTES unless its path is one of the upload
   routes in BODY_LIMIT_OVERRIDES. The query string is capped too. Over the
   limit gets a 413 with a plain message; the body is never fully buffered.

2. Each field: every request model inherits LimitedModel, which caps every
   piece of text in it (including text inside lists and dictionaries) at
   TEXT_MAX characters. Fields that genuinely hold more (certificates, SAML
   metadata, templates, page text) opt up to LONG_TEXT_MAX with
   Field(max_length=LONG_TEXT_MAX); short fields opt down. Lists and
   dictionaries get an item cap with Field(max_length=...).

The test auth.request_fields_bounded walks the whole API and fails if a new
field or upload slips past both layers.

Pure standard library apart from pydantic, imported lazily, so the fuzz
targets can import the constants.
"""
from typing import Optional

# ── Per-field limits (characters / items) ────────────────────────────────────
NAME_MAX = 200            # people's names, labels, titles
TEXT_MAX = 4_000          # default for any text field: URLs, hosts, notes, tokens
LONG_TEXT_MAX = 200_000   # certificates, SAML metadata, templates, page text
ITEMS_MAX = 1_000         # default for lists and dictionaries
IDS_MAX = 10_000          # lists of numeric IDs (bulk broker actions)
ICON_DATA_URL_MAX = 1_500_000  # app icon sent as a data: URL (an image of ~1.1 MB)

# ── Whole-request limits (bytes) ─────────────────────────────────────────────
MAX_BODY_BYTES = 2 * 1024 * 1024        # a full language pack is ~0.5 MB
MAX_QUERY_BYTES = 8 * 1024
_MB = 1024 * 1024
# Upload routes: their own file limit plus room for the multipart wrapping.
# Keep in sync with the limit each route enforces on the file itself.
BODY_LIMIT_OVERRIDES = {
    "/api/plugins/upload":            51 * _MB,   # plugins.MAX_UPLOAD_BYTES = 50 MB
    "/api/resident-addresses/upload": 31 * _MB,   # resident_addresses.MAX_BYTES = 30 MB
    "/api/registry/":                 21 * _MB,   # registry_sync.MAX_BYTES = 20 MB (prefix)
    "/api/brokers/import-csv":        11 * _MB,   # UPLOAD_IMPORT_BYTES
    "/api/brokers/import-json":       11 * _MB,
    "/api/branding/logo":              3 * _MB,   # LOGO_MAX_BYTES
}
UPLOAD_IMPORT_BYTES = 10 * _MB
LOGO_MAX_BYTES = 2 * _MB


def body_limit_for(path: str) -> int:
    """The byte limit for a request to `path` (longest matching prefix wins)."""
    best, best_len = MAX_BODY_BYTES, -1
    for prefix, limit in BODY_LIMIT_OVERRIDES.items():
        if path.startswith(prefix) and len(prefix) > best_len:
            best, best_len = limit, len(prefix)
    return best


def _too_large_message(limit: int) -> str:
    size = f"{limit // _MB} MB" if limit >= _MB else f"{limit // 1024} KB"
    return f"That's too much to send at once (the limit is {size}). Try a smaller file or less text."


class RequestSizeLimitMiddleware:
    """Pure ASGI middleware: reject over-size requests before the app reads
    them. Checks Content-Length up front, and also counts streamed bytes so a
    chunked request with no (or a false) Content-Length can't get around it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        if len(scope.get("query_string", b"")) > MAX_QUERY_BYTES:
            return await _reject(send, 414, "That web address is too long.")

        qs = scope.get("query_string", b"")
        if b"\x00" in qs or b"%00" in qs or b"%0" in qs:
            scope = dict(scope)
            scope["query_string"] = qs.replace(b"\x00", b"").replace(b"%00", b"")

        limit = body_limit_for(scope.get("path", ""))
        is_form_urlencoded = False
        for name, value in scope.get("headers", []):
            if name == b"content-type" and b"application/x-www-form-urlencoded" in value.lower():
                is_form_urlencoded = True
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    return await _reject(send, 400, "The request was malformed.")
                if declared > limit:
                    return await _reject(send, 413, _too_large_message(limit))

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                received += len(chunk)
                if received > limit:
                    raise _BodyTooLarge(limit)
                if is_form_urlencoded and (b"\x00" in chunk or b"%00" in chunk):
                    message = dict(message)
                    message["body"] = chunk.replace(b"\x00", b"").replace(b"%00", b"")
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge as e:
            if not response_started:
                await _reject(send, 413, _too_large_message(e.limit))


try:
    # An HTTPException, so FastAPI passes it through with its own status and
    # message even when it surfaces while a route is parsing the body
    # (FastAPI turns any other exception there into a vague 400).
    from starlette.exceptions import HTTPException as _HTTPException
except ImportError:          # fuzz build without starlette
    _HTTPException = Exception


class _BodyTooLarge(_HTTPException):
    def __init__(self, limit: int):
        self.limit = limit
        if _HTTPException is not Exception:
            super().__init__(status_code=413, detail=_too_large_message(limit))


async def _reject(send, status: int, detail: str):
    import json
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


def read_upload(upload, max_bytes: int, what: str = "file") -> bytes:
    """Read an UploadFile, refusing (413) anything over max_bytes instead of
    loading an unbounded file into memory."""
    from fastapi import HTTPException
    data = upload.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"The {what} is too big. The limit is {max_bytes // _MB} MB.")
    return data


def decode_text_upload(data: bytes, what: str = "file") -> str:
    """Decode an uploaded text file as UTF-8 (with or without a byte-order
    mark), turning a wrong encoding into a readable 400 instead of a crash."""
    from fastapi import HTTPException
    try:
        return strip_null_bytes(data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise HTTPException(400, f"The {what} isn't plain text in UTF-8. "
                                 "Save it as UTF-8 (\"CSV UTF-8\" in Excel) and try again.")


def safe_filename_fragment(s: str, max_len: int = 40, fallback: str = "file") -> str:
    """A string like a broker name turned into something safe to put in a
    file path: only [A-Za-z0-9_-], truncated, never empty (ASVS 5.3.2). Not
    for display — just for building a path component out of untrusted or
    admin-entered text (a broker's name, imported from CSV/JSON or a
    third-party plugin manifest, is not itself path-safe)."""
    import re
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", s or "").strip("_")
    return cleaned[:max_len] or fallback


def strip_null_bytes(val):
    """Recursively strip invisible NUL (\\x00) characters and lone UTF-16
    surrogates from strings, lists, tuples, sets, and dicts so they can never
    reach PostgreSQL, SQLite, or shell/header builders."""
    if isinstance(val, str):
        if "\x00" in val:
            val = val.replace("\x00", "")
        # Also drop lone UTF-16 surrogates (U+D800..U+DFFF) which crash UTF-8 encoders
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in val):
            val = "".join(ch for ch in val if not (0xD800 <= ord(ch) <= 0xDFFF))
        return val
    if isinstance(val, dict):
        return {strip_null_bytes(k): strip_null_bytes(v) for k, v in val.items()}
    if isinstance(val, list):
        return [strip_null_bytes(x) for x in val]
    if isinstance(val, tuple):
        return tuple(strip_null_bytes(x) for x in val)
    return val


def _make_limited_model():
    from pydantic import BaseModel, ConfigDict, model_validator

    class LimitedModel(BaseModel):
        """Base for every request model: caps all text at TEXT_MAX characters
        unless a field sets its own max_length, and strips invisible null
        (\\x00) characters and lone surrogates from every incoming string."""
        model_config = ConfigDict(str_max_length=TEXT_MAX)

        @model_validator(mode="before")
        @classmethod
        def _strip_invisible_nulls(cls, data):
            return strip_null_bytes(data)

    return LimitedModel


try:
    LimitedModel = _make_limited_model()
except ImportError:          # pydantic missing (fuzz build): constants still usable
    LimitedModel: Optional[type] = None

