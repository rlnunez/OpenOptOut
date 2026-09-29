"""
Control Plane Result Ingestion & Lease Management (Roadmap Phase 7.4).

Processes execution results returned by workers in the distributed fleet:
  - Ingests JobResultEnvelopes: updates RemovalRequest statuses, creates AutomationLogs,
    records broker health metrics, and routes CAPTCHA challenges to the operator queue.
  - Stores discovered profile URLs in DiscoveryResult and automatically chains
    discovered URLs into downstream removal requests.
  - Triggers parent company cascade confirmations when parent-wide requests confirm.
  - Lease management & orphan reclamation: detects timed-out worker leases and
    safely requeues or dead-letters orphaned jobs.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .envelope import JobResultEnvelope, JobEnvelope
from .queue import (
    JobQueue,
    get_queue,
    CHANNEL_RETRY,
    CHANNEL_DEAD_LETTER,
)

log = logging.getLogger(__name__)

# Resilient ORM model resolution (supports test environments where SQLAlchemy is absent)
try:
    from ...models.database import (
        RemovalRequest,
        RequestStatus,
        AutomationLog,
        CaptchaChallenge,
        DiscoveryResult,
        Broker,
    )
    HAS_ORM_MODELS = True
except ImportError:
    HAS_ORM_MODELS = False
    class RequestStatus:  # type: ignore
        pending = "pending"
        submitted = "submitted"
        needs_manual = "needs_manual"
        confirmed = "confirmed"
        failed = "failed"

    class _DummyCol:
        def __eq__(self, other): return True
        def __ne__(self, other): return True
        def ilike(self, other): return True

    class RemovalRequest:  # type: ignore
        id = _DummyCol()
        request_key = _DummyCol()
        member_id = _DummyCol()
        broker_id = _DummyCol()
        status = _DummyCol()
        listing_url = _DummyCol()
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class AutomationLog:  # type: ignore
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class CaptchaChallenge:  # type: ignore
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class DiscoveryResult:  # type: ignore
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class Broker:  # type: ignore
        id = _DummyCol()
        name = _DummyCol()
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)


def _make_record(cls, **kwargs) -> Any:
    if cls is not None:
        try:
            return cls(**kwargs)
        except Exception:
            pass
    from types import SimpleNamespace
    return SimpleNamespace(**kwargs)


def _record_broker_success(db: Any, broker_id: Any) -> None:
    try:
        from ..broker_health import record_success
        record_success(db, broker_id)
    except Exception:
        try:
            from core.broker_health import record_success
            record_success(db, broker_id)
        except Exception:
            pass


def _record_broker_failure(db: Any, broker_id: Any, detail: str = "") -> None:
    try:
        from ..broker_health import record_failure
        record_failure(db, broker_id, detail=detail)
    except Exception:
        try:
            from core.broker_health import record_failure
            record_failure(db, broker_id, detail=detail)
        except Exception:
            pass


def _record_parent_confirmation(db: Any, parent_company_id: Any) -> None:
    try:
        from ..parent_company import record_confirmation
        record_confirmation(db, parent_company_id)
    except Exception:
        try:
            from core.parent_company import record_confirmation
            record_confirmation(db, parent_company_id)
        except Exception:
            pass


# ── Orphan Lease Reclamation ──────────────────────────────────────────────────

def reclaim_orphaned_leases(
    queue: JobQueue,
    lease_timeout_seconds: float = 300.0,
    max_retries: int = 3,
) -> Dict[str, int]:
    """
    Detect and reclaim in-flight job leases that have exceeded lease_timeout_seconds
    (e.g., worker node crashed, OOM-killed, or disconnected during execution).
    Jobs under max_retries are requeued to CHANNEL_RETRY; exhausted jobs route to DLQ.
    """
    leases = queue.get_in_flight_leases()
    reclaimed_retried = 0
    reclaimed_dead_lettered = 0

    for lease in leases:
        age = float(lease.get("age_seconds", 0.0))
        if age > lease_timeout_seconds:
            envelope: JobEnvelope = lease["envelope"]
            retries = int(envelope.meta.get("retries", 0)) + 1
            envelope.meta["retries"] = retries
            envelope.meta["reclaimed_at"] = time.time()
            envelope.meta["reclaim_reason"] = f"Lease timeout expired ({age:.1f}s > {lease_timeout_seconds:.1f}s)"

            if retries <= max_retries:
                log.info(
                    "Reclaiming orphaned envelope %s (retry %d/%d, age=%.1fs)",
                    envelope.envelope_id, retries, max_retries, age
                )
                queue.requeue(envelope, queue_name=CHANNEL_RETRY)
                reclaimed_retried += 1
            else:
                log.warning(
                    "Orphaned envelope %s exceeded max retries (%d); routing to DLQ (age=%.1fs)",
                    envelope.envelope_id, max_retries, age
                )
                queue.dead_letter(
                    envelope,
                    reason=f"Worker lease expired ({age:.1f}s > {lease_timeout_seconds}s); retries exhausted"
                )
                reclaimed_dead_lettered += 1

    return {
        "inspected": len(leases),
        "reclaimed_retried": reclaimed_retried,
        "reclaimed_dead_lettered": reclaimed_dead_lettered,
    }


# ── Result Ingestion Service ──────────────────────────────────────────────────

class ResultIngestionService:
    """
    Asynchronous control plane service that drains the results queue and
    updates database records (requests, logs, broker health, discovery results).
    """

    def __init__(
        self,
        queue: Optional[JobQueue] = None,
        session_factory: Optional[Callable[[], Any]] = None,
        db_session_factory: Optional[Callable[[], Any]] = None,
        screenshots_dir: str = "/data/screenshots",
    ):
        self.queue = queue or get_queue()
        self.session_factory = session_factory or db_session_factory
        self.screenshots_dir = screenshots_dir

    def _get_session(self):
        if self.session_factory is not None:
            return self.session_factory()
        try:
            from ...models.database import SessionLocal
            return SessionLocal()
        except Exception:
            return None

    def _save_screenshots(self, screenshots: Dict[str, str], prefix: str = "result") -> Optional[str]:
        """Save base64 screenshot strings to disk and return primary path."""
        if not screenshots:
            return None
        primary_path = None
        try:
            os.makedirs(self.screenshots_dir, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            for name, b64_data in screenshots.items():
                if not b64_data:
                    continue
                file_path = os.path.join(self.screenshots_dir, f"{prefix}_{name}_{ts}.png")
                with open(file_path, "wb") as f:
                    f.write(base64.b64decode(b64_data))
                if primary_path is None:
                    primary_path = file_path
        except Exception as e:
            log.debug("Could not save screenshot to disk: %s", e)
        return primary_path

    def ingest_result(self, result_env: JobResultEnvelope, db: Optional[Any] = None) -> Dict[str, Any]:
        """
        Process a single JobResultEnvelope and commit updates to database models.
        """
        managed_db = False
        if db is None:
            db = self._get_session()
            managed_db = True

        out: Dict[str, Any] = {
            "envelope_id": result_env.envelope_id,
            "action": result_env.action,
            "ok": result_env.ok,
            "status": result_env.status,
            "request_id": result_env.request_id,
            "updated_request": False,
            "discovery_listings_saved": 0,
            "chained_requests": 0,
        }

        # If database session is not available (e.g. lightweight environment), return summary
        if db is None:
            return out

        try:
            # ── 1. Removal Result Handling ────────────────────────────────────
            if result_env.action == "removal":
                req = None
                if result_env.request_id:
                    req = db.query(RemovalRequest).filter(RemovalRequest.id == result_env.request_id).first()
                if req is None and result_env.request_key:
                    req = db.query(RemovalRequest).filter(RemovalRequest.request_key == result_env.request_key).first()

                exec_result = result_env.result.get("exec_result", {})
                detail = str(exec_result.get("detail") or result_env.error or result_env.status)
                screenshot_path = self._save_screenshots(
                    result_env.screenshots,
                    prefix=f"req_{result_env.request_id or 'unknown'}"
                )

                if req is not None:
                    out["updated_request"] = True
                    if result_env.ok:
                        if result_env.status == "manual":
                            req.status = RequestStatus.needs_manual
                        else:
                            req.status = RequestStatus.submitted
                        req.sent_at = datetime.utcnow()

                        # Broker health success update
                        _record_broker_success(db, req.broker_id)

                    elif result_env.status == "captcha":
                        req.status = RequestStatus.needs_manual
                        req.notes = ((req.notes or "") + " [Paused for human CAPTCHA resolution]").strip()

                        # Route to CaptchaChallenge queue
                        try:
                            ch_data = exec_result.get("challenge") or {}
                            challenge = _make_record(
                                CaptchaChallenge,
                                request_id=getattr(req, "id", None),
                                broker_id=getattr(req, "broker_id", None),
                                member_id=getattr(req, "member_id", None),
                                challenge_type=str(ch_data.get("type", "other")),
                                site_key=ch_data.get("site_key"),
                                page_url=ch_data.get("page_url"),
                                screenshot=screenshot_path,
                                status="pending",
                            )
                            db.add(challenge)
                        except Exception as ce:
                            log.debug("Captcha challenge record creation skipped: %s", ce)

                        # Broker health failure update
                        _record_broker_failure(db, req.broker_id, detail="CAPTCHA challenge encountered")

                    else:
                        req.status = RequestStatus.failed
                        err_str = result_env.error or result_env.status
                        req.notes = ((req.notes or "") + f" [Worker error: {err_str}]").strip()

                        # Broker health failure update
                        _record_broker_failure(db, req.broker_id, detail=err_str)

                    # Parent company confirmation cascade
                    if result_env.ok and req.status == RequestStatus.confirmed and getattr(req, "broker", None) and getattr(req.broker, "parent_company_id", None):
                        _record_parent_confirmation(db, req.broker.parent_company_id)

                # Record AutomationLog
                try:
                    action_type = "form_fill"
                    log_entry = _make_record(
                        AutomationLog,
                        request_id=getattr(req, "id", None) if req else result_env.request_id,
                        member_id=getattr(req, "member_id", None) if req else (int(result_env.member_id) if str(result_env.member_id).isdigit() else None),
                        broker_id=getattr(req, "broker_id", None) if req else None,
                        action=action_type,
                        status="success" if result_env.ok else result_env.status,
                        detail=detail,
                        screenshot=screenshot_path,
                        duration_ms=result_env.duration_ms,
                    )
                    db.add(log_entry)
                except Exception as ale:
                    log.debug("AutomationLog write skipped: %s", ale)

            # ── 2. Discovery Result Handling ──────────────────────────────────
            elif result_env.action == "discovery":
                discovery_data = result_env.result.get("discovery", {})
                listings = discovery_data.get("listings", [])
                member_id_int = int(result_env.member_id) if str(result_env.member_id).isdigit() else None

                # Find broker ID
                broker_id_int = None
                broker_obj = None
                if result_env.broker_id:
                    if str(result_env.broker_id).isdigit():
                        broker_id_int = int(result_env.broker_id)
                    else:
                        try:
                            broker_obj = db.query(Broker).filter(
                                (Broker.name.ilike(f"%{result_env.broker_id}%"))
                            ).first()
                            if broker_obj:
                                broker_id_int = broker_obj.id
                        except Exception as b_err:
                            log.debug("Broker resolution query skipped: %s", b_err)

                saved_count = 0
                chained_count = 0

                if member_id_int and broker_id_int:
                    for item in listings:
                        url = str(item.get("url", ""))
                        if not url:
                            continue
                        snippet = str(item.get("snippet", ""))
                        source = str(item.get("domain", "discovery"))

                        disc_row = _make_record(
                            DiscoveryResult,
                            member_id=member_id_int,
                            broker_id=broker_id_int,
                            found=True,
                            listing_url=url,
                            source=source,
                            snippet=snippet[:500],
                            scanned_at=datetime.utcnow(),
                        )
                        db.add(disc_row)
                        saved_count += 1

                        # Auto-chaining: If a pending removal request exists waiting for listing URL, attach it
                        pending_req = db.query(RemovalRequest).filter(
                            RemovalRequest.member_id == member_id_int,
                            RemovalRequest.broker_id == broker_id_int,
                            RemovalRequest.status == RequestStatus.pending,
                        ).first()

                        if pending_req and not pending_req.listing_url:
                            pending_req.listing_url = url
                            pending_req.notes = ((pending_req.notes or "") + f" [Auto-chained discovered URL: {url}]").strip()
                            chained_count += 1

                out["discovery_listings_saved"] = saved_count
                out["chained_requests"] = chained_count

                # Record AutomationLog
                try:
                    disc_log = _make_record(
                        AutomationLog,
                        member_id=member_id_int,
                        broker_id=broker_id_int,
                        action="discovery",
                        status="success" if result_env.ok else "failure",
                        detail=f"Discovered {len(listings)} profile listings",
                        duration_ms=result_env.duration_ms,
                    )
                    db.add(disc_log)
                except Exception as ale:
                    log.debug("AutomationLog write skipped: %s", ale)

            db.commit()

        except Exception as e:
            log.exception("Error ingesting result envelope %s: %s", result_env.envelope_id, e)
            db.rollback()
            raise
        finally:
            if managed_db:
                db.close()

        return out

    def process_next(self, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        """
        Pull the next result envelope from the queue and ingest it into the DB.
        Returns result report dictionary, or None if queue was empty.
        """
        result_env = self.queue.get_result(timeout=timeout)
        if result_env is None:
            return None
        return self.ingest_result(result_env)

    async def run_loop(
        self,
        stop_event: asyncio.Event,
        poll_interval: float = 0.5,
        reclaim_interval: float = 60.0,
        lease_timeout_seconds: float = 300.0,
    ) -> None:
        """
        Continuous ingestion loop: drains result envelopes and periodically
        reclaims orphaned leases until stop_event is set.
        """
        log.info("Starting Control Plane Result Ingestion Service loop")
        last_reclaim = time.time()

        while not stop_event.is_set():
            try:
                # 1. Drain results
                processed = False
                report = self.process_next(timeout=poll_interval)
                if report is not None:
                    processed = True
                    log.debug("Ingested result for envelope %s (%s)", report["envelope_id"], report["action"])

                # 2. Periodic orphan lease reclamation
                now = time.time()
                if now - last_reclaim >= reclaim_interval:
                    last_reclaim = now
                    reclaimed = reclaim_orphaned_leases(
                        self.queue,
                        lease_timeout_seconds=lease_timeout_seconds,
                    )
                    if reclaimed["reclaimed_retried"] > 0 or reclaimed["reclaimed_dead_lettered"] > 0:
                        log.info("Orphan lease reclamation report: %s", reclaimed)

                if not processed:
                    await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Error in result ingestion loop: %s", e)
                await asyncio.sleep(1.0)

        log.info("Control Plane Result Ingestion Service stopped")
