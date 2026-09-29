from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from .core.scheduler import start_scheduler, stop_scheduler
from .core.version import get_version, get_commit, version_string
from .core.logging_config import init_logging

app = FastAPI(
    title="PrivacyShield API",
    description="Open-source personal data removal pipeline",
    version=get_version(),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in [
    auth.router, brokers.router, requests_router.router,
    family_router, identity_router, admin_router,
    settings_router, scheduler_router, help_router,
    automation_router, email_monitor_router,
    branding_router, reporting_router,
    db_admin_router, plugins_router, parent_companies_router, wizard_router,
    email_oauth_router, test_broker_router, saml_router, cert_monitor_router,
    consortium_router, logs_router,
]:
    app.include_router(r)


@app.on_event("startup")
def startup():
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
