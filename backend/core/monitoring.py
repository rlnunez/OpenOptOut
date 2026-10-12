"""
Monitoring: health checks and a metrics endpoint for Uptime Kuma, Prometheus,
Grafana, Zabbix, Nagios and the like.

  GET /api/health          liveness: the app answers (public, unchanged)
  GET /api/health/ready    readiness: every check below, ok or not, in plain
                           words. 200 when all pass, 503 when one fails. Public:
                           it says nothing about anyone.
  GET /api/metrics         Prometheus text format. Needs the metrics token
                           (Authorization: Bearer ...) or a super admin.

Nothing here is personal: counts by status, timestamps, and the names of
checks. A check never reads anyone's details.

Every five minutes the health job runs the checks and sends the webhook events
health_problem / health_ok when the result changes (core/webhooks.py).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import shutil
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

log = logging.getLogger(__name__)
STARTED = time.time()
_last_state: Dict[str, Optional[bool]] = {"ok": None}


def data_dir() -> str:
    for p in (os.getenv("DATA_DIR", ""), "/data", os.path.dirname(os.path.abspath(
            os.getenv("SETTINGS_FILE", "./openoptout_settings.json")))):
        if p and os.path.isdir(p):
            return p
    return "."


# Every phrase a check can show, so the page can translate it (the
# extractor reads this table; scripts/extract_page_texts.py SERVER_TEXTS).
CHECK_TEXTS = {
    "database": "Database",
    "database_ok": "Answering.",
    "database_bad": "Not answering ({error}).",
    "scheduler": "Scheduled jobs",
    "scheduler_ok": "Running.",
    "scheduler_bad": "Not running, so nothing is sent or checked on schedule.",
    "runs": "Opt-out runs",
    "runs_ok": "No stuck or failed runs.",
    "runs_stuck": "{n} run(s) started over 6 hours ago and never finished.",
    "runs_error": "The last run stopped with an error. See System logs.",
    "inboxes": "Email inboxes",
    "inboxes_ok": "{n} connected, all checked recently.",
    "inboxes_bad": "{errors} inbox(es) can't be read, {late} not checked for over 2 hours.",
    "disk": "Disk space",
    "disk_ok": "{gb} GB free ({pct}%).",
    "disk_bad": "{gb} GB free ({pct}%). Free up space soon.",
    "backups": "Backups",
    "backups_ok": "Last backup worked.",
    "backups_none": "No backup yet.",
    "backups_bad": "The last backup didn't work. See Backups.",
    "log_forwarding": "Log forwarding",
    "log_forwarding_ok": "Sending.",
    "log_forwarding_bad": "Can't reach: {names}.",
}


def _check(name: str, ok: bool, text: str, **vars_) -> dict:
    """One check: English label and detail (for monitoring tools), plus the
    phrase key and values the page translates."""
    template = CHECK_TEXTS[text]
    return {"name": name, "label": CHECK_TEXTS[name], "ok": bool(ok),
            "detail": template.format(**vars_), "text": template, "vars": vars_}


def checks(db, settings: Optional[dict] = None) -> List[dict]:
    """Each check: {"name", "label", "ok", "detail", "text", "vars"}."""
    from sqlalchemy import text
    from ..models.database import SchedulerRun, Mailbox
    if settings is None:
        from .settings_store import load_settings
        settings = load_settings()
    out = []
    try:
        db.execute(text("SELECT 1"))
        out.append(_check("database", True, "database_ok"))
    except Exception as e:
        out.append(_check("database", False, "database_bad", error=type(e).__name__))
        return out

    try:
        from .scheduler import get_scheduler
        running = bool(get_scheduler().running)
    except Exception:
        running = False
    out.append(_check("scheduler", running, "scheduler_ok" if running else "scheduler_bad"))

    now = datetime.utcnow()
    stuck = db.query(SchedulerRun).filter(SchedulerRun.status == "running",
                                          SchedulerRun.started_at < now - timedelta(hours=6)).count()
    last = (db.query(SchedulerRun).filter(SchedulerRun.run_type == "optout")
            .order_by(SchedulerRun.started_at.desc()).first())
    if stuck:
        out.append(_check("runs", False, "runs_stuck", n=stuck))
    elif last is not None and last.status == "error":
        out.append(_check("runs", False, "runs_error"))
    else:
        out.append(_check("runs", True, "runs_ok"))

    boxes = db.query(Mailbox).filter(Mailbox.status == "connected").all()
    late = [b for b in boxes if b.last_polled_at and b.last_polled_at < now - timedelta(hours=2)]
    errors = db.query(Mailbox).filter(Mailbox.status == "error").count()
    if errors or late:
        out.append(_check("inboxes", False, "inboxes_bad", errors=errors, late=len(late)))
    else:
        out.append(_check("inboxes", True, "inboxes_ok", n=len(boxes)))

    try:
        du = shutil.disk_usage(data_dir())
        free_pct = du.free / du.total * 100 if du.total else 100
        ok = du.free > 1 << 30 or free_pct > 10
        out.append(_check("disk", ok, "disk_ok" if ok else "disk_bad",
                          gb=f"{du.free / (1 << 30):.1f}", pct=f"{free_pct:.0f}"))
    except Exception:
        pass

    try:
        from .backup import settings_of
        backups_on = bool(settings_of(settings).get("enabled"))
    except Exception:
        backups_on = False
    if backups_on:
        hist = settings.get("backups_history") or []
        if hist and not hist[0].get("ok"):
            out.append(_check("backups", False, "backups_bad"))
        else:
            out.append(_check("backups", True, "backups_ok" if hist else "backups_none"))

    try:
        from . import log_forwarding as lf
        dests = [d for d in lf.destinations(settings) if d.get("enabled", True)]
        bad = [d.get("name", "") for d in dests if lf.LAST_ERROR.get(d["id"])]
        if dests:
            out.append(_check("log_forwarding", not bad, "log_forwarding_bad" if bad else "log_forwarding_ok",
                              names=", ".join(bad)))
    except Exception:
        pass
    return out


def ready(db, settings: Optional[dict] = None) -> dict:
    c = checks(db, settings)
    return {"status": "ok" if all(x["ok"] for x in c) else "problem", "checks": c}


# ── Metrics ───────────────────────────────────────────────────────────────────

def _esc(v) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def metrics(db, settings: Optional[dict] = None) -> str:
    """Prometheus text exposition (version 0.0.4)."""
    from sqlalchemy import func
    from ..models.database import (RemovalRequest, Broker, BrokerHealth, CaptchaChallenge,
                                   FamilyMember, Mailbox, InstalledPlugin, SchedulerRun)
    from .version import get_version
    lines: List[str] = []

    def metric(name, kind, help_, samples):
        lines.append(f"# HELP {name} {help_}")
        lines.append(f"# TYPE {name} {kind}")
        for labels, value in samples:
            lab = ",".join(f'{k}="{_esc(v)}"' for k, v in labels.items())
            lines.append(f"{name}{{{lab}}} {value}" if lab else f"{name} {value}")

    metric("openoptout_up", "gauge", "1 while OpenOptOut answers.", [({}, 1)])
    metric("openoptout_build_info", "gauge", "The running version.", [({"version": get_version()}, 1)])
    metric("openoptout_uptime_seconds", "gauge", "Seconds since the app started.", [({}, round(time.time() - STARTED))])
    rows = db.query(RemovalRequest.status, func.count(RemovalRequest.id)).group_by(RemovalRequest.status).all()
    metric("openoptout_requests", "gauge", "Opt-out requests by status.",
           [({"status": getattr(s, "value", s)}, n) for s, n in rows])
    metric("openoptout_brokers", "gauge", "Brokers, turned on or off.",
           [({"enabled": "true"}, db.query(Broker).filter(Broker.enabled.is_(True)).count()),
            ({"enabled": "false"}, db.query(Broker).filter(Broker.enabled.is_(False)).count())])
    metric("openoptout_brokers_auto_disabled", "gauge", "Brokers turned off by the health monitor.",
           [({}, db.query(BrokerHealth).filter(BrokerHealth.auto_disabled.is_(True)).count())])
    metric("openoptout_captchas_waiting", "gauge", "CAPTCHAs waiting for a person.",
           [({}, db.query(CaptchaChallenge).filter(CaptchaChallenge.status == "pending").count())])
    metric("openoptout_family_members", "gauge", "People whose details are being removed.",
           [({}, db.query(FamilyMember).count())])
    metric("openoptout_inboxes", "gauge", "Connected email inboxes by state.",
           [({"status": s}, n) for s, n in db.query(Mailbox.status, func.count(Mailbox.id)).group_by(Mailbox.status).all()])
    metric("openoptout_plugins", "gauge", "Installed plugins by state.",
           [({"status": s or "unknown"}, n) for s, n in
            db.query(InstalledPlugin.status, func.count(InstalledPlugin.id)).group_by(InstalledPlugin.status).all()])
    last = {}
    for r in db.query(SchedulerRun.run_type, func.max(SchedulerRun.finished_at)).filter(
            SchedulerRun.status == "done").group_by(SchedulerRun.run_type).all():
        if r[1]:
            last[r[0]] = int((r[1] - datetime(1970, 1, 1)).total_seconds())
    metric("openoptout_job_last_success_timestamp_seconds", "gauge",
           "When each scheduled job last finished without an error (Unix time).",
           [({"job": k}, v) for k, v in sorted(last.items())])
    try:
        du = shutil.disk_usage(data_dir())
        metric("openoptout_disk_free_bytes", "gauge", "Free space where OpenOptOut keeps its data.", [({}, du.free)])
    except Exception:
        pass
    try:
        from . import log_forwarding as lf
        metric("openoptout_log_forwarded_total", "counter", "Log lines sent to log servers.", [({}, lf.STATS["sent"])])
        metric("openoptout_log_dropped_total", "counter", "Log lines that couldn't be sent.", [({}, lf.STATS["dropped"])])
    except Exception:
        pass
    try:
        from . import webhooks as wh
        metric("openoptout_webhooks_total", "counter", "Webhook messages by result.",
               [({"result": k}, v) for k, v in wh.STATS.items()])
    except Exception:
        pass
    return "\n".join(lines) + "\n"


# ── Metrics token ─────────────────────────────────────────────────────────────

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token(settings: dict) -> str:
    """A new metrics token; only its hash is stored. Shown once."""
    token = "oo_metrics_" + secrets.token_urlsafe(32)
    settings.setdefault("observability", {})["metrics_token_hash"] = _hash(token)
    return token


def token_ok(settings: dict, token: str) -> bool:
    want = (settings.get("observability") or {}).get("metrics_token_hash") or ""
    return bool(want and token) and hmac.compare_digest(want, _hash(token))


# ── The health job ────────────────────────────────────────────────────────────

def health_job() -> None:
    """Every five minutes: run the checks, and tell webhooks when the result
    changes (not on every run)."""
    from ..models.database import SessionLocal
    db = SessionLocal()
    try:
        r = ready(db)
    except Exception as e:
        r = {"status": "problem", "checks": [{"name": "app", "label": "App", "ok": False,
                                              "detail": type(e).__name__}]}
    finally:
        db.close()
    ok = r["status"] == "ok"
    prev = _last_state["ok"]
    _last_state["ok"] = ok
    if prev is None and ok:
        return
    if prev is ok:
        return
    from .webhooks import safe_notify
    if ok:
        safe_notify("health_ok", "Every check passes again.")
    else:
        bad = [c for c in r["checks"] if not c["ok"]]
        safe_notify("health_problem", " ".join(f"{c['label']}: {c['detail']}" for c in bad),
                    {"checks": ", ".join(c["name"] for c in bad)})
