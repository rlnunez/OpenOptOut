"""
Distributed Execution Package (Roadmap Item 7).
"""

from __future__ import annotations

from .envelope import (
    JobEnvelope,
    JobResultEnvelope,
    EnvelopeError,
    EnvelopeTamperedError,
    EnvelopeExpiredError,
    EnvelopeInvalidError,
    canonical_json,
    compute_envelope_hmac,
    create_removal_envelope,
    create_discovery_envelope,
    create_result_envelope,
)

from .queue import (
    JobQueue,
    InProcessJobQueue,
    RedisJobQueue,
    get_queue,
    infer_channel_for_envelope,
    CHANNEL_REMOVAL_HIGH,
    CHANNEL_REMOVAL_NORMAL,
    CHANNEL_DISCOVERY,
    CHANNEL_RETRY,
    CHANNEL_DEAD_LETTER,
    CHANNEL_RESULTS,
    DEFAULT_CHANNELS,
)

from .worker import (
    WorkerConfig,
    WorkerDaemon,
    WorkerBrowserPool,
    execute_discovery_query,
)

from .ingestion import (
    reclaim_orphaned_leases,
    ResultIngestionService,
)

from .registry import (
    WorkerRegistry,
    get_worker_registry,
    collect_system_telemetry,
)

__all__ = [
    # Envelope (Phase 7.1)
    "JobEnvelope",
    "JobResultEnvelope",
    "EnvelopeError",
    "EnvelopeTamperedError",
    "EnvelopeExpiredError",
    "EnvelopeInvalidError",
    "canonical_json",
    "compute_envelope_hmac",
    "create_removal_envelope",
    "create_discovery_envelope",
    "create_result_envelope",
    # Queue (Phase 7.2)
    "JobQueue",
    "InProcessJobQueue",
    "RedisJobQueue",
    "get_queue",
    "infer_channel_for_envelope",
    "CHANNEL_REMOVAL_HIGH",
    "CHANNEL_REMOVAL_NORMAL",
    "CHANNEL_DISCOVERY",
    "CHANNEL_RETRY",
    "CHANNEL_DEAD_LETTER",
    "CHANNEL_RESULTS",
    "DEFAULT_CHANNELS",
    # Worker (Phase 7.3)
    "WorkerConfig",
    "WorkerDaemon",
    "WorkerBrowserPool",
    "execute_discovery_query",
    # Ingestion & Control Plane (Phase 7.4)
    "reclaim_orphaned_leases",
    "ResultIngestionService",
    # Fleet Monitoring & Telemetry (Phase 7.5)
    "WorkerRegistry",
    "get_worker_registry",
    "collect_system_telemetry",
]
