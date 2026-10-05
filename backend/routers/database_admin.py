"""
Database administration endpoints.
Health check, stats, connection info, and SQLite → Postgres migration.
Super admin only.
"""

import os, json, logging, time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import text, inspect, select, func, table as sql_table, column as sql_column
from sqlalchemy.orm import Session

from ..models.database import get_db, engine, User, FamilyMember, Broker, RemovalRequest
from ..core.auth import require_super_admin
from ..core.access import require_permission

router = APIRouter(prefix="/api/database", tags=["database"])
log    = logging.getLogger(__name__)

# Migration status stored in memory (single-instance) or settings file
_migration_status: dict = {"running": False, "progress": [], "done": False, "error": None}


# ── Health & stats ────────────────────────────────────────────────────────────

@router.get("/health")
def db_health(db: Session = Depends(get_db), _=Depends(require_permission("database.view"))):
    """Connection health, engine info, and basic row counts."""
    db_url  = os.getenv("DATABASE_URL", "sqlite:///./privacy_pipeline.db")
    db_type = "postgres" if "postgresql" in db_url else "sqlite"

    # Ping
    t0 = time.monotonic()
    try:
        db.execute(text("SELECT 1"))
        ping_ms = round((time.monotonic() - t0) * 1000, 1)
        connected = True
    except Exception as e:
        ping_ms = None; connected = False

    # Row counts
    counts = {}
    try:
        inspector = inspect(engine)
        for table in inspector.get_table_names():
            try:
                result = db.execute(select(func.count()).select_from(sql_table(table))).scalar()
                counts[table] = result
            except Exception:
                counts[table] = None
    except Exception:
        pass

    # SQLite-specific: file size
    file_size_mb = None
    if db_type == "sqlite":
        db_path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
        if os.path.exists(db_path):
            file_size_mb = round(os.path.getsize(db_path) / 1_048_576, 2)

    # Postgres-specific: DB size
    pg_size = None
    if db_type == "postgres":
        try:
            pg_size = db.execute(
                text("SELECT pg_size_pretty(pg_database_size(current_database()))")
            ).scalar()
        except Exception:
            pass

    # Connection pool stats (SQLAlchemy)
    pool_stats = {}
    try:
        pool = engine.pool
        pool_stats = {
            "size":      pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow":  pool.overflow(),
        }
    except Exception:
        pass

    return {
        "connected":      connected,
        "db_type":        db_type,
        "ping_ms":        ping_ms,
        "file_size_mb":   file_size_mb,
        "pg_size":        pg_size,
        "table_counts":   counts,
        "pool":           pool_stats,
        "sqlcipher":      _sqlcipher_active(),
        "field_encryption": _field_enc_active(),
        "recommendations": _get_recommendations(db_type, counts, file_size_mb),
    }


def _sqlcipher_active() -> bool:
    try:
        from sqlcipher3 import dbapi2
        return bool(os.getenv("DB_ENCRYPTION_KEY") or os.getenv("SECRET_KEY", "").startswith("change") is False)
    except ImportError:
        return False


def _field_enc_active() -> bool:
    from ..core.encryption import get_field_encryption_key
    return bool(get_field_encryption_key())


def _get_recommendations(db_type: str, counts: dict, file_size_mb: Optional[float]) -> list:
    recs = []
    total_requests = counts.get("removal_requests", 0) or 0
    total_users    = counts.get("users", 0) or 0
    total_members  = counts.get("family_members", 0) or 0

    if db_type == "sqlite":
        if total_users > 500:
            recs.append({
                "level":   "warning",
                "message": f"{total_users} users on SQLite — consider migrating to Postgres at this scale",
            })
        elif total_users > 100:
            recs.append({
                "level":   "info",
                "message": f"{total_users} users — SQLite is fine now but plan a Postgres migration before reaching 500+ concurrent users",
            })
        if total_requests > 50_000:
            recs.append({
                "level":   "warning",
                "message": f"{total_requests:,} removal requests — SQLite write locking may cause slowdowns under concurrent load",
            })
        if file_size_mb and file_size_mb > 500:
            recs.append({
                "level":   "info",
                "message": f"Database file is {file_size_mb}MB — consider archiving old automation logs",
            })
    if not _field_enc_active():
        recs.append({
            "level":   "warning",
            "message": "Field-level PII encryption is not enabled — set FIELD_ENCRYPTION_KEY in .env",
        })
    if db_type == "sqlite" and not _sqlcipher_active():
        recs.append({
            "level":   "info",
            "message": "SQLCipher database encryption is not enabled — set DB_ENCRYPTION_KEY in .env",
        })
    return recs


# ── Table stats ───────────────────────────────────────────────────────────────

@router.get("/tables")
def table_stats(db: Session = Depends(get_db), _=Depends(require_permission("database.view"))):
    """Detailed per-table statistics."""
    db_url  = os.getenv("DATABASE_URL", "sqlite:///./privacy_pipeline.db")
    db_type = "postgres" if "postgresql" in db_url else "sqlite"

    inspector = inspect(engine)
    tables    = []

    for table_name in sorted(inspector.get_table_names()):
        try:
            count = db.execute(select(func.count()).select_from(sql_table(table_name))).scalar()
        except Exception:
            count = None

        size_bytes = None
        if db_type == "postgres":
            try:
                size_bytes = db.execute(
                    select(func.pg_total_relation_size(table_name))
                ).scalar()
            except Exception:
                pass

        columns = [c["name"] for c in inspector.get_columns(table_name)]
        tables.append({
            "name":       table_name,
            "row_count":  count,
            "size_bytes": size_bytes,
            "columns":    columns,
        })

    return tables


# ── Migration: SQLite → Postgres ──────────────────────────────────────────────

@router.get("/migration-status")
def migration_status(_=Depends(require_permission("database.view"))):
    return _migration_status


@router.post("/migrate-to-postgres")
def start_migration(
    target_url: str,
    background_tasks: BackgroundTasks,
    _=Depends(require_super_admin),
):
    """
    Migrate all data from the current SQLite database to a Postgres database.
    Runs in the background — poll /migration-status for progress.

    target_url: full Postgres connection string,
    e.g. postgresql://user:password@host:5432/openoptout
    """
    global _migration_status

    db_url = os.getenv("DATABASE_URL", "sqlite:///./privacy_pipeline.db")
    if "postgresql" in db_url:
        raise HTTPException(400, "Already using Postgres")
    if not target_url.startswith("postgresql"):
        raise HTTPException(400, "target_url must be a PostgreSQL connection string")
    if _migration_status["running"]:
        raise HTTPException(400, "Migration already in progress")

    _migration_status = {"running": True, "progress": [], "done": False, "error": None, "started_at": datetime.utcnow().isoformat()}
    background_tasks.add_task(_run_migration, target_url)
    return {"started": True}


def _log_progress(msg: str):
    global _migration_status
    _migration_status["progress"].append(f"{datetime.utcnow().strftime('%H:%M:%S')} {msg}")
    log.info(f"DB migration: {msg}")


def _run_migration(target_url: str):
    global _migration_status
    try:
        from sqlalchemy import create_engine as _ce, MetaData, Table, insert, select
        from sqlalchemy.orm import sessionmaker as _sm

        _log_progress("Connecting to source SQLite database...")
        src_engine = engine   # existing engine

        _log_progress(f"Connecting to target Postgres: {target_url.split('@')[-1]}...")
        try:
            tgt_engine = _ce(target_url, pool_pre_ping=True)
            tgt_engine.connect().close()
        except Exception:
            raise RuntimeError("Cannot connect to Postgres. Check database credentials and network connectivity.")

        _log_progress("Creating schema on Postgres...")
        from ..models.database import Base
        Base.metadata.create_all(bind=tgt_engine)

        _log_progress("Starting table-by-table data copy...")

        src_meta = MetaData()
        src_meta.reflect(bind=src_engine)

        # Copy in dependency order to respect FK constraints
        ordered_tables = [
            "users", "family_members", "identities",
            "profile_access", "invite_codes",
            "brokers", "broker_scripts",
            "removal_requests", "email_logs",
            "discovery_results", "automation_logs",
            "member_schedule_configs", "scheduler_runs",
            "usage_events",
        ]

        src_session = _sm(bind=src_engine)()
        tgt_session = _sm(bind=tgt_engine)()

        total_rows = 0
        for table_name in ordered_tables:
            if table_name not in src_meta.tables:
                _log_progress(f"  Skipping {table_name} (not in source)")
                continue
            tbl = src_meta.tables[table_name]
            rows = src_session.execute(select(tbl)).fetchall()
            if not rows:
                _log_progress(f"  {table_name}: 0 rows (empty)")
                continue

            # Convert rows to dicts
            cols = [c.name for c in tbl.columns]
            dicts = [dict(zip(cols, row)) for row in rows]

            # Insert in batches of 500
            tgt_tbl = Table(table_name, MetaData(), autoload_with=tgt_engine)
            batch_size = 500
            for i in range(0, len(dicts), batch_size):
                batch = dicts[i:i + batch_size]
                tgt_session.execute(insert(tgt_tbl), batch)
            tgt_session.commit()

            total_rows += len(rows)
            _log_progress(f"  {table_name}: {len(rows):,} rows copied")

        # Reset Postgres sequences to avoid PK conflicts
        _log_progress("Resetting Postgres sequences...")
        for table_name in ordered_tables:
            try:
                tgt_session.execute(
                    select(
                        func.setval(
                            func.pg_get_serial_sequence(table_name, "id"),
                            func.coalesce(func.max(sql_column("id")), 1),
                        )
                    ).select_from(sql_table(table_name))
                )
            except Exception:
                pass
        tgt_session.commit()

        src_session.close()
        tgt_session.close()

        _log_progress(f"Migration complete — {total_rows:,} total rows copied")
        _log_progress("Next steps:")
        _log_progress("  1. Set DATABASE_URL in .env to the Postgres connection string")
        _log_progress("  2. Restart the container")
        _log_progress("  3. Verify by checking /api/database/health")
        _log_progress("  4. Keep the SQLite file as backup for 30 days")

        _migration_status["done"]    = True
        _migration_status["running"] = False
        _migration_status["total_rows"] = total_rows

    except Exception as e:
        log.error(f"DB migration failed: {e}")
        _log_progress("ERROR: Database migration failed. Check server logs.")
        _migration_status["error"]   = "Database migration failed. Check server logs for details."
        _migration_status["running"] = False


# ── Structured connection configuration ───────────────────────────────────────

from pydantic import BaseModel
from typing import Optional as Opt

class DBConnectionConfig(BaseModel):
    """
    Non-secret PostgreSQL connection configuration.
    Secrets (passwords, keys) are NEVER included here — they come from
    environment variables or mounted files controlled by the DBA.
    """
    enabled:      bool = False
    auth_method:  str  = "password"   # see db_connection.py for full list
    host:         Opt[str] = None
    port:         int  = 5432
    dbname:       Opt[str] = None
    user:         Opt[str] = None
    sslmode:      str  = "prefer"
    # Cert/key FILE PATHS (the paths are non-secret; files are DBA-controlled)
    sslrootcert:  Opt[str] = None
    sslcert:      Opt[str] = None
    sslkey:       Opt[str] = None
    iam_region:   Opt[str] = None
    gssapi_principal: Opt[str] = None


AUTH_METHOD_INFO = {
    "password": {
        "label": "Password (SCRAM-SHA-256)",
        "secrets": ["DB_PASSWORD or DB_PASSWORD_FILE"],
        "note": "Standard username/password. Combine with sslmode=require or higher to encrypt in transit.",
    },
    "ssl_password": {
        "label": "Password over verified TLS",
        "secrets": ["DB_PASSWORD or DB_PASSWORD_FILE"],
        "note": "Password auth over a TLS connection with certificate verification. Set sslmode=verify-full and provide a CA cert.",
    },
    "client_cert": {
        "label": "Client certificate (mutual TLS, no password)",
        "secrets": ["Client cert file", "Client key file (chmod 600)"],
        "note": "The strongest common method. The client presents a certificate; no password is transmitted. Requires sslmode=verify-full, a CA cert, client cert, and client key mounted as files.",
    },
    "cert_and_password": {
        "label": "Client certificate + password (defense in depth)",
        "secrets": ["Client cert", "Client key", "DB_PASSWORD"],
        "note": "Requires both a valid client certificate AND a password. Used in high-security environments (finance, healthcare, government).",
    },
    "iam_aws": {
        "label": "AWS RDS IAM authentication",
        "secrets": ["AWS credentials via IAM role (no static password)"],
        "note": "Uses short-lived (15 min) IAM auth tokens instead of a stored password. Requires boto3 and an attached IAM role or AWS credentials. SSL is mandatory.",
    },
    "iam_gcp": {
        "label": "GCP Cloud SQL IAM authentication",
        "secrets": ["GCP service account (no static password)"],
        "note": "Uses OAuth2 tokens from a service account. Requires google-auth and the Cloud SQL IAM database authentication feature enabled.",
    },
    "iam_azure": {
        "label": "Azure AD authentication",
        "secrets": ["Azure managed identity (no static password)"],
        "note": "Uses Azure AD access tokens via managed identity or service principal. Requires azure-identity.",
    },
    "gssapi": {
        "label": "Kerberos / GSSAPI",
        "secrets": ["Kerberos ticket (from kinit / keytab)"],
        "note": "Enterprise single sign-on for databases using Kerberos. No password stored — uses the ticket cache. Common in large Active Directory environments.",
    },
}


@router.get("/connection-config")
def get_connection_config(_=Depends(require_permission("database.view"))):
    """
    Return the current structured connection config (non-secret fields only)
    plus metadata about each auth method and which secrets it requires.
    """
    from ..core.settings_store import load_settings
    s   = load_settings()
    cfg = s.get("database", {})

    # Report which secret sources are currently detected (without revealing values)
    secret_status = {
        "db_password_env":  bool(os.getenv("DB_PASSWORD")),
        "db_password_file": bool(os.getenv("DB_PASSWORD_FILE") and os.path.exists(os.getenv("DB_PASSWORD_FILE", ""))),
        "sslrootcert_exists": bool(cfg.get("sslrootcert") and os.path.exists(cfg.get("sslrootcert", ""))),
        "sslcert_exists":     bool(cfg.get("sslcert") and os.path.exists(cfg.get("sslcert", ""))),
        "sslkey_exists":      bool(cfg.get("sslkey") and os.path.exists(cfg.get("sslkey", ""))),
    }

    return {
        "config": {
            "enabled":     cfg.get("enabled", False),
            "auth_method": cfg.get("auth_method", "password"),
            "host":        cfg.get("host"),
            "port":        cfg.get("port", 5432),
            "dbname":      cfg.get("dbname"),
            "user":        cfg.get("user"),
            "sslmode":     cfg.get("sslmode", "prefer"),
            "sslrootcert": cfg.get("sslrootcert"),
            "sslcert":     cfg.get("sslcert"),
            "sslkey":      cfg.get("sslkey"),
            "iam_region":  cfg.get("iam_region"),
            "gssapi_principal": cfg.get("gssapi_principal"),
        },
        "auth_methods": AUTH_METHOD_INFO,
        "secret_status": secret_status,
    }


@router.patch("/connection-config")
def save_connection_config(
    data: DBConnectionConfig,
    _=Depends(require_super_admin),
):
    """
    Save non-secret connection configuration.
    Secret material is NEVER accepted here — passwords come from env/files only.
    Changes take effect after a container restart.
    """
    from ..core.settings_store import load_settings, SETTINGS_FILE
    import json as _json

    s = load_settings()
    s["database"] = data.model_dump()
    with open(SETTINGS_FILE, "w") as f:
        _json.dump(s, f, indent=2)

    return {
        "saved": True,
        "note": "Connection config saved. Restart the container for changes to take effect. "
                "Ensure required secrets (passwords, certs) are mounted or set as environment variables.",
    }


@router.post("/connection-config/test")
def test_connection_config(_=Depends(require_super_admin)):
    """Test the structured connection configuration."""
    from ..core.db_connection import test_connection
    return test_connection()
