"""
Background scheduler — three APScheduler jobs wired to real engines.
"""

import asyncio, json, imaplib, email, re, logging, threading
from datetime import datetime, timedelta
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from ..models.database import (
    SessionLocal, FamilyMember, RemovalRequest, RequestStatus,
    MemberScheduleConfig, SchedulerRun, EmailLog, init_db
)
from .settings_store import load_settings, decrypt_password

log = logging.getLogger(__name__)
_scheduler: Optional[BackgroundScheduler] = None
UUID_RE = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE
)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
    return _scheduler


def start_scheduler():
    init_db()
    s   = get_scheduler()
    if s.running: return
    cfg = load_settings()
    sc  = cfg.get("scheduler", {})

    # ── Maintenance jobs: run whether or not opt-outs are scheduled ──
    # Daily certificate check (LDAP, SIP2, SAML IdP): dashboard alerts + one
    # admin email per milestone, before sign-in breaks.
    s.add_job(cert_check_job, IntervalTrigger(hours=24), id="cert_check",
              replace_existing=True, misfire_grace_time=3600,
              next_run_time=datetime.utcnow() + timedelta(minutes=2))

    # Distributed worker fleet: result ingestion and orphan lease reclamation
    s.add_job(result_ingestion_job, IntervalTrigger(seconds=30), id="result_ingestion",
              replace_existing=True, misfire_grace_time=60,
              next_run_time=datetime.utcnow() + timedelta(seconds=15))

    if not sc.get("enabled", False):
        s.start()
        log.info("Opt-out scheduling disabled — maintenance jobs only")
        return

    tz         = sc.get("timezone", "America/Chicago")
    poll_mins  = cfg.get("email", {}).get("poll_interval_minutes", 15)

    # ── Opt-out job scheduling based on spread mode ──
    # Modes:
    #   burst       — all at run_time (default, original behavior)
    #   window      — spread evenly across a start→end hour window
    #   rate        — run every N minutes, capped per hour, all day
    #   distributed — small batches spread across 24 hours
    spread_mode = sc.get("spread_mode", "burst")

    if spread_mode == "burst":
        h, m = map(int, sc.get("run_time", "02:00").split(":"))
        s.add_job(
            daily_optout_job,
            CronTrigger(hour=h, minute=m, timezone=tz),
            id="optout_burst", replace_existing=True, misfire_grace_time=3600,
        )
        log.info(f"Opt-out mode: burst at {h:02d}:{m:02d} {tz}")

    elif spread_mode == "window":
        # Spread across [window_start, window_end] hours, firing every window_interval minutes
        start_h  = int(sc.get("window_start_hour", 22))   # 10pm
        end_h    = int(sc.get("window_end_hour", 6))      # 6am
        interval = int(sc.get("window_interval_minutes", 30))
        # Build the list of hours in the window (handles overnight wrap)
        hours = _hours_in_window(start_h, end_h)
        hour_expr = ",".join(str(hh) for hh in hours)
        s.add_job(
            windowed_optout_job,
            CronTrigger(hour=hour_expr, minute=f"*/{interval}", timezone=tz),
            id="optout_window", replace_existing=True, misfire_grace_time=600,
        )
        log.info(f"Opt-out mode: window {start_h:02d}:00–{end_h:02d}:00 {tz} every {interval}m")

    elif spread_mode == "rate":
        # Run every N minutes continuously, respecting a per-hour cap
        interval = int(sc.get("rate_interval_minutes", 20))
        s.add_job(
            rate_limited_optout_job,
            IntervalTrigger(minutes=interval),
            id="optout_rate", replace_existing=True, misfire_grace_time=300,
            next_run_time=datetime.utcnow() + timedelta(minutes=1),
        )
        log.info(f"Opt-out mode: rate-limited every {interval}m")

    elif spread_mode == "distributed":
        # Small batches spread across all 24 hours
        interval = int(sc.get("distributed_interval_minutes", 60))
        s.add_job(
            distributed_optout_job,
            IntervalTrigger(minutes=interval),
            id="optout_distributed", replace_existing=True, misfire_grace_time=600,
            next_run_time=datetime.utcnow() + timedelta(minutes=2),
        )
        log.info(f"Opt-out mode: distributed every {interval}m across 24h")

    # ── Recheck job (always burst, 30 min after the primary opt-out time) ──
    rh_base, rm_base = map(int, sc.get("run_time", "02:00").split(":"))
    rh, rm = (rh_base + (rm_base + 30) // 60) % 24, (rm_base + 30) % 60
    s.add_job(recheck_job, CronTrigger(hour=rh, minute=rm, timezone=tz),
              id="daily_recheck", replace_existing=True, misfire_grace_time=3600)

    # ── Email monitor ──
    s.add_job(email_monitor_job, IntervalTrigger(minutes=poll_mins),
              id="email_monitor", replace_existing=True, next_run_time=datetime.utcnow())

    s.start()
    log.info(f"Scheduler started — spread_mode={spread_mode}, email poll every {poll_mins}m")


def cert_check_job():
    """Daily: LDAP / SIP2 / SAML certificate checks + milestone emails to admins."""
    try:
        from .cert_monitor import run_cert_checks
        run_cert_checks()
    except Exception as e:
        log.error("Certificate check failed: %s", e)


def _hours_in_window(start_h: int, end_h: int) -> list:
    """Return list of hours in [start, end], handling overnight wrap (e.g. 22→6)."""
    if start_h <= end_h:
        return list(range(start_h, end_h + 1))
    # Overnight: start_h..23, then 0..end_h
    return list(range(start_h, 24)) + list(range(0, end_h + 1))


def stop_scheduler():
    s = get_scheduler()
    if s.running: s.shutdown(wait=False)


def reload_scheduler():
    stop_scheduler()
    global _scheduler; _scheduler = None
    start_scheduler()


def get_next_run_times() -> dict:
    s = get_scheduler()
    if not s.running: return {}
    return {j.id: j.next_run_time.isoformat() if j.next_run_time else None for j in s.get_jobs()}


# ── Job 1: daily opt-out ──────────────────────────────────────────────────────

def _select_pending_batch(db, cfg, max_this_run: int) -> list:
    """
    Select up to max_this_run pending request IDs, respecting the daily
    system cap, per-member caps, and per-member enable flags.
    Shared by all spread modes.
    """
    sc      = cfg.get("scheduler", {})
    sys_max = sc.get("max_optouts_per_day", 20)
    dispatch_order = sc.get("dispatch_order", "priority")  # priority | fifo | easy_first

    sent_today = _count_sent_today(db)
    daily_remaining = max(0, sys_max - sent_today)
    if daily_remaining == 0:
        return []

    # This run is limited by BOTH the per-run cap and the daily remaining cap
    run_limit = min(max_this_run, daily_remaining)

    pending = (
        db.query(RemovalRequest)
        .filter(RemovalRequest.status == RequestStatus.pending)
        .all()
    )

    # Order the pending pool by the configured strategy (default: worst
    # offenders / highest data exposure first), so a member's most sensitive
    # exposures clear first even when the full opt-out spans many days.
    from .broker_priority import order_pending
    pending = order_pending(pending, strategy=dispatch_order)

    batch_ids = []
    for req in pending:
        if len(batch_ids) >= run_limit:
            break
        # Skip brokers disabled by an admin or auto-disabled by the health
        # monitor — a broken broker never consumes a member's daily budget.
        if req.broker and (not req.broker.enabled or getattr(req.broker, "is_test", False)):
            continue
        # Skip requests currently paused for human CAPTCHA resolution (Item 4)
        if req.notes and "Paused for human CAPTCHA" in req.notes:
            continue
        mc = req.member.schedule_config
        if mc and not mc.enabled:
            continue
        mem_max        = (mc.max_optouts_per_day if mc and mc.max_optouts_per_day else sys_max)
        mem_sent_today = _count_sent_today_for_member(db, req.member_id)
        if mem_sent_today >= mem_max:
            continue
        batch_ids.append(req.id)

    return batch_ids


def _run_optout_with_limit(run_type: str, max_this_run: int):
    """
    Core opt-out execution shared by all spread modes.
    Selects a batch (capped at max_this_run), runs it, logs a SchedulerRun.
    """
    db  = SessionLocal()
    run = SchedulerRun(run_type=run_type, status="running")
    db.add(run); db.commit()
    run_id = run.id
    errors = []
    sent   = 0

    try:
        cfg = load_settings()
        sc  = cfg.get("scheduler", {})

        if sc.get("pause_before_send", True):
            log.info("pause_before_send=True — skipping auto send")
            _finish_run(db, run_id, status="done", sent=0)
            return

        batch_ids = _select_pending_batch(db, cfg, max_this_run)

        # ── Email-First Parent Company Optimization (Item 10) ──
        # Check if any requests in the batch belong to parent companies with optout_emails.
        # Send one bulk email per (member, parent) instead of launching headless browsers.
        parent_covered_ids = set()
        if batch_ids:
            try:
                from .optout_engine import process_pending_parent_company_optouts
                p_res = process_pending_parent_company_optouts(db, cfg, batch_request_ids=batch_ids)
                parent_covered_ids = set(p_res.get("covered_request_ids", []))
                sent += len(parent_covered_ids)
                if p_res.get("errors"):
                    errors.extend(p_res["errors"])
                if parent_covered_ids:
                    log.info("Parent-company email batch covered %d requests (%d emails sent)",
                             len(parent_covered_ids), p_res.get("sent_emails", 0))
            except Exception as e:
                log.error("Parent-company batch opt-out error: %s", e)
                errors.append(f"Parent batch error: {e}")

        remaining_batch_ids = [rid for rid in batch_ids if rid not in parent_covered_ids]

        if remaining_batch_ids:
            dist_cfg = cfg.get("distributed", {})
            use_distributed = dist_cfg.get("enabled", False) or bool(os.getenv("REDIS_URL"))
            if use_distributed:
                enqueue_res = enqueue_pending_optouts(
                    db, remaining_batch_ids, secret_key=cfg.get("secret_key")
                )
                sent += enqueue_res.get("enqueued", 0)
                errors.extend(enqueue_res.get("errors", []))
            else:
                db.close()
                from .optout_engine import run_optout_batch
                result = asyncio.run(run_optout_batch(remaining_batch_ids))
                sent   += result.get("sent", 0)
                errors.extend(result.get("errors", []))
                db = SessionLocal()

        _finish_run(db, run_id, status="done", sent=sent, errors=errors)

    except Exception as e:
        errors.append(str(e))
        log.error(f"Opt-out job error ({run_type}): {e}")
        try:
            _finish_run(db, run_id, status="error", sent=sent, errors=errors)
        except Exception:
            pass
    finally:
        try: db.close()
        except Exception: pass


def _finish_run(db, run_id, status, sent, errors=None):
    run = db.query(SchedulerRun).filter(SchedulerRun.id == run_id).first()
    if run:
        run.optouts_sent = sent
        run.status       = status
        run.finished_at  = datetime.utcnow()
        run.errors       = json.dumps(errors) if errors else None
        db.commit()


# ── Mode-specific job entry points ────────────────────────────────────────────

def daily_optout_job():
    """Burst mode — send up to the full daily cap in one run."""
    cfg = load_settings()
    sys_max = cfg.get("scheduler", {}).get("max_optouts_per_day", 20)
    _run_optout_with_limit("optout", sys_max)


def windowed_optout_job():
    """
    Window mode — spread the daily cap across the window.
    Each fire sends daily_cap / number_of_slots, so the total across the
    window equals the daily cap.
    """
    cfg = load_settings()
    sc  = cfg.get("scheduler", {})
    sys_max  = sc.get("max_optouts_per_day", 20)
    start_h  = int(sc.get("window_start_hour", 22))
    end_h    = int(sc.get("window_end_hour", 6))
    interval = int(sc.get("window_interval_minutes", 30))

    n_hours = len(_hours_in_window(start_h, end_h))
    slots   = max(1, (n_hours * 60) // interval)
    per_slot = max(1, sys_max // slots)
    _run_optout_with_limit("optout", per_slot)


def rate_limited_optout_job():
    """
    Rate mode — send a fixed number per fire, continuously through the day.
    The per-fire amount is derived from the hourly cap.
    """
    cfg = load_settings()
    sc  = cfg.get("scheduler", {})
    per_hour = int(sc.get("rate_per_hour", 5))
    interval = int(sc.get("rate_interval_minutes", 20))
    fires_per_hour = max(1, 60 // interval)
    per_fire = max(1, per_hour // fires_per_hour)
    _run_optout_with_limit("optout", per_fire)


def distributed_optout_job():
    """
    Distributed mode — small batches spread evenly across 24 hours.
    Per-fire amount = daily_cap / fires_per_day.
    """
    cfg = load_settings()
    sc  = cfg.get("scheduler", {})
    sys_max  = sc.get("max_optouts_per_day", 20)
    interval = int(sc.get("distributed_interval_minutes", 60))
    fires_per_day = max(1, (24 * 60) // interval)
    per_fire = max(1, sys_max // fires_per_day)
    _run_optout_with_limit("optout", per_fire)


def _count_sent_today(db):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(RemovalRequest).filter(
        RemovalRequest.sent_at >= today,
        RemovalRequest.status.in_([RequestStatus.sent, RequestStatus.confirmed]),
    ).count()


def _count_sent_today_for_member(db, member_id):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(RemovalRequest).filter(
        RemovalRequest.member_id == member_id,
        RemovalRequest.sent_at >= today,
        RemovalRequest.status.in_([RequestStatus.sent, RequestStatus.confirmed]),
    ).count()


# ── Job 2: email monitor ──────────────────────────────────────────────────────

def _poll_imap_mailbox(ec: dict, db: Session, cfg: dict, is_grace_period: bool = False) -> tuple:
    errors = []
    matched = 0
    if not ec.get("imap_host") or not ec.get("imap_password_enc"):
        return 0, []

    from .memory_hygiene import ephemeral_secret
    folder  = ec.get("imap_folder", "INBOX")

    try:
        if ec.get("imap_ssl", True):
            conn = imaplib.IMAP4_SSL(ec["imap_host"], ec.get("imap_port", 993))
        else:
            conn = imaplib.IMAP4(ec["imap_host"], ec.get("imap_port", 143))
        with ephemeral_secret(ec["imap_password_enc"]) as imap_pw:
            conn.login(ec["imap_user"], imap_pw)
        conn.select(folder)

        _, msg_ids = conn.search(None, "UNSEEN")
        for mid in msg_ids[0].split():
            try:
                _, data = conn.fetch(mid, "(RFC822)")
                msg  = email.message_from_bytes(data[0][1])
                subj = msg.get("Subject", "")
                body = _get_body(msg)
                text = f"{subj} {body}"

                # Let a plugin parse the email first (custom broker confirmation
                # formats that don't use the standard UUID key). Falls back to
                # the default UUID matcher if no plugin handles it.
                plugin_handled = False
                try:
                    from ..plugins.hooks import try_plugin_parse_email
                    pending_keys = [r.request_key for r in db.query(RemovalRequest).filter(
                        RemovalRequest.status == RequestStatus.sent).all() if r.request_key]
                    presult = try_plugin_parse_email(
                        {"message_id": str(mid), "subject": subj, "from_addr": msg.get("From", ""),
                         "body_text": body, "body_html": ""},
                        pending_keys,
                    )
                    if presult and presult.get("handled") and presult.get("matched"):
                        pkey = presult.get("matched_key")
                        req  = db.query(RemovalRequest).filter(RemovalRequest.request_key == pkey).first()
                        if req and req.status == RequestStatus.sent:
                            req.status = RequestStatus.confirmed
                            req.confirmed_at = datetime.utcnow()
                            recheck_days = cfg.get("scheduler", {}).get("recheck_interval_days", 90)
                            req.recheck_after = datetime.utcnow() + timedelta(days=recheck_days)
                            db.add(EmailLog(request_id=req.id, direction="received",
                                            subject=subj[:500], body_snippet=body[:500], matched_key=pkey))
                            db.commit()
                            matched += 1
                            plugin_handled = True
                            from ..plugins.hooks import fire_event
                            via_label = "grace_plugin" if is_grace_period else "plugin"
                            fire_event("confirmation_received", entity_id=str(req.id),
                                       data={"broker": req.broker.name, "via": via_label})
                            log.info(f"Matched ({via_label}): {req.broker.name} (member_id={req.member_id})")
                except Exception as _pe:
                    log.debug("plugin email parse skipped: %s", _pe)

                if not plugin_handled:
                    for key in set(UUID_RE.findall(text)):
                        matching_reqs = db.query(RemovalRequest).filter(
                            RemovalRequest.request_key == key,
                            RemovalRequest.status == RequestStatus.sent,
                        ).all()
                        if matching_reqs:
                            recheck_days = cfg.get("scheduler", {}).get("recheck_interval_days", 90)
                            recheck_dt = datetime.utcnow() + timedelta(days=recheck_days)
                            now = datetime.utcnow()
                            parent_ids_to_confirm = set()

                            for req in matching_reqs:
                                req.status = RequestStatus.confirmed
                                req.confirmed_at = now
                                req.recheck_after = recheck_dt
                                db.add(EmailLog(
                                    request_id=req.id, direction="received",
                                    subject=subj[:500], body_snippet=body[:500], matched_key=key,
                                ))
                                matched += 1
                                via_label = "grace_uuid" if is_grace_period else "uuid"
                                log.info(f"Matched ({via_label}): {req.broker.name} (member_id={req.member_id})")
                                if req.broker and req.broker.parent_company_id:
                                    parent_ids_to_confirm.add(req.broker.parent_company_id)
                                try:
                                    from ..plugins.hooks import fire_event
                                    fire_event("confirmation_received", entity_id=str(req.id),
                                               data={"broker": req.broker.name, "via": via_label})
                                except Exception:
                                    pass

                            db.commit()

                            # Record confirmation for parent companies
                            if parent_ids_to_confirm:
                                try:
                                    from . import parent_company as pcmod
                                    for pid in parent_ids_to_confirm:
                                        pcmod.record_confirmation(db, pid)
                                except Exception as _pce:
                                    log.debug("parent confirmation tracking error: %s", _pce)

                conn.store(mid, "+FLAGS", "\\Seen")
            except Exception as e:
                errors.append(f"Message {mid}: {e}")

        conn.logout()
    except Exception as e:
        errors.append(str(e))
        log.warning("IMAP polling error (%s): %s", "grace_period" if is_grace_period else "primary", e)

    return matched, errors


def email_monitor_job():
    db  = SessionLocal()
    run = SchedulerRun(run_type="email_poll", status="running")
    db.add(run); db.commit()
    errors = []; matched = 0

    try:
        cfg = load_settings(); ec = cfg.get("email", {})

        # 1. Primary Inbox Polling
        if ec.get("imap_host") and ec.get("imap_password_enc"):
            succ, errs = _poll_imap_mailbox(ec, db, cfg, is_grace_period=False)
            matched += succ
            errors.extend(errs)

        # 2. Mode-Switching Grace Period Dual-Inbox Polling (Roadmap Item 11)
        try:
            from .email_grace import get_email_grace_status
            grace = get_email_grace_status(cfg)
            if grace.get("active") and grace.get("previous_config"):
                prev_ec = grace["previous_config"]
                if prev_ec.get("imap_host") and prev_ec.get("imap_password_enc"):
                    log.info(
                        "Polling previous mailbox during mode grace period (%d days remaining)...",
                        grace.get("days_remaining", 0)
                    )
                    g_succ, g_errs = _poll_imap_mailbox(prev_ec, db, cfg, is_grace_period=True)
                    matched += g_succ
                    if g_errs:
                        log.debug("Grace period inbox polling warnings: %s", g_errs)
        except Exception as ge:
            log.debug("Grace period inbox check skipped: %s", ge)

        run.emails_matched = matched; run.status = "done"

    except Exception as e:
        errors.append(str(e)); run.status = "error"
        log.error(f"Email monitor error: {e}")
    finally:
        run.errors = json.dumps(errors) if errors else None
        run.finished_at = datetime.utcnow()
        db.commit(); db.close()


def _get_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try: return part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception: pass
        return ""
    try: return msg.get_payload(decode=True).decode("utf-8", errors="replace")
    except Exception: return ""


# ── Job 3: recheck scanner ────────────────────────────────────────────────────

def recheck_job():
    db  = SessionLocal()
    run = SchedulerRun(run_type="recheck", status="running")
    db.add(run); db.commit()
    errors = []; queued = 0

    try:
        cfg = load_settings()
        if not cfg.get("scheduler", {}).get("auto_recheck", True):
            run.status = "done"; run.finished_at = datetime.utcnow(); db.commit(); return

        overdue = db.query(RemovalRequest).filter(
            RemovalRequest.status == RequestStatus.confirmed,
            RemovalRequest.recheck_after <= datetime.utcnow(),
        ).all()

        for req in overdue:
            req.status = RequestStatus.pending
            req.confirmed_at = None; req.sent_at = None
            queued += 1
        db.commit()
        run.rechecks_queued = queued; run.status = "done"
        log.info(f"Recheck: {queued} re-queued")

    except Exception as e:
        errors.append(str(e)); run.status = "error"
        log.error(f"Recheck job error: {e}")
    finally:
        run.errors = json.dumps(errors) if errors else None
        run.finished_at = datetime.utcnow()
        db.commit(); db.close()


# ── Distributed Scheduling & Fleet Orchestration (Phase 7.4) ─────────────────

def enqueue_pending_optouts(
    db: Session,
    batch_request_ids: list[int],
    queue = None,
    secret_key = None,
) -> dict:
    """
    Compile pending removal requests into signed JobEnvelopes and push to JobQueue.
    Decouples scheduler from in-process execution for the distributed worker fleet.
    """
    from .distributed.envelope import create_removal_envelope
    from .distributed.queue import get_queue
    from .interpreter.script_bridge import get_or_build_broker_spec
    from .interpreter import compile_job
    from .combinations import _get_values, _parse_address

    q = queue or get_queue(secret_key=secret_key)
    enqueued = 0
    errors = []

    for req_id in batch_request_ids:
        try:
            req = db.query(RemovalRequest).filter(RemovalRequest.id == req_id).first()
            if not req:
                continue

            broker = req.broker
            member = req.member
            script = getattr(broker, "script", None)

            spec = get_or_build_broker_spec(broker, script=script, db=db)

            # Resolve member fields
            def first(kind):
                vals = _get_values(member, kind, 1)
                return vals[0] if vals else ""

            raw_addr = first("address")
            p = _parse_address(raw_addr) if raw_addr else {"address": "", "city": "", "state": "", "zip": ""}
            parts = (member.full_name or "").split()
            member_fields = {
                "full_name": member.full_name or first("name"),
                "formal_name": getattr(member, "formal_name", "") or member.full_name or "",
                "first_name": parts[0] if parts else "",
                "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
                "email": first("email"),
                "phone": first("phone"),
                "address": p.get("address") or raw_addr,
                "city": p.get("city", ""),
                "state": p.get("state", ""),
                "zip": p.get("zip", ""),
            }

            job = compile_job(spec, member_fields, member_id=str(member.id))
            priority = "high" if getattr(broker, "priority", 3) >= 4 else "normal"

            env = create_removal_envelope(
                job=job,
                member_fields=member_fields,
                request_id=req.id,
                request_key=req.request_key,
                priority=priority,
                secret_key=secret_key,
            )

            q.enqueue(env)
            req.status = RequestStatus.submitted
            enqueued += 1

        except Exception as e:
            log.error("Failed to enqueue request %d: %s", req_id, e)
            errors.append(f"Request {req_id}: {e}")

    db.commit()
    return {
        "enqueued": enqueued,
        "request_ids": batch_request_ids,
        "errors": errors,
    }


def enqueue_pending_discoveries(
    db: Session,
    member_ids: list[int],
    broker_ids: Optional[list[int]] = None,
    queue = None,
    secret_key = None,
) -> dict:
    """
    Build and enqueue discovery query envelopes for specified family members across brokers.
    """
    from .distributed.envelope import create_discovery_envelope
    from .distributed.queue import get_queue
    from .combinations import _get_values, _parse_address
    from ..models.database import Broker

    q = queue or get_queue(secret_key=secret_key)
    enqueued = 0
    errors = []

    brokers = []
    if broker_ids:
        brokers = db.query(Broker).filter(Broker.id.in_(broker_ids)).all()
    else:
        brokers = db.query(Broker).filter(Broker.status != "disabled").all()

    for mem_id in member_ids:
        try:
            member = db.query(FamilyMember).filter(FamilyMember.id == mem_id).first()
            if not member:
                continue

            def first(kind):
                vals = _get_values(member, kind, 1)
                return vals[0] if vals else ""

            raw_addr = first("address")
            p = _parse_address(raw_addr) if raw_addr else {}
            name = member.full_name or first("name")
            city = p.get("city", "")
            state = p.get("state", "")

            for b in brokers:
                script = getattr(b, "script", None)
                query_criteria = {
                    "name": name,
                    "city": city,
                    "state": state,
                    "broker_domain": b.name.lower().replace(" ", "") + ".com" if not b.opt_out_url else None,
                    "search_url": script.search_url if script and script.search_url else b.opt_out_url,
                }

                env = create_discovery_envelope(
                    query_criteria=query_criteria,
                    broker_id=str(b.id),
                    broker_name=b.name,
                    member_id=str(member.id),
                    secret_key=secret_key,
                )
                q.enqueue(env)
                enqueued += 1

        except Exception as e:
            log.error("Failed to enqueue discoveries for member %d: %s", mem_id, e)
            errors.append(f"Member {mem_id}: {e}")

    return {
        "enqueued": enqueued,
        "member_ids": member_ids,
        "errors": errors,
    }


def result_ingestion_job():
    """
    APScheduler job to drain results from the distributed queue
    and perform periodic orphan lease reclamation.
    """
    from .distributed.ingestion import ResultIngestionService, reclaim_orphaned_leases
    from .distributed.queue import get_queue

    q = get_queue()
    service = ResultIngestionService(queue=q)

    # Ingest up to 50 pending results per cycle
    ingested = 0
    for _ in range(50):
        report = service.process_next(timeout=0.1)
        if report is None:
            break
        ingested += 1

    # Reclaim timed out worker leases
    reclaim_report = reclaim_orphaned_leases(q, lease_timeout_seconds=300.0)

    if ingested > 0 or reclaim_report.get("reclaimed_retried", 0) > 0:
        log.info(
            "Result ingestion cycle: %d results ingested, %d leases reclaimed",
            ingested, reclaim_report.get("reclaimed_retried", 0)
        )
