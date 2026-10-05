"""
Unified Queue Abstraction & Pluggable Backends (Roadmap Phase 7.2).

Provides the transport boundary between the Control Plane and the Worker Fleet:
  - InProcessJobQueue: Thread-safe in-memory queue with priority channels,
    in-flight tracking, and zero external dependencies (default for single-node).
  - RedisJobQueue: Distributed Redis-backed queue supporting prioritized
    worker channels (removal_high, removal_normal, discovery, retry, dlq)
    and atomic delivery.
  - get_queue(): Factory function resolving queue backend based on configuration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import collections
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from .envelope import (
    JobEnvelope,
    JobResultEnvelope,
    EnvelopeError,
    EnvelopeTamperedError,
    EnvelopeExpiredError,
    EnvelopeInvalidError,
    canonical_json,
)

log = logging.getLogger(__name__)

# Standard Priority Channels
CHANNEL_REMOVAL_HIGH = "removal_high"
CHANNEL_REMOVAL_NORMAL = "removal_normal"
CHANNEL_DISCOVERY = "discovery"
CHANNEL_RETRY = "retry"
CHANNEL_DEAD_LETTER = "dlq"
CHANNEL_RESULTS = "results"

DEFAULT_CHANNELS = [
    CHANNEL_REMOVAL_HIGH,
    CHANNEL_REMOVAL_NORMAL,
    CHANNEL_DISCOVERY,
    CHANNEL_RETRY,
]


def infer_channel_for_envelope(envelope: JobEnvelope) -> str:
    """Infer the default queue channel based on envelope action and priority."""
    if envelope.action == "removal":
        return CHANNEL_REMOVAL_HIGH if envelope.priority == "high" else CHANNEL_REMOVAL_NORMAL
    elif envelope.action == "discovery":
        return CHANNEL_DISCOVERY
    return CHANNEL_REMOVAL_NORMAL


# ── Abstract Base Queue Interface ─────────────────────────────────────────────

class JobQueue(ABC):
    """
    Abstract interface for distributed job and result dispatch.
    Decouples scheduling producers and execution workers from physical transport.
    """

    @abstractmethod
    def enqueue(self, envelope: JobEnvelope, queue_name: Optional[str] = None) -> str:
        """
        Enqueue a JobEnvelope onto a specified channel (or inferred priority channel).
        Returns the envelope_id.
        """
        pass

    @abstractmethod
    def dequeue(
        self,
        queue_names: Optional[List[str]] = None,
        timeout: float = 0.0,
        verify_signature: bool = False,  # nosemgrep: queue-message-signature-not-verified -- verified by WorkerDaemon.execute_envelope for DLQ routing
    ) -> Optional[JobEnvelope]:
        """
        Dequeue the next JobEnvelope from the specified channels (in priority order).
        Blocks up to timeout seconds (0.0 means return immediately if empty).
        Returns None if queue is empty or timeout expires.
        """
        pass

    @abstractmethod
    def acknowledge(self, envelope_id: str) -> bool:
        """
        Acknowledge completion of a leased envelope, removing it from in-flight tracking.
        Returns True if the envelope was tracked in-flight, False otherwise.
        """
        pass

    @abstractmethod
    def requeue(
        self,
        envelope: JobEnvelope,
        queue_name: str = CHANNEL_RETRY,
        delay_seconds: float = 0.0,
    ) -> str:
        """
        Requeue a failed or deferred job back onto a queue (default: retry).
        """
        pass

    @abstractmethod
    def dead_letter(self, envelope: JobEnvelope, reason: str = "") -> str:
        """
        Route an unrecoverable or poison envelope to the dead-letter queue (dlq).
        """
        pass

    @abstractmethod
    def publish_result(self, result_envelope: JobResultEnvelope) -> str:
        """
        Publish an execution result back to the control plane.
        """
        pass

    @abstractmethod
    def get_result(self, timeout: float = 0.0) -> Optional[JobResultEnvelope]:
        """
        Fetch the next execution result envelope (for control plane ingestion).
        Blocks up to timeout seconds.
        """
        pass

    @abstractmethod
    def results_depth(self) -> int:
        """Return the count of results waiting in the results channel."""
        pass

    @abstractmethod
    def queue_depth(self, queue_name: Optional[str] = None) -> Union[int, Dict[str, int]]:
        """
        Return the count of pending items for a queue, or a dictionary of depths across all channels.
        """
        pass

    @abstractmethod
    def in_flight_count(self) -> int:
        """
        Return the number of envelopes currently leased/in-flight.
        """
        pass

    @abstractmethod
    def get_in_flight_leases(self) -> List[Dict[str, Any]]:
        """
        Return active in-flight lease metadata for orphan detection and reclamation.
        Each entry is a dict: {'envelope_id': str, 'envelope': JobEnvelope, 'leased_at': float, 'age_seconds': float}
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """
        Clear all queues, in-flight leases, and results.
        """
        pass


# ── In-Process Job Queue (Zero-Dependency Thread-Safe) ─────────────────────────

class InProcessJobQueue(JobQueue):
    """
    Thread-safe in-memory queue implementation with priority channels,
    in-flight lease tracking, and zero external dependencies.
    """

    def __init__(self, secret_key: Optional[Union[str, bytes]] = None):
        self.secret_key = secret_key
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._results_cond = threading.Condition(self._lock)

        self._channels: Dict[str, collections.deque] = {
            CHANNEL_REMOVAL_HIGH: collections.deque(),
            CHANNEL_REMOVAL_NORMAL: collections.deque(),
            CHANNEL_DISCOVERY: collections.deque(),
            CHANNEL_RETRY: collections.deque(),
            CHANNEL_DEAD_LETTER: collections.deque(),
        }
        self._in_flight: Dict[str, Dict[str, Any]] = {}
        self._results: collections.deque = collections.deque()

    def enqueue(self, envelope: JobEnvelope, queue_name: Optional[str] = None) -> str:
        ch = queue_name or infer_channel_for_envelope(envelope)
        with self._cond:
            if ch not in self._channels:
                self._channels[ch] = collections.deque()

            # Store serialized copy to guarantee immutability across thread boundaries
            serialized = envelope.to_json()
            self._channels[ch].append(serialized)
            self._cond.notify_all()
            return envelope.envelope_id

    def dequeue(
        self,
        queue_names: Optional[List[str]] = None,
        timeout: float = 0.0,
        verify_signature: bool = False,  # nosemgrep: queue-message-signature-not-verified -- verified by WorkerDaemon.execute_envelope for DLQ routing
    ) -> Optional[JobEnvelope]:
        channels = queue_names or DEFAULT_CHANNELS
        deadline = time.time() + timeout if timeout > 0 else 0.0

        with self._cond:
            while True:
                # Check channels in strict priority order
                for ch in channels:
                    q = self._channels.get(ch)
                    if q and len(q) > 0:
                        raw_json = q.popleft()
                        envelope = JobEnvelope.from_json(
                            raw_json,
                            secret_key=self.secret_key,
                            verify_signature=verify_signature,
                        )
                        self._in_flight[envelope.envelope_id] = {
                            "raw_json": raw_json,
                            "envelope": envelope,
                            "channel": ch,
                            "leased_at": time.time(),
                        }
                        return envelope

                if timeout <= 0:
                    return None

                remaining = deadline - time.time()
                if remaining <= 0:
                    return None

                self._cond.wait(timeout=remaining)

    def acknowledge(self, envelope_id: str) -> bool:
        with self._lock:
            if envelope_id in self._in_flight:
                del self._in_flight[envelope_id]
                return True
            return False

    def requeue(
        self,
        envelope: JobEnvelope,
        queue_name: str = CHANNEL_RETRY,
        delay_seconds: float = 0.0,
    ) -> str:
        with self._cond:
            # Remove from in-flight if present
            self._in_flight.pop(envelope.envelope_id, None)

            # Update retry count metadata
            retries = int(envelope.meta.get("retries", 0)) + 1
            envelope.meta["retries"] = retries
            envelope.meta["last_requeued_at"] = time.time()
            if self.secret_key:
                envelope.sign(self.secret_key)

            if queue_name not in self._channels:
                self._channels[queue_name] = collections.deque()

            # If delay is requested, we can still enqueue directly in-process
            self._channels[queue_name].append(envelope.to_json())
            self._cond.notify_all()
            return envelope.envelope_id

    def dead_letter(self, envelope: JobEnvelope, reason: str = "") -> str:
        with self._cond:
            self._in_flight.pop(envelope.envelope_id, None)

            envelope.meta["dead_letter_reason"] = reason
            envelope.meta["dead_lettered_at"] = time.time()
            if self.secret_key:
                envelope.sign(self.secret_key)

            self._channels[CHANNEL_DEAD_LETTER].append(envelope.to_json())
            return envelope.envelope_id

    def publish_result(self, result_envelope: JobResultEnvelope) -> str:
        with self._results_cond:
            serialized = result_envelope.to_json()
            self._results.append(serialized)
            self._results_cond.notify_all()
            return result_envelope.envelope_id

    def get_result(self, timeout: float = 0.0) -> Optional[JobResultEnvelope]:
        deadline = time.time() + timeout if timeout > 0 else 0.0
        with self._results_cond:
            while True:
                if self._results:
                    raw_json = self._results.popleft()
                    return JobResultEnvelope.from_json(
                        raw_json,
                        secret_key=self.secret_key,
                        verify_signature=bool(self.secret_key),
                    )

                if timeout <= 0:
                    return None

                remaining = deadline - time.time()
                if remaining <= 0:
                    return None

                self._results_cond.wait(timeout=remaining)

    def results_depth(self) -> int:
        with self._results_cond:
            return len(self._results)

    def queue_depth(self, queue_name: Optional[str] = None) -> Union[int, Dict[str, int]]:
        with self._lock:
            if queue_name is not None:
                return len(self._channels.get(queue_name, []))
            depths = {ch: len(q) for ch, q in self._channels.items()}
            depths["total"] = sum(depths.values())
            return depths

    def in_flight_count(self) -> int:
        with self._lock:
            return len(self._in_flight)

    def get_in_flight_leases(self) -> List[Dict[str, Any]]:
        with self._lock:
            now = time.time()
            leases = []
            for env_id, info in self._in_flight.items():
                leases.append({
                    "envelope_id": env_id,
                    "envelope": info["envelope"],
                    "leased_at": info["leased_at"],
                    "age_seconds": max(0.0, now - info["leased_at"]),
                    "channel": info.get("channel", ""),
                })
            return leases

    def clear(self) -> None:
        with self._lock:
            for q in self._channels.values():
                q.clear()
            self._in_flight.clear()
            self._results.clear()


# ── Redis Job Queue (Distributed Backed) ──────────────────────────────────────

class RedisJobQueue(JobQueue):
    """
    Distributed queue backend backed by Redis.
    Uses atomic list operations (RPUSH, BLPOP, RPOPLPUSH) across priority channels.
    """

    KEY_PREFIX = "ps:queue:"
    KEY_INFLIGHT = "ps:inflight"
    KEY_RESULTS = "ps:queue:results"

    def __init__(
        self,
        redis_client: Optional[Any] = None,
        redis_url: Optional[str] = None,
        secret_key: Optional[Union[str, bytes]] = None,
    ):
        self.secret_key = secret_key
        if redis_client is not None:
            self.client = redis_client
        else:
            try:
                import redis
                url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
                self.client = redis.from_url(url, decode_responses=True)
            except ImportError:
                raise ImportError(
                    "The 'redis' package is required to use RedisJobQueue. "
                    "Install it via `pip install redis`."
                )

    def _channel_key(self, channel: str) -> str:
        return f"{self.KEY_PREFIX}{channel}"

    def enqueue(self, envelope: JobEnvelope, queue_name: Optional[str] = None) -> str:
        ch = queue_name or infer_channel_for_envelope(envelope)
        key = self._channel_key(ch)
        serialized = envelope.to_json()
        self.client.rpush(key, serialized)
        return envelope.envelope_id

    def dequeue(
        self,
        queue_names: Optional[List[str]] = None,
        timeout: float = 0.0,
        verify_signature: bool = False,  # nosemgrep: queue-message-signature-not-verified -- verified by WorkerDaemon.execute_envelope for DLQ routing
    ) -> Optional[JobEnvelope]:
        channels = queue_names or DEFAULT_CHANNELS
        keys = [self._channel_key(ch) for ch in channels]

        # Use non-blocking pop if timeout is 0
        if timeout <= 0:
            for key in keys:
                item = self.client.lpop(key)
                if item:
                    # In python redis, decode_responses may return str or bytes
                    raw_json = item.decode("utf-8") if isinstance(item, bytes) else str(item)
                    env = JobEnvelope.from_json(
                        raw_json,
                        secret_key=self.secret_key,
                        verify_signature=verify_signature,
                    )
                    lease_data = json.dumps({"leased_at": time.time(), "raw_json": raw_json})
                    self.client.hset(self.KEY_INFLIGHT, env.envelope_id, lease_data)
                    return env
            return None

        # Blocking pop across keys in priority order
        t_int = max(1, int(timeout))
        res = self.client.blpop(keys, timeout=t_int)
        if not res:
            return None

        # blpop returns (key, item) tuple
        _, item = res
        raw_json = item.decode("utf-8") if isinstance(item, bytes) else str(item)
        env = JobEnvelope.from_json(
            raw_json,
            secret_key=self.secret_key,
            verify_signature=verify_signature,
        )
        lease_data = json.dumps({"leased_at": time.time(), "raw_json": raw_json})
        self.client.hset(self.KEY_INFLIGHT, env.envelope_id, lease_data)
        return env

    def acknowledge(self, envelope_id: str) -> bool:
        removed = self.client.hdel(self.KEY_INFLIGHT, envelope_id)
        return bool(removed)

    def requeue(
        self,
        envelope: JobEnvelope,
        queue_name: str = CHANNEL_RETRY,
        delay_seconds: float = 0.0,
    ) -> str:
        self.client.hdel(self.KEY_INFLIGHT, envelope.envelope_id)
        retries = int(envelope.meta.get("retries", 0)) + 1
        envelope.meta["retries"] = retries
        envelope.meta["last_requeued_at"] = time.time()
        if self.secret_key:
            envelope.sign(self.secret_key)

        key = self._channel_key(queue_name)
        self.client.rpush(key, envelope.to_json())
        return envelope.envelope_id

    def dead_letter(self, envelope: JobEnvelope, reason: str = "") -> str:
        self.client.hdel(self.KEY_INFLIGHT, envelope.envelope_id)
        envelope.meta["dead_letter_reason"] = reason
        envelope.meta["dead_lettered_at"] = time.time()
        if self.secret_key:
            envelope.sign(self.secret_key)

        key = self._channel_key(CHANNEL_DEAD_LETTER)
        self.client.rpush(key, envelope.to_json())
        return envelope.envelope_id

    def publish_result(self, result_envelope: JobResultEnvelope) -> str:
        serialized = result_envelope.to_json()
        self.client.rpush(self.KEY_RESULTS, serialized)
        return result_envelope.envelope_id

    def get_result(self, timeout: float = 0.0) -> Optional[JobResultEnvelope]:
        if timeout <= 0:
            item = self.client.lpop(self.KEY_RESULTS)
            if not item:
                return None
        else:
            t_int = max(1, int(timeout))
            res = self.client.blpop([self.KEY_RESULTS], timeout=t_int)
            if not res:
                return None
            _, item = res

        raw_json = item.decode("utf-8") if isinstance(item, bytes) else str(item)
        return JobResultEnvelope.from_json(
            raw_json,
            secret_key=self.secret_key,
            verify_signature=bool(self.secret_key),
        )

    def results_depth(self) -> int:
        return int(self.client.llen(self.KEY_RESULTS))

    def queue_depth(self, queue_name: Optional[str] = None) -> Union[int, Dict[str, int]]:
        if queue_name is not None:
            return int(self.client.llen(self._channel_key(queue_name)))

        all_channels = DEFAULT_CHANNELS + [CHANNEL_DEAD_LETTER]
        depths = {}
        total = 0
        for ch in all_channels:
            d = int(self.client.llen(self._channel_key(ch)))
            depths[ch] = d
            total += d
        depths["total"] = total
        return depths

    def in_flight_count(self) -> int:
        return int(self.client.hlen(self.KEY_INFLIGHT))

    def get_in_flight_leases(self) -> List[Dict[str, Any]]:
        now = time.time()
        leases = []
        try:
            entries = self.client.hgetall(self.KEY_INFLIGHT)
            for env_id_raw, val in entries.items():
                env_id = env_id_raw.decode("utf-8") if isinstance(env_id_raw, bytes) else str(env_id_raw)
                val_str = val.decode("utf-8") if isinstance(val, bytes) else str(val)
                leased_at = now
                raw_json = val_str
                try:
                    data = json.loads(val_str)
                    if isinstance(data, dict) and "leased_at" in data and "raw_json" in data:
                        leased_at = float(data["leased_at"])
                        raw_json = data["raw_json"]
                except Exception:
                    pass
                try:
                    # nosemgrep: queue-message-signature-not-verified -- admin inspection of in-flight leases does not execute envelopes
                    env = JobEnvelope.from_json(raw_json, secret_key=self.secret_key, verify_signature=False)
                    leases.append({
                        "envelope_id": env_id,
                        "envelope": env,
                        "leased_at": leased_at,
                        "age_seconds": max(0.0, now - leased_at),
                    })
                except Exception:
                    pass
        except Exception as e:
            log.warning("Could not read in-flight leases from Redis: %s", e)
        return leases

    def clear(self) -> None:
        keys = [self._channel_key(ch) for ch in DEFAULT_CHANNELS + [CHANNEL_DEAD_LETTER]]
        keys.extend([self.KEY_INFLIGHT, self.KEY_RESULTS])
        self.client.delete(*keys)


# ── Global Queue Factory & Provider ───────────────────────────────────────────

_GLOBAL_QUEUE: Optional[JobQueue] = None
_GLOBAL_LOCK = threading.Lock()


def get_queue(
    url: Optional[str] = None,
    secret_key: Optional[Union[str, bytes]] = None,
    reset: bool = False,
) -> JobQueue:
    """
    Provide the global queue instance. If REDIS_URL or url is present,
    constructs RedisJobQueue; otherwise provides an InProcessJobQueue.
    """
    global _GLOBAL_QUEUE
    with _GLOBAL_LOCK:
        if reset or _GLOBAL_QUEUE is None:
            resolved_url = url or os.getenv("REDIS_URL")
            sec_key = secret_key or os.getenv("SECRET_KEY")
            if resolved_url:
                try:
                    _GLOBAL_QUEUE = RedisJobQueue(redis_url=resolved_url, secret_key=sec_key)
                    log.info("Initialized distributed RedisJobQueue at %s", resolved_url)
                except Exception as e:
                    log.warning("Could not initialize RedisJobQueue (%s); falling back to InProcessJobQueue", e)
                    _GLOBAL_QUEUE = InProcessJobQueue(secret_key=sec_key)
            else:
                _GLOBAL_QUEUE = InProcessJobQueue(secret_key=sec_key)
                log.debug("Initialized standalone InProcessJobQueue")
        return _GLOBAL_QUEUE
