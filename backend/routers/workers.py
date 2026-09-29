"""
Worker Fleet Management & Telemetry API Router (Roadmap Phase 7.5).

Provides control plane endpoints to monitor distributed worker nodes,
query fleet health, inspect queue depths, signal worker draining,
and trigger orphan lease reclamation.
Gated by the `settings.system` permission.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..core.access import require_permission
from ..core.distributed.registry import get_worker_registry, WorkerRegistry
from ..core.distributed.queue import get_queue, JobQueue
from ..core.distributed.ingestion import reclaim_orphaned_leases

router = APIRouter(prefix="/api/workers", tags=["workers"])
log = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class DrainWorkerRequest(BaseModel):
    drain: bool = Field(True, description="True to signal node to drain and stop, False to cancel")


class ReclaimLeasesRequest(BaseModel):
    lease_timeout_seconds: float = Field(300.0, description="Age in seconds after which an in-flight lease is considered orphaned")
    max_retries: int = Field(3, description="Maximum requeue attempts before moving orphaned job to DLQ")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[Dict[str, Any]])
def list_workers(
    timeout_seconds: float = Query(30.0, ge=1.0, le=300.0, description="Heartbeat timeout threshold in seconds"),
    _ = Depends(require_permission("settings.system")),
):
    """
    List all registered worker nodes with their status, slots, uptime, and host telemetry.
    """
    reg = get_worker_registry()
    return reg.list_workers(timeout_seconds=timeout_seconds)


@router.get("/stats", response_model=Dict[str, Any])
def fleet_stats(
    timeout_seconds: float = Query(30.0, ge=1.0, le=300.0),
    _ = Depends(require_permission("settings.system")),
):
    """
    Aggregate operational summary of the distributed fleet and queue depths.
    """
    reg = get_worker_registry()
    queue = get_queue()
    return reg.get_fleet_summary(timeout_seconds=timeout_seconds, queue=queue)


@router.get("/{worker_id}", response_model=Dict[str, Any])
def get_worker_details(
    worker_id: str,
    timeout_seconds: float = Query(30.0, ge=1.0, le=300.0),
    _ = Depends(require_permission("settings.system")),
):
    """
    Get detailed telemetry and heartbeat information for a specific worker node.
    """
    reg = get_worker_registry()
    w = reg.get_worker(worker_id=worker_id, timeout_seconds=timeout_seconds)
    if not w:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Worker '{worker_id}' not found")
    return w


@router.post("/{worker_id}/drain")
def drain_worker(
    worker_id: str,
    req: DrainWorkerRequest = DrainWorkerRequest(),
    _ = Depends(require_permission("settings.system")),
):
    """
    Signal a worker node to gracefully drain its active jobs and shut down.
    """
    reg = get_worker_registry()
    reg.set_drain_signal(worker_id=worker_id, drain=req.drain)
    return {
        "worker_id": worker_id,
        "draining": req.drain,
        "message": f"Worker '{worker_id}' drain signal updated to {req.drain}",
    }


@router.post("/reclaim")
def trigger_lease_reclamation(
    req: ReclaimLeasesRequest = ReclaimLeasesRequest(),
    _ = Depends(require_permission("settings.system")),
):
    """
    Manually sweep in-flight leases and reclaim orphaned jobs from crashed workers.
    """
    queue = get_queue()
    report = reclaim_orphaned_leases(
        queue=queue,
        lease_timeout_seconds=req.lease_timeout_seconds,
        max_retries=req.max_retries,
    )
    return {
        "status": "success",
        "report": report,
    }


@router.delete("/{worker_id}")
def deregister_worker(
    worker_id: str,
    _ = Depends(require_permission("settings.system")),
):
    """
    Remove an offline or decommissioned worker node from the fleet registry.
    """
    reg = get_worker_registry()
    w = reg.get_worker(worker_id=worker_id)
    if not w:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Worker '{worker_id}' not found")

    with reg._lock:
        reg._in_memory_workers.pop(worker_id, None)
        reg._drain_signals.discard(worker_id)

    if reg.redis is not None:
        try:
            reg.redis.hdel("ps:fleet:workers", worker_id)
            reg.redis.srem("ps:fleet:drain", worker_id)
        except Exception as e:
            log.warning("Failed to deregister worker from Redis: %s", e)

    return {"status": "success", "worker_id": worker_id, "message": "Worker deregistered"}
