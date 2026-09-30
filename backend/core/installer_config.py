"""
OpenOptOut Unified Host & Fleet Installer Configuration Engine (Roadmap Item 23).

Defines cluster role profiles, system dependency matrices, Nginx site configuration
templates, systemd unit templates, and environment file generation for standalone,
control-plane, and worker fleet nodes.
"""

import os
import secrets
from typing import Dict, List, Optional, Set, Tuple


class Role:
    STANDALONE = "standalone"
    CONTROL_PLANE = "control-plane"
    WORKER = "worker"
    ALL = (STANDALONE, CONTROL_PLANE, WORKER)


class DatabaseEngine:
    SQLITE = "sqlite"
    POSTGRESQL = "postgres"
    SQLCIPHER = "sqlcipher"
    ALL = (SQLITE, POSTGRESQL, SQLCIPHER)


# Base operating system packages required across all native installations
BASE_OS_PACKAGES = [
    "python3",
    "python3-venv",
    "python3-dev",
    "wget",
    "curl",
    "ca-certificates",
    "rsync",
    "gcc",
    "build-essential",
]

# Browser automation & sandboxing packages (for Standalone and Worker roles)
BROWSER_AND_SANDBOX_PACKAGES = [
    "bubblewrap",
    "libseccomp2",
    "python3-seccomp",
    "fonts-liberation",
    "libatk-bridge2.0-0",
    "libatk1.0-0",
    "libcups2",
    "libdbus-1-3",
    "libdrm2",
    "libgbm1",
    "libgtk-3-0",
    "libnspr4",
    "libnss3",
    "libx11-xcb1",
    "libxcomposite1",
    "libxdamage1",
    "libxfixes3",
    "libxrandr2",
    "libxss1",
    "libxtst6",
    "xdg-utils",
]

# Web server & identity protocol headers (for Standalone and Control Plane roles)
WEB_AND_IDENTITY_PACKAGES = [
    "nginx",
    "xmlsec1",
    "libldap2-dev",
    "libsasl2-dev",
]


def get_packages_for_role(role: str) -> List[str]:
    """
    Returns the distinct list of required Debian/Ubuntu OS packages for a given role.

    Role characteristics:
    - standalone: installs all base, browser/sandbox, and web/identity packages.
    - control-plane: installs base and web/identity packages. EXCLUDES Playwright,
      Firefox, Bubblewrap, and X11 graphics packages (>1.5GB savings).
    - worker: installs base and browser/sandbox packages. EXCLUDES Nginx, Node.js,
      frontend build tools, and web identity packages.
    """
    role = role.lower()
    if role not in Role.ALL:
        raise ValueError(f"Unknown role: {role}. Must be one of {Role.ALL}")

    pkgs = list(BASE_OS_PACKAGES)

    if role in (Role.STANDALONE, Role.CONTROL_PLANE):
        pkgs.extend(WEB_AND_IDENTITY_PACKAGES)

    if role in (Role.STANDALONE, Role.WORKER):
        pkgs.extend(BROWSER_AND_SANDBOX_PACKAGES)

    # Return deduplicated while preserving order
    seen: Set[str] = set()
    result: List[str] = []
    for pkg in pkgs:
        if pkg not in seen:
            seen.add(pkg)
            result.append(pkg)
    return result


def requires_frontend_build(role: str) -> bool:
    """Returns True if the role requires building and serving the React frontend."""
    return role in (Role.STANDALONE, Role.CONTROL_PLANE)


def requires_nginx(role: str) -> bool:
    """Returns True if the role requires Nginx reverse proxy configuration."""
    return role in (Role.STANDALONE, Role.CONTROL_PLANE)


def requires_playwright_browsers(role: str) -> bool:
    """Returns True if the role requires Playwright browser binaries (Firefox)."""
    return role in (Role.STANDALONE, Role.WORKER)


def generate_nginx_config(
    domain: str,
    frontend_root: str = "/opt/openoptout/frontend/dist",
    api_host: str = "127.0.0.1",
    api_port: int = 8000,
    client_max_body_size: str = "50M",
) -> str:
    """
    Generates an optimized Nginx server block configuration for OpenOptOut.
    Includes SPA routing, API reverse proxying, WebSocket upgrade headers,
    SSE streaming settings, and standard security headers.
    """
    domain = domain.strip() if domain else "localhost"
    return f"""# OpenOptOut — Nginx Reverse Proxy Configuration (Roadmap Item 23)
server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    root {frontend_root};
    index index.html;

    client_max_body_size {client_max_body_size};

    # Reverse proxy for FastAPI backend with WebSockets and SSE support
    location /api/ {{
        proxy_pass http://{api_host}:{api_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Disable proxy buffering for Server-Sent Events (SSE) and live log streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }}

    # Single Page Application (SPA) routing fallback
    location / {{
        try_files $uri $uri/ /index.html;
    }}

    # Security defense-in-depth headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}}
"""


def generate_systemd_api_service(
    install_dir: str = "/opt/openoptout",
    user: str = "openoptout",
    workers: int = 2,
    port: int = 8000,
) -> str:
    """Generates the systemd unit definition for the API web service."""
    return f"""[Unit]
Description=OpenOptOut API
After=network.target
Wants=network.target

[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={install_dir}
EnvironmentFile={install_dir}/.env
ExecStart={install_dir}/venv/bin/uvicorn app.main:app \\
    --host 127.0.0.1 --port {port} --workers {workers}
Restart=on-failure
RestartSec=5

# Service hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={install_dir}/data /var/log/openoptout

[Install]
WantedBy=multi-user.target
"""


def generate_systemd_worker_service(
    install_dir: str = "/opt/openoptout",
    user: str = "openoptout",
) -> str:
    """Generates the systemd unit definition for the headless worker daemon."""
    return f"""[Unit]
Description=OpenOptOut Stateless Worker Daemon
After=network.target
Wants=network.target

[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={install_dir}
EnvironmentFile={install_dir}/.env
ExecStart={install_dir}/venv/bin/python -m app.worker
Restart=always
RestartSec=5

# Service hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={install_dir}/data /var/log/openoptout

[Install]
WantedBy=multi-user.target
"""


def generate_env_config(
    role: str,
    secret_key: Optional[str] = None,
    database_url: Optional[str] = None,
    redis_url: Optional[str] = None,
    worker_id: Optional[str] = None,
    worker_concurrency: int = 1,
    domain: Optional[str] = None,
    install_dir: str = "/opt/openoptout",
    sqlcipher_key: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generates key-value configuration pairs for the .env file tailored to the node's cluster role.
    """
    role = role.lower()
    if role not in Role.ALL:
        raise ValueError(f"Unknown role: {role}")

    secret = secret_key or secrets.token_hex(32)
    env: Dict[str, str] = {
        "ROLE": role,
        "SECRET_KEY": secret,
    }

    # Storage paths
    env["SETTINGS_FILE"] = f"{install_dir}/data/openoptout_settings.json"
    env["LOGO_PATH"] = f"{install_dir}/data/logo"

    # Frontend URL & Domain
    dom = domain.strip() if domain else "localhost"
    proto = "http" if dom in ("localhost", "127.0.0.1") else "https"
    env["FRONTEND_URL"] = f"{proto}://{dom}"

    # Database configuration (Standalone & Control Plane require DB; Worker is stateless)
    if role in (Role.STANDALONE, Role.CONTROL_PLANE):
        if database_url:
            env["DATABASE_URL"] = database_url
        else:
            env["DATABASE_URL"] = f"sqlite:////{install_dir}/data/openoptout.db"

        if sqlcipher_key:
            env["SQLCIPHER_KEY"] = sqlcipher_key

    # Distributed queue & worker settings
    if redis_url:
        env["REDIS_URL"] = redis_url

    if role == Role.WORKER:
        env["WORKER_ID"] = worker_id or f"worker-{secrets.token_hex(4)}"
        env["WORKER_CONCURRENCY"] = str(worker_concurrency)
        # Workers operate in headless mode by default
        env["HEADLESS"] = "true"

    return env


def format_env_file(config: Dict[str, str]) -> str:
    """Formats a dictionary of key-value pairs into a standard .env file string."""
    lines = ["# OpenOptOut Environment Configuration", "# Generated by OpenOptOut Installer (Item 23)", ""]
    for k, v in sorted(config.items()):
        # Escape any double quotes if value contains spaces
        if " " in v and not v.startswith('"'):
            val = f'"{v}"'
        else:
            val = v
        lines.append(f"{k}={val}")
    lines.append("")
    return "\n".join(lines)
