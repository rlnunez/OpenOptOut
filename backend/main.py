import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import StatementError, IntegrityError
from .models.database import init_db
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
from .routers.confirm_links import router as confirm_links_router
from .routers.checklist import router as checklist_router
from .routers.variants import router as variants_router
from .core.scheduler import start_scheduler, stop_scheduler
from .core.version import get_version, get_commit, version_string
from .core.logging_config import init_logging

app = FastAPI(
    title="OpenOptOut API",
    description="Open-source personal data removal pipeline",
    version=get_version(),
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none';",
        )
    return response


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
    web_search_router, checklist_router, variants_router, privacy_pages_router, confirm_links_router, broker_updates_router, verification_router, broker_network_router, credit_freeze_router, timeline_router, compliance_router, privacy_router,
]:
    app.include_router(r)


@app.on_event("startup")
def startup():
    # Enforce zero-core-dump memory hygiene policy (prevents PII disk dumps on crash)
    from .core.memory_hygiene import disable_core_dumps
    disable_core_dumps()
    # Initialize rotating file logger and in-memory ring buffer
    init_logging()
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
        _db = SessionLocal()
        try:
            sync_builtin_brokers(_db)
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


@app.get("/api/health")
def health():
    return {"status": "ok", "version": get_version(), "commit": get_commit()}
