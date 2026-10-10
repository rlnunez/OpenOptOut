"""Certificate monitor API (super admin): dashboard alerts + run-now."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.auth import require_super_admin
from ..core.access import require_permission
from ..core import cert_monitor as cm

router = APIRouter(prefix="/api/cert-monitor", tags=["cert-monitor"])


@router.get("/alerts")
def get_alerts(_: User = Depends(require_permission("certificates.view"))):
    """Certificates needing attention (for the dashboard banner)."""
    state = cm.load_state()
    return {"checked_at": state.get("checked_at"), "alerts": cm.alerts(state)}


@router.get("/status")
def get_status(_: User = Depends(require_permission("certificates.view"))):
    state = cm.load_state()
    return {"checked_at": state.get("checked_at"), "results": state.get("results", {})}


@router.get("/https-status")
def get_https_status(_: User = Depends(require_permission("certificates.view"))):
    """
    A live, on-demand read of OpenOptOut's own HTTPS certificate — separate
    from /run so it stays fast and side-effect-free (no email, no touching the
    other checks' state) for a "did this actually work?" button right after
    running scripts/enable-https.ps1 or .sh and restarting the containers.

    This is a read-only TLS handshake to the front-door container (caddy or
    traefik, per HTTPS_CHECK_HOST) over the internal
    Docker network the api container already has (the same thing the daily
    monitor does) — never a docker/host action. The api container deliberately
    has no docker socket and never runs docker compose itself: giving it that
    would mean anything that ever compromises the api container (a bug, or a
    malicious/broken plugin, given the plugin system) could reach the host's
    Docker daemon. Turning HTTPS on/off is a host-level step by design.
    """
    st = cm.https_cert_status()
    if st is None:
        return {"configured": False, "level": "none",
                "message": "HTTPS_MODE/DOMAIN aren't set — nothing to check yet. "
                           "Run scripts/enable-https.ps1 (Windows) or .sh (Linux/macOS), "
                           "then docker compose up -d --build."}
    return {"configured": True, **st}


@router.post("/run")
def run_now(db: Session = Depends(get_db), _: User = Depends(require_permission("certificates.view"))):
    """Run every certificate check now (also sends any due milestone reminders)."""
    out = cm.run_cert_checks(db=db)
    return {"results": out["results"], "emailed": out["emailed"],
            "alerts": cm.alerts({"results": out["results"]})}
