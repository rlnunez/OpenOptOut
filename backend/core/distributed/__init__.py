"""
Distributed Execution Package (Roadmap Item 7).
"""

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
]
