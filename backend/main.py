import os
import re
from typing import Optional
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import StatementError, IntegrityError
from .models.database import init_db, User
from .core.auth import get_current_user_optional
from .routers import auth, brokers, requests as requests_router
from .routers.family import family_router, identity_router
from .routers.admin import router as admin_router
from .routers.settings import router as settings_router
from .routers.scheduler import router as scheduler_router
from .routers.help import router as help_router
from .routers.automation import router as automation_router
from .routers.branding import router as branding_router
from .routers.database_admin import router as db_admin_router
from .routers.reporting import router as reporting_router
from .routers.email_monitor import router as email_monitor_router
from .routers.plugins import router as plugins_router
from .routers.parent_companies import router as parent_companies_router
from .routers.wizard import router as wizard_router
from .routers.email_oauth import router as email_oauth_router
from .routers.test_broker import router as test_broker_router
from .routers.saml import router as saml_router
from .routers.cert_monitor import router as cert_monitor_router
from .routers.consortium import router as consortium_router
from .routers.logs import router as logs_router
from .routers.captcha import router as captcha_router
from .routers.i18n import router as i18n_router
from .routers.workers import router as workers_router
from .routers.mailboxes import router as mailboxes_router
from .routers.listings import router as listings_router
from .routers.registry import router as registry_router
from .routers.web_search import router as web_search_router
from .routers.backups import router as backups_router
from .routers.privacy_pages import router as privacy_pages_router
from .routers.broker_updates import router as broker_updates_router
from .routers.verification import router as verification_router
from .routers.broker_network import router as broker_network_router
from .routers.credit_freeze import router as credit_freeze_router
from .routers.timeline import router as timeline_router
from .routers.compliance import router as compliance_router
from .routers.privacy import router as privacy_router
from .routers.reports import router as reports_router
from .routers.calendar import router as calendar_router
from .routers.confirm_links import router as confirm_links_router
from .routers.checklist import router as checklist_router
from .routers.variants import router as variants_router
from .routers.spec_helpers import router as spec_helpers_router
from .routers.live_steps import router as live_steps_router
from .routers.letters import router as letters_router
from .routers.observability import router as observability_router, ops_router
from .routers.terms import router as terms_router
from .routers.usage_stats import router as stats_admin_router, api_router as stats_api_router
from .routers.resident_addresses import router as resident_addresses_router
from .routers.updates import router as updates_router
from .routers.csp_report import router as csp_report_router
from .routers.scim import router as scim_router
from .core.scheduler import start_scheduler, stop_scheduler
from .core.version import get_version, get_commit, version_string
from .core.logging_config import init_logging
from .core.gpc import gpc_well_known_document

# The interactive Swagger/ReDoc explorer UIs hand an unauthenticated visitor
# a human-browsable map of every route and field name on an appliance that
# holds families' (including children's) PII — reconnaissance a WAF or log
# review won't flag, since it looks like ordinary docs traffic. They're off
# by default; set ENABLE_API_DOCS=true (for local development) to turn them
# back on. /openapi.json itself stays on: the bundled reverse-proxy configs
# (Caddy/Traefik/nginx) only ever forward /api/* to this API, so the raw
# schema isn't part of the normal deployment's public surface either way,
# and the release-test harness relies on fetching it directly to sweep every
# GET endpoint for server errors.
_enable_interactive_docs = os.getenv("ENABLE_API_DOCS", "").lower() in ("true", "1", "yes")

app = FastAPI(
    title="OpenOptOut API",
    description="Open-source personal data removal pipeline",
    version=get_version(),
    docs_url="/docs" if _enable_interactive_docs else None,
    redoc_url="/redoc" if _enable_interactive_docs else None,
)

_cors_origins_env = os.getenv("ALLOWED_ORIGINS") or os.getenv("CORS_ORIGINS")
if _cors_origins_env:
    cors_origins = [orig.strip() for orig in _cors_origins_env.split(",") if orig.strip()]
else:
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost").rstrip("/")
    cors_origins = sorted(list({
        frontend_url,
        "http://localhost",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    }))

# Cap every request's size before anything reads it (core/limits.py). Added
# before CORS so CORS stays outermost and a 413 still carries CORS headers —
# the browser then shows our message instead of a vague network error.
from .core.limits import RequestSizeLimitMiddleware
app.add_middleware(RequestSizeLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    # The exact verbs every route actually uses (plus OPTIONS for preflight),
    # not "*" (ASVS 4.1.4 defense-in-depth — routing itself already 405s any
    # method with no matching route, so this narrows what a cross-origin
    # preflight is told is allowed, not what the server will actually do).
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    # ASVS 14.2.2/14.3.2: nothing here is cached by default — browsers, shared
    # proxies, or a load balancer in front of this API. A handful of routes
    # (calendar feed, CAPTCHA/step screenshots, usage stats) set their own
    # deliberate value above and this setdefault leaves theirs alone.
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    # ASVS 3.4.8: blocks tabnabbing/cross-window attacks via window.opener;
    # 3.5.8: same-origin default for any resource this API itself serves.
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    from .core.settings_store import is_hsts_enabled
    if is_hsts_enabled():
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    content_type = response.headers.get("content-type", "").lower()
    from .core.csp import MINIMAL_HTML_CSP, SVG_CSP, REPORTING_ENDPOINTS_HEADER
    if "text/html" in content_type:
        response.headers.setdefault("Content-Security-Policy", MINIMAL_HTML_CSP)
        response.headers.setdefault("Reporting-Endpoints", REPORTING_ENDPOINTS_HEADER)
    elif "svg" in content_type:
        response.headers.setdefault("Content-Security-Policy", SVG_CSP)
    return response


# Traefik's passTLSClientCert middleware packs several fields into one header
# as name="value" pairs; this pulls out just SerialNumber.
_TRAEFIK_CERT_SERIAL_RE = re.compile(r'SerialNumber="?([0-9A-Fa-f:]+)"?')


@app.middleware("http")
async def reject_revoked_client_certs(request, call_next):
    """
    Self-managed mTLS (core/mtls.py, docs/admin/https.md) authenticates a
    device at the TLS layer against the client CA, but none of the three
    supported reverse proxies (Caddy, Traefik, nginx) check a revocation list
    at that layer -- a revoked certificate still authenticates there until it
    expires. The proxy entrypoints instead forward the serial of whichever
    certificate authenticated the connection (X-Client-Cert-Serial, or
    Traefik's X-Forwarded-Tls-Client-Cert-Info), so this can still refuse it.

    The TLS handshake the header describes is real cryptography the proxy
    already performed; a forged header can only name a certificate that the
    client did NOT present, which this check can only use to BLOCK (an
    already-revoked identity) -- never to grant anything a client without a
    valid certificate wouldn't already get from the route's own auth. Like
    core/rate_limit.py's trust in X-Forwarded-For, this assumes the API is
    reachable only through the configured proxy -- see docs/admin/https.md.

    No header present -> nothing to check here; pass through unchanged. That
    covers mTLS being off, mode=optional with no client cert offered, and any
    proxy this project doesn't yet forward the serial for.
    """
    serial = request.headers.get("x-client-cert-serial")
    if not serial:
        m = _TRAEFIK_CERT_SERIAL_RE.search(request.headers.get("x-forwarded-tls-client-cert-info", ""))
        serial = m.group(1) if m else None
    if serial:
        from .core.mtls import is_serial_revoked
        if is_serial_revoked(serial):
            return JSONResponse(
                status_code=403,
                content={"detail": "This client certificate has been revoked. Contact an administrator for a new one."},
            )
    return await call_next(request)


@app.exception_handler(OverflowError)
async def overflow_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"detail": "Value out of range"})


@app.exception_handler(StatementError)
async def statement_error_handler(request, exc):
    if hasattr(exc, "orig") and (isinstance(exc.orig, OverflowError) or "too large" in str(exc).lower()):
        return JSONResponse(status_code=400, content={"detail": "Value out of range"})
    return JSONResponse(status_code=400, content={"detail": "Invalid statement parameters"})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"detail": "Database integrity constraint violated"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    """ASVS 16.5.4: a last-resort handler so an exception type nobody added a
    specific handler for still gets its traceback into this app's own log
    store (not just raw stdout) and still returns the app's generic error
    body (ASVS 16.5.1) instead of taking the whole process down or leaking
    internals. More specific handlers above (and FastAPI's own HTTPException/
    RequestValidationError handlers) still take precedence for their types —
    Starlette only falls back to this one when nothing else matched."""
    import logging
    logging.getLogger(__name__).error(
        "Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc,
    )
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})

for r in [
    auth.router, brokers.router, requests_router.router,
    family_router, identity_router, admin_router,
    settings_router, scheduler_router, help_router,
    automation_router, email_monitor_router,
    branding_router, reporting_router,
    db_admin_router, plugins_router, parent_companies_router, wizard_router,
    email_oauth_router, test_broker_router, saml_router, cert_monitor_router,
    consortium_router, logs_router, captcha_router, i18n_router,
    workers_router, mailboxes_router, listings_router, registry_router,
    web_search_router, checklist_router, variants_router, privacy_pages_router, confirm_links_router, broker_updates_router, verification_router, broker_network_router, credit_freeze_router, timeline_router, compliance_router, privacy_router, reports_router, calendar_router, spec_helpers_router, live_steps_router, letters_router, observability_router, ops_router, terms_router, stats_admin_router, stats_api_router, resident_addresses_router, updates_router, csp_report_router, scim_router,
]:
    app.include_router(r)


@app.on_event("startup")
def startup():
    # Load persistent secret.key if present, or replace missing/example SECRET_KEY with an ephemeral key until configured in UI
    from .core.settings_store import ensure_bootstrap_secret_key
    ensure_bootstrap_secret_key()
    # Enforce zero-core-dump memory hygiene policy (prevents PII disk dumps on crash)
    from .core.memory_hygiene import disable_core_dumps
    disable_core_dumps()
    # Initialize rotating file logger and in-memory ring buffer
    init_logging()
    try:   # copies of log lines to a central server, if an admin set one up
        from .core.log_forwarding import apply as _forward_logs
        _forward_logs()
        from .core import monitoring as _monitoring   # noqa: F401  (uptime counts from here)
    except Exception:
        pass
    # First thing logged, before anything that could fail — so "what version
    # is this" is answerable from `docker compose logs api` even if startup
    # doesn't get any further than this.
    import logging
    logging.getLogger(__name__).info(version_string() + " starting up")
    init_db()
    from .core.migrations import (run_migrations, seed_property_brokers, run_institutional_migrations,
                                  add_manager_role, migrate_plugin_upload_grants)
    add_manager_role()
    run_migrations()
    run_institutional_migrations()
    migrate_plugin_upload_grants()   # needs every users column, so after both lists
    seed_property_brokers()
    # Curated broker opt-out steps that ship with the app.
    try:
        from .models.database import SessionLocal
        from .plugins.broker_addon import sync_builtin_brokers
        from .plugins.language_packs import sync_builtin_languages, sync_builtin_letters
        _db = SessionLocal()
        try:
            sync_builtin_brokers(_db)
            sync_builtin_languages(_db)
            sync_builtin_letters(_db)
        finally:
            _db.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Built-in broker add-ons not installed: %s", e)
    start_scheduler()
    # Plugin system — process-isolated, sandboxed, opt-in via settings
    try:
        from .plugins import init_plugin_system
        init_plugin_system()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Plugin system failed to start: %s", e)


@app.on_event("shutdown")
def shutdown():
    stop_scheduler()
    try:
        from .plugins import get_manager
        mgr = get_manager()
        if mgr:
            mgr.stop()
    except Exception:
        pass


@app.get("/.well-known/gpc.json")
@app.get("/api/.well-known/gpc.json")
def gpc_well_known():
    """
    W3C Global Privacy Control (GPC) server discovery resource.
    Conforms to W3C GPC spec (https://privacycg.github.io/gpc-spec/#well-known-resource).
    """
    return JSONResponse(
        content=gpc_well_known_document(),
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=86400",
        },
    )


@app.get("/.well-known/security.txt")
@app.get("/api/.well-known/security.txt")
def security_txt():
    """
    RFC 9116 security.txt vulnerability disclosure discovery resource.
    Conforms to CISA Secure by Design guidelines.
    """
    from fastapi.responses import PlainTextResponse
    content = (
        "Contact: https://github.com/rlnunez/OpenOptOut/security/advisories/new\n"
        "Expires: 2027-10-24T00:00:00.000Z\n"
        "Preferred-Languages: en\n"
        "Canonical: https://raw.githubusercontent.com/rlnunez/OpenOptOut/main/.well-known/security.txt\n"
        "Policy: https://github.com/rlnunez/OpenOptOut/blob/main/SECURITY.md\n"
        "Acknowledgments: https://github.com/rlnunez/OpenOptOut/graphs/contributors\n"
        "Acknowledgments: https://github.com/rlnunez/OpenOptOut/blob/main/CHANGELOG.md\n"
        "CSAF: https://raw.githubusercontent.com/rlnunez/OpenOptOut/main/.well-known/csaf/provider-metadata.json\n"
    )
    return PlainTextResponse(
        content=content,
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Cache-Control": "public, max-age=86400",
        },
    )


@app.get("/.well-known/csaf/provider-metadata.json")
@app.get("/api/.well-known/csaf/provider-metadata.json")
def csaf_provider_metadata():
    """
    OASIS Common Security Advisory Framework (CSAF) 2.0 Provider Metadata.
    Enables automated machine ingestion of vulnerability advisories.
    """
    from .core.csaf import get_csaf_provider_metadata
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content=get_csaf_provider_metadata(),
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=86400",
        },
    )


@app.get("/api/health")
def health(current_user: Optional[User] = Depends(get_current_user_optional)):
    # Public liveness probe (docker healthchecks, the updater, release
    # testing all poll this unauthenticated) — version alone is already
    # public knowledge (GitHub releases/Docker tags). The exact commit is
    # sharper fingerprinting (an anonymous caller could diff the public repo
    # at that commit to see exactly what's patched), so it's only included
    # once someone is actually signed in, matching how the app's own
    # Sidebar/Help "copy diagnostics" feature already calls this endpoint
    # while logged in (ASVS 13.4.6).
    out = {"status": "ok", "version": get_version()}
    if current_user is not None:
        out["commit"] = get_commit()
    return out
