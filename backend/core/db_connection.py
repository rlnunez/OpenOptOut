"""
Enterprise PostgreSQL connection builder.

Security model:
  - Non-secret connection parameters (host, port, sslmode, dbname, IAM region)
    may come from the settings UI or environment variables.
  - SECRET material (passwords, tokens, private keys, certificates) is NEVER
    stored in the app database or settings file. It is read from:
      * environment variables (Docker secrets, K8s secrets, Vault injection), or
      * mounted files whose paths are configured, with the file owned and
        permissioned by the DBA outside the application.
  - The application only ever READS secret files; it never writes or logs them.

Supported authentication methods:
  1. password        — username/password (SCRAM-SHA-256), optionally over SSL
  2. ssl_password    — password over verified TLS
  3. client_cert     — mutual TLS with client certificate (no password)
  4. cert_and_password — client cert + password (defense in depth)
  5. iam_aws         — AWS RDS IAM authentication (short-lived tokens)
  6. iam_gcp         — GCP Cloud SQL IAM authentication
  7. iam_azure       — Azure AD token authentication
  8. gssapi          — Kerberos / GSSAPI (enterprise SSO)

Connection is assembled into a SQLAlchemy URL + connect_args dict.
"""

import os
import logging
from typing import Optional
from urllib.parse import quote_plus

log = logging.getLogger(__name__)


# ── Secret resolution ─────────────────────────────────────────────────────────

def _resolve_secret(env_var: Optional[str], file_path: Optional[str]) -> Optional[str]:
    """
    Resolve a secret value from (in priority order):
      1. An environment variable (e.g. Docker/K8s secret, Vault injection)
      2. A mounted file whose path is given (the file content is the secret)

    Returns None if neither is set. Never logs the secret value.
    """
    if env_var and os.getenv(env_var):
        return os.getenv(env_var)
    if file_path and os.path.exists(file_path):
        # e.g. Docker secret at /run/secrets/db_password
        try:
            with open(file_path, "r") as f:
                return f.read().strip()
        except Exception as e:
            log.error(f"Could not read secret file {file_path}: {e}")
            return None
    return None


def _file_must_exist(path: Optional[str], label: str) -> Optional[str]:
    """Validate that a cert/key file path exists and is readable."""
    if not path:
        return None
    if not os.path.exists(path):
        log.error(f"{label} file not found: {path}")
        raise FileNotFoundError(f"{label} not found at {path}")
    # Warn if a private key is world-readable
    if "key" in label.lower():
        try:
            mode = oct(os.stat(path).st_mode)[-3:]
            if mode not in ("600", "400"):
                log.warning(
                    f"{label} at {path} has permissions {mode}. "
                    f"Recommended: chmod 600 (owner read/write only)."
                )
        except Exception:
            pass
    return path


# ── Connection config loader ──────────────────────────────────────────────────

def get_db_config() -> dict:
    """
    Load database connection configuration.

    Non-secret settings come from environment variables (preferred for
    infrastructure config) or the settings file (for UI-configured options).
    Secrets are resolved separately via _resolve_secret at connection time.

    Environment variables (all optional; UI settings used as fallback):
      DB_HOST, DB_PORT, DB_NAME, DB_USER
      DB_AUTH_METHOD   — one of the supported methods above
      DB_SSLMODE       — disable|allow|prefer|require|verify-ca|verify-full
      DB_SSLROOTCERT   — path to CA certificate (mounted file)
      DB_SSLCERT       — path to client certificate (mounted file)
      DB_SSLKEY        — path to client private key (mounted file, chmod 600)
      DB_PASSWORD or DB_PASSWORD_FILE   — password secret
      DB_IAM_REGION    — for AWS/GCP/Azure IAM auth
      DB_GSSAPI_PRINCIPAL — for Kerberos
    """
    from .settings_store import load_settings

    s      = load_settings()
    dbcfg  = s.get("database", {})

    def env_or_setting(env_key: str, setting_key: str, default=None):
        return os.getenv(env_key) or dbcfg.get(setting_key, default)

    return {
        "auth_method": env_or_setting("DB_AUTH_METHOD", "auth_method", "password"),
        "host":        env_or_setting("DB_HOST",        "host",        "localhost"),
        "port":        int(env_or_setting("DB_PORT",    "port",        5432)),
        "dbname":      env_or_setting("DB_NAME",        "dbname",      "privacyshield"),
        "user":        env_or_setting("DB_USER",        "user",        "privacyshield"),
        "sslmode":     env_or_setting("DB_SSLMODE",     "sslmode",     "prefer"),
        # Cert/key file paths (paths are non-secret; the files they point to are secret)
        "sslrootcert": env_or_setting("DB_SSLROOTCERT", "sslrootcert", None),
        "sslcert":     env_or_setting("DB_SSLCERT",     "sslcert",     None),
        "sslkey":      env_or_setting("DB_SSLKEY",      "sslkey",      None),
        # Secret references (resolved at connect time, never stored)
        "password_env":  "DB_PASSWORD",
        "password_file": os.getenv("DB_PASSWORD_FILE"),
        # IAM
        "iam_region":  env_or_setting("DB_IAM_REGION",  "iam_region",  None),
        # Kerberos
        "gssapi_principal": env_or_setting("DB_GSSAPI_PRINCIPAL", "gssapi_principal", None),
    }


# ── URL + connect_args builder ────────────────────────────────────────────────

def build_postgres_connection() -> Optional[tuple[str, dict]]:
    """
    Build a (sqlalchemy_url, connect_args) tuple for PostgreSQL.

    Returns None if the deployment is not using structured Postgres config
    (i.e. it's using a plain DATABASE_URL or SQLite instead).

    The returned connect_args carries SSL and auth material for psycopg2.
    """
    # If a full DATABASE_URL is set and structured config isn't requested,
    # let the caller use the URL directly.
    database_url = os.getenv("DATABASE_URL", "")
    use_structured = os.getenv("DB_USE_STRUCTURED_CONFIG", "").lower() in ("1", "true", "yes")

    from .settings_store import load_settings
    s = load_settings()
    if not use_structured and not s.get("database", {}).get("enabled"):
        return None   # use DATABASE_URL / SQLite path

    cfg = get_db_config()
    method = cfg["auth_method"]

    connect_args: dict = {}

    # ── SSL configuration (applies to all methods) ──
    sslmode = cfg["sslmode"]
    if sslmode and sslmode != "disable":
        connect_args["sslmode"] = sslmode

        # CA certificate — required for verify-ca / verify-full
        if cfg["sslrootcert"]:
            connect_args["sslrootcert"] = _file_must_exist(cfg["sslrootcert"], "CA certificate")

        if sslmode in ("verify-ca", "verify-full") and not cfg["sslrootcert"]:
            log.warning(
                f"sslmode={sslmode} requires a CA certificate (DB_SSLROOTCERT). "
                f"Connection may fail without it."
            )

    # ── Method-specific configuration ──
    password = None

    if method in ("password", "ssl_password"):
        password = _resolve_secret(cfg["password_env"], cfg["password_file"])
        if not password:
            log.error("Password auth selected but no password found in DB_PASSWORD or DB_PASSWORD_FILE")

    elif method == "client_cert":
        # Mutual TLS — client presents cert + key, NO password
        connect_args["sslcert"] = _file_must_exist(cfg["sslcert"], "Client certificate")
        connect_args["sslkey"]  = _file_must_exist(cfg["sslkey"],  "Client private key")
        if sslmode not in ("verify-ca", "verify-full"):
            log.warning("client_cert auth should use sslmode=verify-full for full security")

    elif method == "cert_and_password":
        # Both client cert AND password
        connect_args["sslcert"] = _file_must_exist(cfg["sslcert"], "Client certificate")
        connect_args["sslkey"]  = _file_must_exist(cfg["sslkey"],  "Client private key")
        password = _resolve_secret(cfg["password_env"], cfg["password_file"])

    elif method == "iam_aws":
        # AWS RDS IAM — generate a short-lived auth token
        password = _generate_aws_iam_token(cfg)
        connect_args["sslmode"] = "verify-full"  # AWS requires SSL for IAM
        if cfg["sslrootcert"]:
            connect_args["sslrootcert"] = cfg["sslrootcert"]

    elif method == "iam_gcp":
        # GCP Cloud SQL IAM — uses the Cloud SQL connector or OAuth token
        password = _generate_gcp_iam_token(cfg)

    elif method == "iam_azure":
        # Azure AD token authentication
        password = _generate_azure_ad_token(cfg)
        connect_args["sslmode"] = "require"

    elif method == "gssapi":
        # Kerberos / GSSAPI — no password, uses ticket cache
        connect_args["gssencmode"] = "prefer"
        if cfg["gssapi_principal"]:
            connect_args["krbsrvname"] = "postgres"

    # ── Assemble the SQLAlchemy URL ──
    # Password (if any) goes in connect_args, NOT the URL, to avoid logging it.
    user_enc = quote_plus(cfg["user"])
    url = f"postgresql+psycopg2://{user_enc}@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"

    if password:
        connect_args["password"] = password

    log.info(
        f"Postgres connection configured: host={cfg['host']} db={cfg['dbname']} "
        f"user={cfg['user']} method={method} sslmode={sslmode}"
    )

    return url, connect_args


# ── Cloud IAM token generators ────────────────────────────────────────────────

def _generate_aws_iam_token(cfg: dict) -> Optional[str]:
    """
    Generate an AWS RDS IAM authentication token.
    Requires boto3 and AWS credentials (via IAM role, env, or ~/.aws).
    Token is valid for 15 minutes — regenerated on each new connection.
    """
    try:
        import boto3
        region = cfg["iam_region"] or os.getenv("AWS_REGION", "us-east-1")
        client = boto3.client("rds", region_name=region)
        token = client.generate_db_auth_token(
            DBHostname=cfg["host"],
            Port=cfg["port"],
            DBUsername=cfg["user"],
            Region=region,
        )
        log.info("Generated AWS RDS IAM auth token")
        return token
    except ImportError:
        log.error("AWS IAM auth requires boto3 — pip install boto3")
        return None
    except Exception as e:
        log.error(f"AWS IAM token generation failed: {e}")
        return None


def _generate_gcp_iam_token(cfg: dict) -> Optional[str]:
    """
    Generate a GCP Cloud SQL IAM OAuth2 access token.
    Requires google-auth and appropriate service account credentials.
    """
    try:
        import google.auth
        import google.auth.transport.requests
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/sqlservice.login"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        log.info("Generated GCP Cloud SQL IAM token")
        return credentials.token
    except ImportError:
        log.error("GCP IAM auth requires google-auth — pip install google-auth")
        return None
    except Exception as e:
        log.error(f"GCP IAM token generation failed: {e}")
        return None


def _generate_azure_ad_token(cfg: dict) -> Optional[str]:
    """
    Generate an Azure AD access token for Azure Database for PostgreSQL.
    Requires azure-identity and a managed identity or service principal.
    """
    try:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
        log.info("Generated Azure AD auth token")
        return token.token
    except ImportError:
        log.error("Azure AD auth requires azure-identity — pip install azure-identity")
        return None
    except Exception as e:
        log.error(f"Azure AD token generation failed: {e}")
        return None


# ── Connection test ───────────────────────────────────────────────────────────

def test_connection() -> dict:
    """Test the configured Postgres connection without exposing secrets."""
    result = build_postgres_connection()
    if not result:
        return {"configured": False, "message": "Structured Postgres config not enabled"}

    url, connect_args = result
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            ssl_info = conn.execute(text(
                "SELECT ssl, version FROM pg_stat_ssl "
                "JOIN pg_stat_activity USING (pid) WHERE pid = pg_backend_pid()"
            )).fetchone()
        engine.dispose()
        return {
            "configured": True,
            "connected": True,
            "server_version": version.split(" ")[1] if version else None,
            "ssl_active": bool(ssl_info[0]) if ssl_info else False,
            "ssl_version": ssl_info[1] if ssl_info and len(ssl_info) > 1 else None,
        }
    except Exception as e:
        # Sanitize error — never echo back secret material
        err = str(e)
        for secret_marker in ("password", "token", "key"):
            if secret_marker in err.lower():
                err = "Connection failed (credentials error — check secret configuration)"
                break
        return {"configured": True, "connected": False, "error": err}
