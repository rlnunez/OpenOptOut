"""
Additive schema migrations — run on startup after init_db().
Uses ALTER TABLE for SQLite compatibility (add columns only, no drops).
For Postgres these are no-ops if columns already exist.
"""

import logging
from sqlalchemy import text
from ..models.database import engine

log = logging.getLogger(__name__)

# Each migration is (description, SQL).
# SQLite doesn't support IF NOT EXISTS on ALTER TABLE,
# so we catch the "duplicate column" error and continue.

MIGRATIONS = [
    (
        "Add formal_name to family_members",
        "ALTER TABLE family_members ADD COLUMN formal_name VARCHAR"
    ),
    (
        "Add max_children_override to profile_access",
        "ALTER TABLE profile_access ADD COLUMN max_children_override INTEGER"
    ),
    (
        "Add is_deed to identities",
        "ALTER TABLE identities ADD COLUMN is_deed BOOLEAN DEFAULT 0"
    ),
    (
        "Add is_mortgage to identities",
        "ALTER TABLE identities ADD COLUMN is_mortgage BOOLEAN DEFAULT 0"
    ),
    (
        "Add is_property_broker to brokers",
        "ALTER TABLE brokers ADD COLUMN is_property_broker BOOLEAN DEFAULT 0"
    ),
    (
        # FALSE, not 0: Postgres rejects an integer default on a BOOLEAN column.
        "Add can_upload_plugins to users",
        "ALTER TABLE users ADD COLUMN can_upload_plugins BOOLEAN NOT NULL DEFAULT FALSE"
    ),
    (
        "Add permissions_granted to users",
        "ALTER TABLE users ADD COLUMN permissions_granted TEXT"
    ),
    (
        "Add permissions_revoked to users",
        "ALTER TABLE users ADD COLUMN permissions_revoked TEXT"
    ),
    (
        "Add code_hash to installed_plugins",
        "ALTER TABLE installed_plugins ADD COLUMN code_hash VARCHAR"
    ),
    (
        "Add branch_id to users",
        "ALTER TABLE users ADD COLUMN branch_id INTEGER"
    ),
    (
        "Add branch_source to users",
        "ALTER TABLE users ADD COLUMN branch_source VARCHAR DEFAULT 'sip2'"
    ),
    (
        "Add branch_override_by to users",
        "ALTER TABLE users ADD COLUMN branch_override_by INTEGER"
    ),
    (
        "Add branch_override_at to users",
        "ALTER TABLE users ADD COLUMN branch_override_at TIMESTAMP"
    ),
    (
        "Add captcha_plugin_id to brokers",
        "ALTER TABLE brokers ADD COLUMN captcha_plugin_id VARCHAR(100)"
    ),
    (
        "Add plugin_id to brokers",
        "ALTER TABLE brokers ADD COLUMN plugin_id VARCHAR(100)"
    ),
    (
        "Add preferred_language to users",
        "ALTER TABLE users ADD COLUMN preferred_language VARCHAR(10) DEFAULT 'en'"
    ),
    (
        "Add tutorial_completed to users",
        "ALTER TABLE users ADD COLUMN tutorial_completed BOOLEAN DEFAULT 0"
    ),
    (
        "Add totp_secret_enc to users",
        "ALTER TABLE users ADD COLUMN totp_secret_enc TEXT"
    ),
    (
        "Add totp_enabled to users",
        "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    ),
    (
        "Add backup_codes to users",
        "ALTER TABLE users ADD COLUMN backup_codes TEXT"
    ),
    (
        "Add webauthn_credentials to users",
        "ALTER TABLE users ADD COLUMN webauthn_credentials TEXT"
    ),
    (
        "Add mfa_options_override to users",
        "ALTER TABLE users ADD COLUMN mfa_options_override TEXT"
    ),
    (
        "Add eligibility_rules to sip2_connections",
        "ALTER TABLE sip2_connections ADD COLUMN eligibility_rules TEXT DEFAULT ''"
    ),
    (
        "Add date_format to sip2_connections",
        "ALTER TABLE sip2_connections ADD COLUMN date_format VARCHAR(30) DEFAULT 'auto'"
    ),
    (
        "Add map_patron_fields to sip2_connections",
        "ALTER TABLE sip2_connections ADD COLUMN map_patron_fields BOOLEAN DEFAULT FALSE"
    ),
    (
        "Add field_mappings to sip2_connections",
        "ALTER TABLE sip2_connections ADD COLUMN field_mappings TEXT DEFAULT ''"
    ),
    (
        "Add populate_vault to sip2_connections",
        "ALTER TABLE sip2_connections ADD COLUMN populate_vault BOOLEAN DEFAULT FALSE"
    ),
    (
        "Add forced_fields to sip2_connections",
        "ALTER TABLE sip2_connections ADD COLUMN forced_fields TEXT DEFAULT '[\"library\"]'"
    ),
    (
        "Add patron_choice to sip2_connections",
        "ALTER TABLE sip2_connections ADD COLUMN patron_choice BOOLEAN DEFAULT TRUE"
    ),
    (
        "Add pending_ils_import to users",
        "ALTER TABLE users ADD COLUMN pending_ils_import TEXT DEFAULT NULL"
    ),
    (
        "Add accessibility_settings to users",
        "ALTER TABLE users ADD COLUMN accessibility_settings TEXT DEFAULT NULL"
    ),
]

# Known property brokers — flagged on first startup
PROPERTY_BROKER_PATTERNS = [
    "homes.com", "realtytrac.com", "propertyshark.com", "zillow.com",
    "realtor.com", "redfin.com", "trulia.com", "realeflow.com",
    "realtyhop.com", "propertyrec.com", "propertyrecs.com",
    "propertyrecord.com", "propertyreach.com", "propertychecker.com",
    "publicrecord.com", "publicrecords.info", "staterecords.org",
    "realtyhop", "propertyshark", "realtytrac", "homefacts.com",
    "neighborhoodscout.com", "blockchainrealty.com",
]


def add_manager_role():
    """
    Postgres stores UserRole as a native enum type, which needs the new
    'manager' value added explicitly (SQLite stores it as plain text). Uses
    IF NOT EXISTS so it's safe on every startup.
    """
    if engine.dialect.name != "postgresql":
        return
    try:
        # ALTER TYPE ... ADD VALUE can't run inside a transaction block on older
        # Postgres versions, so use autocommit.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'manager'"))
    except Exception as e:
        log.warning(f"Could not add 'manager' to the userrole enum: {e}")


def migrate_plugin_upload_grants():
    """
    Before the manager role existed, a super admin could give a parent a
    per-user "can upload plugins" switch. Turn each of those into a manager
    whose only permission is plugins.upload, so nobody gains or loses access,
    then clear the old switch so this runs once per user.
    """
    import json
    from ..models.database import SessionLocal, User, UserRole
    from .access import manager_defaults
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.can_upload_plugins == True,  # noqa: E712
                                      User.role != UserRole.super_admin).all()
        for u in users:
            u.role = UserRole.manager
            u.permissions_granted = json.dumps(["plugins.upload"])
            u.permissions_revoked = json.dumps([k for k in manager_defaults() if k != "plugins.upload"])
            u.can_upload_plugins = False
            log.info(f"Converted plugin-upload grant for user {u.id} into a manager "
                     f"with only the plugins.upload permission")
        if users:
            db.commit()
    except Exception as e:
        db.rollback()
        log.warning(f"Could not migrate plugin-upload grants: {e}")
    finally:
        db.close()


def run_migrations():
    """Run all additive migrations idempotently."""
    with engine.connect() as conn:
        for desc, sql in MIGRATIONS:
            try:
                conn.execute(text(sql))
                conn.commit()
                log.info(f"Migration applied: {desc}")
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    pass  # already applied
                else:
                    log.warning(f"Migration '{desc}' skipped: {e}")


def seed_property_brokers():
    """Flag known property brokers in the brokers table."""
    from ..models.database import SessionLocal
    from ..models.database import Broker
    db = SessionLocal()
    try:
        flagged = 0
        for pattern in PROPERTY_BROKER_PATTERNS:
            brokers = db.query(Broker).filter(
                Broker.name.ilike(f"%{pattern}%"),
                Broker.is_property_broker == False,
            ).all()
            for b in brokers:
                b.is_property_broker = True
                flagged += 1
        if flagged:
            db.commit()
            log.info(f"Flagged {flagged} property brokers")
    finally:
        db.close()


INSTITUTIONAL_MIGRATIONS = [
    ("Add invite_codes table",
     """CREATE TABLE IF NOT EXISTS invite_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code VARCHAR UNIQUE NOT NULL,
        created_by INTEGER REFERENCES users(id),
        max_uses INTEGER DEFAULT 1,
        uses INTEGER DEFAULT 0,
        expires_at DATETIME,
        role VARCHAR DEFAULT 'parent',
        note VARCHAR,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_active BOOLEAN DEFAULT 1
     )"""),
    ("Add usage_events table",
     """CREATE TABLE IF NOT EXISTS usage_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type VARCHAR NOT NULL,
        user_id INTEGER REFERENCES users(id),
        member_id INTEGER REFERENCES family_members(id),
        broker_id INTEGER REFERENCES brokers(id),
        meta TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
     )"""),
    ("Add installed_plugins table",
     """CREATE TABLE IF NOT EXISTS installed_plugins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plugin_id VARCHAR UNIQUE NOT NULL,
        name VARCHAR NOT NULL,
        version VARCHAR NOT NULL,
        author VARCHAR,
        description TEXT,
        manifest_json TEXT NOT NULL,
        granted_permissions TEXT,
        enabled BOOLEAN DEFAULT 0,
        install_path VARCHAR NOT NULL,
        installed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        enabled_at DATETIME,
        enabled_by INTEGER REFERENCES users(id),
        status VARCHAR DEFAULT 'stopped',
        crash_count INTEGER DEFAULT 0,
        last_error TEXT,
        last_started DATETIME
     )"""),
    ("Add plugin_storage table",
     """CREATE TABLE IF NOT EXISTS plugin_storage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plugin_id VARCHAR NOT NULL,
        key VARCHAR NOT NULL,
        value TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(plugin_id, key)
     )"""),
    ("Add plugin_audit_logs table",
     """CREATE TABLE IF NOT EXISTS plugin_audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plugin_id VARCHAR NOT NULL,
        action VARCHAR NOT NULL,
        detail TEXT,
        actor_id INTEGER REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
     )"""),
    ("Add plugin_violations table",
     """CREATE TABLE IF NOT EXISTS plugin_violations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plugin_id VARCHAR NOT NULL,
        vtype VARCHAR NOT NULL,
        severity VARCHAR NOT NULL,
        detail TEXT,
        action_taken VARCHAR,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
     )"""),
    ("Add needs_reapproval to installed_plugins",
     "ALTER TABLE installed_plugins ADD COLUMN needs_reapproval BOOLEAN DEFAULT 0"),
    ("Add enabled column to brokers",
     "ALTER TABLE brokers ADD COLUMN enabled BOOLEAN DEFAULT 1"),
    ("Add priority column to brokers",
     "ALTER TABLE brokers ADD COLUMN priority INTEGER DEFAULT 3"),
    ("Add priority_source column to brokers",
     "ALTER TABLE brokers ADD COLUMN priority_source VARCHAR DEFAULT 'default'"),
    ("Add parent_companies table",
     """CREATE TABLE IF NOT EXISTS parent_companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR NOT NULL UNIQUE,
        optout_email VARCHAR,
        cc_emails VARCHAR,
        locale VARCHAR DEFAULT 'en',
        website VARCHAR,
        notes TEXT,
        date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
        honor_status VARCHAR DEFAULT 'unknown',
        emails_sent INTEGER DEFAULT 0,
        emails_confirmed INTEGER DEFAULT 0,
        emails_failed INTEGER DEFAULT 0,
        last_sent_at DATETIME,
        last_confirmed_at DATETIME
     )"""),
    ("Add parent_company_id column to brokers",
     "ALTER TABLE brokers ADD COLUMN parent_company_id INTEGER"),
    ("Add is_test column to brokers",
     "ALTER TABLE brokers ADD COLUMN is_test BOOLEAN DEFAULT 0"),
    ("Add is_test column to parent_companies",
     "ALTER TABLE parent_companies ADD COLUMN is_test BOOLEAN DEFAULT 0"),
    ("Add auth_source column to users (external/SSO login)",
     "ALTER TABLE users ADD COLUMN auth_source VARCHAR"),
    ("Allow parent-level email logs (nullable request_id) — Postgres; no-op error on SQLite",
     "ALTER TABLE email_logs ALTER COLUMN request_id DROP NOT NULL"),
    ("Add broker_health table",
     """CREATE TABLE IF NOT EXISTS broker_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        broker_id INTEGER NOT NULL UNIQUE,
        consecutive_failures INTEGER DEFAULT 0,
        total_attempts INTEGER DEFAULT 0,
        total_successes INTEGER DEFAULT 0,
        total_failures INTEGER DEFAULT 0,
        last_success_at DATETIME,
        last_failure_at DATETIME,
        last_failure_reason VARCHAR,
        last_failure_detail TEXT,
        auto_disabled BOOLEAN DEFAULT 0,
        auto_disabled_at DATETIME,
        auto_disabled_reason VARCHAR,
        needs_review BOOLEAN DEFAULT 0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
     )"""),
]


def run_institutional_migrations():
    with engine.connect() as conn:
        for desc, sql in INSTITUTIONAL_MIGRATIONS:
            try:
                conn.execute(text(sql))
                conn.commit()
                log.info(f"Migration applied: {desc}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    pass
                else:
                    log.warning(f"Migration '{desc}' skipped: {e}")
