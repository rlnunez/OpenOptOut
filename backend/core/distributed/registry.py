"""
Worker Fleet Heartbeat Registry & Telemetry Aggregator (Roadmap Phase 7.5).

Tracks active distributed worker nodes, their concurrency utilization,
telemetry (CPU, memory, uptime), and operational status (online, busy, draining, offline).
Supports Redis-backed clustering with thread-safe in-memory fallback.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Set, Union

log = logging.getLogger(__name__)

# Key constants for Redis-backed registry
REDIS_KEY_WORKERS = "ps:fleet:workers"
REDIS_KEY_DRAIN = "ps:fleet:drain"
DEFAULT_HEARTBEAT_TIMEOUT = 30.0  # seconds after which node is flagged offline


def collect_system_telemetry() -> Dict[str, Any]:
    """
    Collect lightweight host telemetry (CPU count, memory, platform) without
    heavy external dependencies.
    """
    telemetry: Dict[str, Any] = {
        "platform": platform.system(),
        "release": platform.release(),
        "cpu_count": os.cpu_count() or 1,
        "hostname": socket.gethostname(),
    }
    try:
        # Check load avg on Unix if available
        if hasattr(os, "getloadavg"):
            load1, load5, load15 = os.getloadavg()
            telemetry["load_avg_1m"] = round(load1, 2)
            telemetry["load_avg_5m"] = round(load5, 2)
    except Exception:
        pass

    try:
        # Check memory on Linux via /proc/meminfo if available
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                mem_total = 0
                mem_avail = 0
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"):
                        mem_avail = int(line.split()[1]) // 1024
                if mem_total > 0:
                    telemetry["mem_total_mb"] = mem_total
                    telemetry["mem_available_mb"] = mem_avail
                    telemetry["mem_used_pct"] = round((1 - (mem_avail / mem_total)) * 100, 1)
    except Exception:
        pass

    return telemetry


class WorkerRegistry:
    """
    Thread-safe registry for distributed worker nodes and fleet telemetry.
    """

    def __init__(self, redis_client: Optional[Any] = None):
        self.redis = redis_client
        self._lock = threading.Lock()
        self._in_memory_workers: Dict[str, Dict[str, Any]] = {}
        self._drain_signals: Set[str] = set()

    def record_heartbeat(
        self,
        worker_id: str,
        concurrency: int = 1,
        active_jobs: int = 0,
        jobs_completed: int = 0,
        jobs_failed: int = 0,
        uptime_seconds: float = 0.0,
        started_at: Optional[float] = None,
        telemetry: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        hostname: Optional[str] = None,
        is_draining: bool = False,
    ) -> Dict[str, Any]:
        """
        Record or refresh a worker node's heartbeat in the fleet registry.
        """
        now = time.time()
        start = started_at or (now - uptime_seconds)
        host = hostname or socket.gethostname()

        # Compute worker operational status
        if is_draining or self.is_draining(worker_id):
            status = "draining"
        elif active_jobs >= concurrency and concurrency > 0:
            status = "busy"
        else:
            status = "online"

        worker_data: Dict[str, Any] = {
            "worker_id": worker_id,
            "hostname": host,
            "concurrency": int(concurrency),
            "active_jobs": int(active_jobs),
            "jobs_completed": int(jobs_completed),
            "jobs_failed": int(jobs_failed),
            "uptime_seconds": round(uptime_seconds, 1),
            "started_at": start,
            "last_heartbeat_at": now,
            "status": status,
            "telemetry": telemetry or collect_system_telemetry(),
            "tags": tags or ["playwright", "declarative"],
        }

        if self.redis is not None:
            try:
                self.redis.hset(REDIS_KEY_WORKERS, worker_id, json.dumps(worker_data))
            except Exception as e:
                log.warning("Failed to persist heartbeat in Redis (%s), falling back to in-memory: %s", worker_id, e)
                with self._lock:
                    self._in_memory_workers[worker_id] = worker_data
        else:
            with self._lock:
                self._in_memory_workers[worker_id] = worker_data

        return worker_data

    def get_worker(self, worker_id: str, timeout_seconds: float = DEFAULT_HEARTBEAT_TIMEOUT) -> Optional[Dict[str, Any]]:
        """
        Retrieve state for a specific worker node with current offline status calculation.
        """
        raw: Optional[Dict[str, Any]] = None

        if self.redis is not None:
            try:
                val = self.redis.hget(REDIS_KEY_WORKERS, worker_id)
                if val:
                    raw = json.loads(val.decode("utf-8") if isinstance(val, bytes) else val)
            except Exception as e:
                log.warning("Failed to get worker from Redis: %s", e)

        if raw is None:
            with self._lock:
                raw = self._in_memory_workers.get(worker_id)

        if raw is None:
            return None

        # Check offline threshold
        now = time.time()
        age = now - float(raw.get("last_heartbeat_at", now))
        raw_copy = dict(raw)
        raw_copy["heartbeat_age_seconds"] = round(age, 1)

        if age > timeout_seconds:
            raw_copy["status"] = "offline"
        elif self.is_draining(worker_id):
            raw_copy["status"] = "draining"

        return raw_copy

    def list_workers(self, timeout_seconds: float = DEFAULT_HEARTBEAT_TIMEOUT) -> List[Dict[str, Any]]:
        """
        List all registered worker nodes, ordered by worker_id.
        """
        all_workers: Dict[str, Dict[str, Any]] = {}

        if self.redis is not None:
            try:
                entries = self.redis.hgetall(REDIS_KEY_WORKERS)
                for k, v in entries.items():
                    k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                    v_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                    try:
                        all_workers[k_str] = json.loads(v_str)
                    except Exception:
                        pass
            except Exception as e:
                log.warning("Failed to fetch workers from Redis: %s", e)

        with self._lock:
            for k, v in self._in_memory_workers.items():
                if k not in all_workers:
                    all_workers[k] = dict(v)

        now = time.time()
        result: List[Dict[str, Any]] = []

        for wid, wdata in all_workers.items():
            entry = dict(wdata)
            age = now - float(entry.get("last_heartbeat_at", now))
            entry["heartbeat_age_seconds"] = round(age, 1)
            if age > timeout_seconds:
                entry["status"] = "offline"
            elif self.is_draining(wid):
                entry["status"] = "draining"
            result.append(entry)

        result.sort(key=lambda x: str(x.get("worker_id", "")))
        return result

    def get_fleet_summary(
        self,
        timeout_seconds: float = DEFAULT_HEARTBEAT_TIMEOUT,
        queue: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate operational fleet metrics across all active/offline worker nodes
        and queue depths.
        """
        workers = self.list_workers(timeout_seconds=timeout_seconds)

        total_nodes = len(workers)
        online_nodes = 0
        busy_nodes = 0
        draining_nodes = 0
        offline_nodes = 0

        total_slots = 0
        active_slots = 0
        total_completed = 0
        total_failed = 0

        for w in workers:
            st = w.get("status", "offline")
            conc = int(w.get("concurrency", 1))
            act = int(w.get("active_jobs", 0))

            total_completed += int(w.get("jobs_completed", 0))
            total_failed += int(w.get("jobs_failed", 0))

            if st == "online":
                online_nodes += 1
                total_slots += conc
                active_slots += act
            elif st == "busy":
                busy_nodes += 1
                online_nodes += 1
                total_slots += conc
                active_slots += act
            elif st == "draining":
                draining_nodes += 1
                total_slots += conc
                active_slots += act
            elif st == "offline":
                offline_nodes += 1

        utilization_pct = 0.0
        if total_slots > 0:
            utilization_pct = round((active_slots / total_slots) * 100, 1)

        summary: Dict[str, Any] = {
            "total_nodes": total_nodes,
            "online_nodes": online_nodes,
            "busy_nodes": busy_nodes,
            "draining_nodes": draining_nodes,
            "offline_nodes": offline_nodes,
            "total_slots": total_slots,
            "active_slots": active_slots,
            "idle_slots": max(0, total_slots - active_slots),
            "utilization_pct": utilization_pct,
            "total_jobs_completed": total_completed,
            "total_jobs_failed": total_failed,
            "timestamp": time.time(),
        }

        # Queue depths if queue is provided
        if queue is not None:
            try:
                depths = queue.queue_depth()
                summary["queue_depths"] = depths
                summary["in_flight_count"] = queue.in_flight_count()
                summary["results_depth"] = queue.results_depth()
            except Exception as qe:
                log.debug("Queue depth fetch skipped in fleet summary: %s", qe)

        return summary

    def set_drain_signal(self, worker_id: str, drain: bool = True) -> bool:
        """
        Signal a worker node to drain its in-flight jobs and gracefully stop.
        """
        if self.redis is not None:
            try:
                if drain:
                    self.redis.sadd(REDIS_KEY_DRAIN, worker_id)
                else:
                    self.redis.srem(REDIS_KEY_DRAIN, worker_id)
            except Exception as e:
                log.warning("Failed to update drain signal in Redis: %s", e)

        with self._lock:
            if drain:
                self._drain_signals.add(worker_id)
            else:
                self._drain_signals.discard(worker_id)

        log.info("Worker %s drain signal set to %s", worker_id, drain)
        return True

    def is_draining(self, worker_id: str) -> bool:
        """
        Check if a worker node has been requested to drain.
        """
        if self.redis is not None:
            try:
                if self.redis.sismember(REDIS_KEY_DRAIN, worker_id):
                    return True
            except Exception:
                pass

        with self._lock:
            return worker_id in self._drain_signals

    def prune_stale_workers(self, max_age_seconds: float = 86400.0) -> int:
        """
        Remove stale workers that have been offline longer than max_age_seconds (default 24h).
        """
        now = time.time()
        pruned = 0

        # In-memory prune
        with self._lock:
            stale_ids = [
                wid for wid, data in self._in_memory_workers.items()
                if now - float(data.get("last_heartbeat_at", now)) > max_age_seconds
            ]
            for wid in stale_ids:
                del self._in_memory_workers[wid]
                self._drain_signals.discard(wid)
                pruned += 1

        # Redis prune
        if self.redis is not None:
            try:
                entries = self.redis.hgetall(REDIS_KEY_WORKERS)
                for k, v in entries.items():
                    try:
                        k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                        data = json.loads(v.decode("utf-8") if isinstance(v, bytes) else str(v))
                        if now - float(data.get("last_heartbeat_at", now)) > max_age_seconds:
                            self.redis.hdel(REDIS_KEY_WORKERS, k_str)
                            self.redis.srem(REDIS_KEY_DRAIN, k_str)
                    except Exception:
                        pass
            except Exception as e:
                log.warning("Failed to prune stale workers in Redis: %s", e)

        return pruned


# Global singleton registry
_GLOBAL_REGISTRY: Optional[WorkerRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_worker_registry(redis_client: Optional[Any] = None) -> WorkerRegistry:
    """
    Get or initialize the global WorkerRegistry singleton.
    """
    global _GLOBAL_REGISTRY
    with _REGISTRY_LOCK:
        if _GLOBAL_REGISTRY is None:
            # Check if REDIS_URL is configured in environment
            rc = redis_client
            if rc is None and os.getenv("REDIS_URL"):
                try:
                    import redis
                    rc = redis.from_url(os.environ["REDIS_URL"])
                except Exception as re:
                    log.warning("Could not connect to Redis for WorkerRegistry (%s); using in-memory: %s", os.getenv("REDIS_URL"), re)
            _GLOBAL_REGISTRY = WorkerRegistry(redis_client=rc)
        return _GLOBAL_REGISTRY
