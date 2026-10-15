"""
System Updates API.

Endpoints for checking GitHub releases, inspecting host Docker engine status,
configuring update policies, and initiating safe container upgrades.
All endpoints require super_admin privileges.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..models.database import User
from ..core.auth import require_super_admin
from ..core import updater

router = APIRouter(prefix="/api/system/updates", tags=["updates"])


class PolicyIn(BaseModel):
    policy: str             # "approval_required", "notify_only", "auto_install", "disabled"
    channel: Optional[str] = "stable"  # "stable", "pre_release"


class IgnoreIn(BaseModel):
    tag: str


class ApplyIn(BaseModel):
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
    """Update automated release update policy."""
    valid_policies = {"approval_required", "notify_only", "auto_install", "disabled"}
    if body.policy not in valid_policies:
        raise HTTPException(400, f"Invalid policy. Must be one of: {', '.join(valid_policies)}")

    cfg = updater.get_updater_config()
    cfg["policy"] = body.policy
    if body.channel in {"stable", "pre_release"}:
        cfg["channel"] = body.channel
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
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to initiate update: {e}")

