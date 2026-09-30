"""
Diagnostic logs API router.

Exposes live in-memory filtered logs, log file download, and dynamic log verbosity
management for super admins and authorized managers (via logs.view / logs.manage).
"""

from datetime import datetime, timezone
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..core.access import require_permission
from ..core.auth import get_current_user
from ..core.logging_config import (
    get_ring_buffer,
    get_log_level,
    set_log_level,
    get_log_file_info,
    VALID_LEVELS,
    LOG_FILE_PATH,
)
from ..models.database import User

router = APIRouter(prefix="/api/logs", tags=["logs"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class LogEntry(BaseModel):
    id: int
    timestamp: str
    epoch: float
    level: str
    logger: str
    message: str


class LogQueryResponse(BaseModel):
    entries: List[LogEntry]
    total: int
    active_level: str
    file_info: dict


class LogLevelResponse(BaseModel):
    level: str
    available_levels: List[str]


class LogLevelUpdate(BaseModel):
    level: str = Field(..., description="Target logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=LogQueryResponse)
def get_logs(
    level: Optional[str] = Query(None, description="Minimum log level (DEBUG, INFO, WARNING, ERROR)"),
    logger: Optional[str] = Query(None, description="Filter by logger / component name"),
    search: Optional[str] = Query(None, description="Search query string"),
    limit: int = Query(200, ge=1, le=1000, description="Max entries to return"),
    cursor: Optional[int] = Query(None, description="Return entries with id > cursor"),
    current_user: User = Depends(require_permission("logs.view")),
):
    """
    Fetch filtered diagnostic log entries from the in-memory buffer.
    Accessible to super admins and managers with 'logs.view'.
    """
    rb = get_ring_buffer()
    entries = rb.query(
        level=level,
        logger_filter=logger,
        search=search,
        limit=limit,
        cursor=cursor,
    )
    return {
        "entries": entries,
        "total": len(entries),
        "active_level": get_log_level(),
        "file_info": get_log_file_info(),
    }


@router.get("/download")
def download_logs(
    current_user: User = Depends(require_permission("logs.view")),
):
    """
    Download the persistent rotating log file from disk.
    Accessible to super admins and managers with 'logs.view'.
    """
    file_info = get_log_file_info()
    path = file_info["path"]

    # If the file does not exist on disk yet, flush current ring buffer to create it
    if not file_info["exists"] or file_info["size_bytes"] == 0:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rb = get_ring_buffer()
        with open(path, "w", encoding="utf-8") as f:
            for item in rb.query(limit=1000):
                f.write(f"{item['timestamp']} [{item['level']}] [{item['logger']}] {item['message']}\n")

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"openoptout_diagnostics_{timestamp_str}.log"

    return FileResponse(
        path=path,
        media_type="text/plain; charset=utf-8",
        filename=filename,
    )


@router.get("/level", response_model=LogLevelResponse)
def get_level(
    current_user: User = Depends(require_permission("logs.view")),
):
    """
    Get the current active logging level.
    """
    return {
        "level": get_log_level(),
        "available_levels": VALID_LEVELS,
    }


@router.post("/level", response_model=LogLevelResponse)
def update_level(
    payload: LogLevelUpdate,
    current_user: User = Depends(require_permission("logs.manage")),
):
    """
    Dynamically change the root log level at runtime without restarting services.
    Accessible to super admins and managers with 'logs.manage'.
    """
    try:
        new_level = set_log_level(payload.level)
        return {
            "level": new_level,
            "available_levels": VALID_LEVELS,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/clear-buffer")
def clear_buffer(
    current_user: User = Depends(require_permission("logs.manage")),
):
    """
    Clear the in-memory ring buffer (does not delete disk files).
    Accessible to super admins and managers with 'logs.manage'.
    """
    rb = get_ring_buffer()
    rb.clear()
    return {"status": "ok", "message": "In-memory log buffer cleared"}
