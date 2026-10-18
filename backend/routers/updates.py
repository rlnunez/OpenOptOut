"""
System Updates API.

Endpoints for checking GitHub releases, inspecting host Docker engine status,
configuring update policies, and initiating safe container upgrades.
All endpoints require super_admin privileges.
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.limits import LimitedModel
from ..models.database import User
from ..core.auth import require_super_admin
from ..core import updater

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system/updates", tags=["updates"])


class PolicyIn(LimitedModel):
    policy: str             # "approval_required", "notify_only", "auto_install", "disabled"
    channel: Optional[str] = "stable"  # "stable", "pre_release"
    schedule_type: Optional[str] = "weekly"  # "weekly", "monthly"
    schedule_weekdays: Optional[List[int]] = Field(default=None, max_length=7)
    schedule_day_of_month: Optional[int] = 1
    schedule_time: Optional[str] = "03:00"
    schedule_window_hours: Optional[int] = 2


class IgnoreIn(LimitedModel):
    tag: str


class ApplyIn(LimitedModel):
    tag: Optional[str] = None


@router.get("")
def get_update_status(_: User = Depends(require_super_admin)):
    """Retrieve current version, latest GitHub release, Docker engine status, and update policy."""
    return updater.check_for_updates(force=False)


@router.post("/check")
def check_updates_now(_: User = Depends(require_super_admin)):
    """Force an immediate check against GitHub Releases and Docker Engine API."""
    return updater.check_for_updates(force=True)


@router.post("/policy")
def set_update_policy(body: PolicyIn, _: User = Depends(require_super_admin)):
    """Update automated release update policy and install window schedule."""
    valid_policies = {"approval_required", "notify_only", "auto_install", "disabled"}
    if body.policy not in valid_policies:
        raise HTTPException(400, f"Invalid policy. Must be one of: {', '.join(valid_policies)}")

    cfg = updater.get_updater_config()
    cfg["policy"] = body.policy
    if body.channel in {"stable", "pre_release"}:
        cfg["channel"] = body.channel

    if body.schedule_type in {"weekly", "monthly"}:
        cfg["schedule_type"] = body.schedule_type

    if body.schedule_weekdays is not None:
        valid_days = [d for d in body.schedule_weekdays if isinstance(d, int) and 0 <= d <= 6]
        if not valid_days:
            raise HTTPException(400, "schedule_weekdays must contain at least one valid day (0=Monday..6=Sunday).")
        cfg["schedule_weekdays"] = sorted(list(set(valid_days)))

    if body.schedule_day_of_month is not None:
        if not (1 <= body.schedule_day_of_month <= 31):
            raise HTTPException(400, "schedule_day_of_month must be between 1 and 31.")
        cfg["schedule_day_of_month"] = body.schedule_day_of_month

    if body.schedule_time is not None:
        import re
        if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", body.schedule_time.strip()):
            raise HTTPException(400, "schedule_time must be in 24-hour HH:MM format (e.g. 03:00).")
        cfg["schedule_time"] = body.schedule_time.strip()

    if body.schedule_window_hours is not None:
        if not (1 <= body.schedule_window_hours <= 24):
            raise HTTPException(400, "schedule_window_hours must be between 1 and 24 hours.")
        cfg["schedule_window_hours"] = body.schedule_window_hours

    updater.save_updater_config(cfg)
    return updater.check_for_updates(force=False)


@router.post("/ignore")
def ignore_release(body: IgnoreIn, _: User = Depends(require_super_admin)):
    """Ignore a specific release tag from update notifications."""
    tag = body.tag.strip()
    if not tag:
        raise HTTPException(400, "Release tag cannot be empty.")

    cfg = updater.get_updater_config()
    ignored = set(cfg.get("ignored_releases", []))
    ignored.add(tag)
    cfg["ignored_releases"] = sorted(list(ignored))
    updater.save_updater_config(cfg)
    return updater.check_for_updates(force=False)


@router.post("/unignore")
def unignore_release(body: IgnoreIn, _: User = Depends(require_super_admin)):
    """Remove a release tag from the ignored list."""
    tag = body.tag.strip()
    cfg = updater.get_updater_config()
    ignored = set(cfg.get("ignored_releases", []))
    ignored.discard(tag)
    cfg["ignored_releases"] = sorted(list(ignored))
    updater.save_updater_config(cfg)
    return updater.check_for_updates(force=False)


@router.post("/apply")
def apply_update(body: ApplyIn, _: User = Depends(require_super_admin)):
    """Initiate a safe container update (pauses removals, creates safety backup, signals updater)."""
    try:
        return updater.request_system_update(target_tag=body.tag)
    except ValueError as e:
        log.warning("Update request rejected: %s", e)
        raise HTTPException(400, "Invalid update request or release target not found.")
    except Exception as e:
        log.error("Failed to initiate system update: %s", e)
        raise HTTPException(500, "Failed to initiate update. Please check system logs.")


@router.post("/rollback")
def rollback_update(_: User = Depends(require_super_admin)):
    """Initiate a rollback to the previous version using the pre-update safety snapshot."""
    try:
        return updater.request_system_rollback()
    except ValueError as e:
        log.warning("Rollback request rejected: %s", e)
        raise HTTPException(400, "No previous version safety snapshot is available to restore.")
    except Exception as e:
        log.error("Failed to initiate system rollback: %s", e)
        raise HTTPException(500, "Failed to initiate rollback. Please check system logs.")


