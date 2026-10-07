# Native install (no Docker)

Docker running on a VM or bare metal is a fully supported, common way to run OpenOptOut in an institutional setting (see the main [README](../README.md) and [docs/HTTPS.md](HTTPS.md)). This doc is for the other real case: **no container runtime at all** — often by policy, not by choice, at institutions whose IT department doesn't run Docker. OpenOptOut runs as an ordinary native process either way: systemd on Linux, a Windows Service on Windows.

If you *can* use Docker, it's the lower-maintenance path (one image, one `docker compose up -d`, automatic HTTPS via one script) — this doc is for when that's genuinely not an option.

## Linux (Debian/Ubuntu)

### What you end up with

```
/opt/openoptout/
├── app/            the backend, laid out as an importable Python package
├── venv/           Python virtual environment
├── frontend/dist/  the built React frontend (static files)
├── data/           settings, uploaded logos, plugin storage, screenshots
└── .env            configuration (same keys as .env.example)
```

- **systemd** runs the API (`uvicorn app.main:app`) as the `openoptout` system user, on `127.0.0.1:8000` only — nothing external talks to it directly.
- **nginx** serves the built frontend and reverse-proxies `/api/` to that local port — this is OpenOptOut's actual public-facing surface.
- **certbot** (optional, for HTTPS) edits the nginx site directly and renews itself via its own systemd timer.

This mirrors the Docker image closely on purpose — same Python dependencies, same `app` package layout (main.py's relative imports need it), same Playwright/Firefox setup for the opt-out automation engine, same optional SQLCipher encryption.

### Install (Unified Interactive Host & Fleet Installer)

OpenOptOut features a unified interactive terminal installer (TUI) with role specialization (Roadmap Item 23). It can be executed directly or via one-line curl:

```bash
# Interactive terminal wizard (detects whiptail or ANSI terminal)
curl -fsSL https://raw.githubusercontent.com/rlnunez/OpenOptOut/main/install.sh | sudo bash

# Or run locally from a git clone
git clone https://github.com/rlnunez/OpenOptOut.git openoptout
cd openoptout
sudo ./deploy/installer/setup.sh
```

#### Cluster Role Specialization

The installer prompts for (or accepts via `--role`) three distinct deployment profiles:

1. **Standalone / All-in-One (`--role standalone`):**
   - Provisions Web UI, FastAPI, database, and local Playwright browser automation on a single host.
2. **Control Plane / UI Server (`--role control-plane`):**
   - Installs Web UI, API, Nginx, and Redis task dispatchers.
   - **Excludes** Playwright, Firefox, Bubblewrap, and X11 graphics packages, saving over **1.5GB of disk** and reducing memory footprint.
3. **Stateless Worker Fleet Node (`--role worker`):**
   - Installs the worker daemon, Bubblewrap sandbox, and Playwright Firefox.
   - **Excludes** Nginx, Node.js, npm, frontend builds, and public web endpoints, creating hardened headless compute instances.

#### Scriptable Non-Interactive Installation

For automated orchestration (Ansible, Cloud-Init, CI/CD), supply flags with `--unattended`:

```bash
# Standalone with automated PostgreSQL and Let's Encrypt TLS:
sudo ./deploy/installer/setup.sh --role standalone --db postgres --domain privacy.example.org --email admin@example.org --tls letsencrypt --unattended

# Control Plane backed by external PostgreSQL and Redis:
sudo ./deploy/installer/setup.sh --role control-plane --db-url "postgresql://user:pass@db:5432/openoptout" --queue "redis://redis:6379/0" --domain privacy.example.org --unattended

# Stateless Worker Node connecting to Redis queue:
sudo ./deploy/installer/setup.sh --role worker --queue "redis://control-plane.internal:6379/0" --worker-id "worker-01" --concurrency 4 --secret-key "SHARED_CLUSTER_KEY" --unattended
```

The installer handles user creation, storage permissions, OS packages, Python venv, database provisioning, automated Nginx configuration with WebSockets/SSE, TLS certification via Certbot, and systemd service startup with pre-flight health validation.


### Updating

```
cd openoptout && git pull
sudo ./deploy/native/install.sh --update
sudo systemctl restart openoptout-api
sudo systemctl reload nginx
```

`--update` re-runs the build steps (venv/pip, proto compile, frontend build) without touching `.env` or `/opt/openoptout/data`.

### Database migrations, backups, logs

- Migrations run automatically at API startup (same as the Docker image) — `sudo systemctl restart openoptout-api` applies them.
- SQLite lives at whatever `SETTINGS_FILE`'s directory implies unless you set `DATABASE_URL` to Postgres — back up `/opt/openoptout/data/` the same way you'd back up the Docker `app_data` volume.
- Logs: `sudo journalctl -u openoptout-api -f` (the API), `sudo journalctl -u nginx` / `/var/log/nginx/error.log` (nginx), `sudo journalctl -u certbot` (renewal, once HTTPS is on).

### Plugin sandboxing

The plugin system's OS-level sandboxing uses Linux namespaces via `bubblewrap` — this works the same on a native install as it does in the Docker image, since it's a kernel feature, not a container-runtime one. If you enable the plugin system and plugins fail to start, the first thing to try is loosening `deploy/native/openoptout-api.service`'s hardening (`ProtectSystem`/`ProtectHome`) — see the comments in that file — before troubleshooting further. See [docs/PLUGINS.md](PLUGINS.md).

### Host-Level Security Hardening (Core Dumps & Encrypted Swap)

Because OpenOptOut handles sensitive patron identities, credentials, and encryption keys in memory, preventing process memory from being persisted unencrypted to physical storage is essential:

1. **Core Dump Prevention (`ulimit -c 0` / `LimitCORE=0`)**:
   - Both `openoptout-api.service` and `openoptout-worker.service` enforce `LimitCORE=0`, and the application calls `resource.setrlimit(RLIMIT_CORE, (0, 0))` on startup.
   - For global host enforcement, the installer writes `/etc/security/limits.d/99-openoptout.conf` (`openoptout soft/hard core 0`) and sets `fs.suid_dumpable = 0` via sysctl.
   - This ensures that in the event of an unhandled crash or kernel panic, process memory containing decrypted PII or secrets is never written to disk.

2. **Encrypted Swap**:
   - Under kernel memory pressure, anonymous memory pages may be swapped to disk. If the host uses unencrypted swap, decrypted PII could be recovered from disk blocks.
   - **Recommendation**: Deploy on a host with no swap (pure RAM) or enable ephemeral encrypted swap using `dm-crypt` / `crypttab`:
     ```ini
     # In /etc/crypttab:
     cryptswap /dev/sdX2 /dev/urandom swap,cipher=aes-xts-plain64,size=512
     ```
     With a `/dev/urandom` key source, the swap encryption key is regenerated randomly on every system boot, guaranteeing zero data recovery after shutdown.
   - The interactive installer (`deploy/installer/setup.sh`) automatically audits `/proc/swaps` and alerts operators if an unencrypted swap device is active.

## Windows Server

Windows has no direct systemd equivalent, so the pieces map slightly differently, but the shape is the same: something supervises the API process, and IIS is the public-facing web server.

### What you end up with

- **A Windows Service**, running the API (`uvicorn app.main:app`) on `127.0.0.1:8000`, registered via [NSSM](https://nssm.cc/) (a small, well-established open-source tool for running any executable as a Windows Service — there's no built-in equivalent of a systemd unit file).
- **IIS**, serving the built frontend as static files and reverse-proxying `/api/` to that local port, via the free **Application Request Routing (ARR)** and **URL Rewrite** modules.
- **win-acme**, for HTTPS — obtains a Let's Encrypt certificate, installs it into IIS's site binding, and registers its own renewal task. This is the Windows-side equivalent of what certbot does for nginx, or what Caddy does in the Docker managed option.

### Install

**Option 1 — automated (steps 2-6 below):**
```powershell
git clone https://github.com/rlnunez/OpenOptOut.git C:\OpenOptOut
cd C:\OpenOptOut
.\deploy\native\install-native.ps1
```
This does the venv, `pip install`, Playwright's Firefox (best-effort — see `-SkipPlaywright` if that download is blocked by a corporate proxy, same as the Linux note above), the `app`-package layout, proto stub compilation, and the frontend build for you, then prints the exact commands for steps 7-9 below (NSSM, IIS, win-acme) — those aren't reliably automatable across Windows Server versions the way a single script can handle Linux's systemd + certbot, so they stay manual. Skip ahead to step 7.

**Option 2 — manual**, if you'd rather do each step yourself or hit something the script doesn't handle for your setup:

1. **Install Python 3.12** and **Node.js LTS** (for building the frontend).
2. **Clone the repo** and set up the backend:
   ```powershell
   git clone https://github.com/rlnunez/OpenOptOut.git C:\OpenOptOut
   cd C:\OpenOptOut\backend
   python -m venv venv
   .\venv\Scripts\pip install -r requirements.txt
   .\venv\Scripts\playwright install firefox
   ```
   (If the Playwright download fails behind a corporate proxy, the same note as the Linux section applies — the app still works; automated opt-outs won't until you can retry that command.)
3. **Lay the backend out as the `app` package**, same reason as Linux (the code uses relative imports): copy `backend\` to `C:\OpenOptOut\app\`, and create empty `__init__.py` files in `app\`, `app\models\`, `app\routers\`, and `app\core\`.
4. **Compile the plugin protocol stubs** (best-effort — the plugin system just stays inactive if this fails):
   ```powershell
   cd C:\OpenOptOut
   .\backend\venv\Scripts\python -m grpc_tools.protoc -Iapp\plugins\proto --python_out=app\plugins\proto --grpc_python_out=app\plugins\proto app\plugins\proto\plugin.proto
   ```
   Then edit `app\plugins\proto\plugin_pb2_grpc.py`, changing `import plugin_pb2 as` to `from . import plugin_pb2 as`, and add an empty `app\plugins\proto\__init__.py`.
5. **Build the frontend:**
   ```powershell
   cd C:\OpenOptOut\frontend
   npm install
   npm run build
   ```
   (`frontend\dist\` is what IIS will serve.)
6. **Create `.env`:**
   ```powershell
   cd C:\OpenOptOut
   Copy-Item .env.example .env
   ```
   Edit it: set `SECRET_KEY` to a random value, add `SETTINGS_FILE=C:\OpenOptOut\data\openoptout_settings.json` and `LOGO_PATH=C:\OpenOptOut\data\logo`, and create that `data` folder.
7. **Register the Windows Service with NSSM:**
   ```powershell
   nssm install OpenOptOutAPI "C:\OpenOptOut\backend\venv\Scripts\uvicorn.exe" "app.main:app --host 127.0.0.1 --port 8000 --workers 2"
   nssm set OpenOptOutAPI AppDirectory "C:\OpenOptOut"
   nssm set OpenOptOutAPI AppEnvironmentExtra (Get-Content .env | Where-Object { $_ -match '=' })
   nssm start OpenOptOutAPI
   ```
   Confirm it's up: `Invoke-WebRequest http://127.0.0.1:8000/api/health` should return `{"status":"ok"}`.
8. **Set up IIS:**
   - Install the **Application Request Routing (ARR)** and **URL Rewrite** modules (free, from Microsoft's IIS download page).
   - In IIS Manager, enable ARR's proxy feature (Server node → Application Request Routing Cache → Server Proxy Settings → **Enable proxy**).
   - Create a site with its physical path pointed at `C:\OpenOptOut\frontend\dist`.
   - Add a URL Rewrite rule: requests to `/api/*` reverse-proxy to `http://127.0.0.1:8000/{R:0}`; everything else falls through to `index.html` (a standard SPA rewrite rule — IIS's URL Rewrite has a built-in template for this).
   - In that rule's **Server Variables**, add/set `HTTP_X_FORWARDED_PROTO` to `https` once HTTPS is on (step 9) so OpenOptOut knows the original request scheme.
9. **Turn on HTTPS with win-acme:**
   - Download [win-acme](https://www.win-acme.com/) and run `wacs.exe`.
   - Point it at your IIS site; it obtains a Let's Encrypt certificate, installs it into the site's HTTPS binding, and registers a scheduled task for renewal — no further action needed.
   - Set `FRONTEND_URL=https://your-domain` in `.env`, update the NSSM service's environment (`nssm set OpenOptOutAPI AppEnvironmentExtra ...` again, or `nssm edit OpenOptOutAPI`), and restart it: `nssm restart OpenOptOutAPI`.
10. Open `https://your-domain/` — the first user to register becomes the super admin.

### Updating

```powershell
cd C:\OpenOptOut
git pull
.\deploy\native\install-native.ps1 -Update    # or re-run steps 2-5 manually
nssm restart OpenOptOutAPI
```

### Confirming HTTPS actually worked (either OS)

Once you're logged in as a super admin, the **dashboard** shows a live check (with a **Check again** button) confirming whether the certificate is actually valid — a real answer, not a guess from the browser's own address bar. This is the same check used on the Docker/managed path; see [docs/HTTPS.md](HTTPS.md#confirming-it-actually-worked) for why the app can't just run these steps and show you the output itself (it deliberately has no OS-level service control or live access to `.env`, on either platform).

## See also

- [docs/HTTPS.md](HTTPS.md) — the Docker (managed), native, and external reverse-proxy paths compared side by side, plus troubleshooting.
- [docs/SSO.md](SSO.md) — LDAP/SIP2/OIDC/SAML setup; the reverse-proxy section there applies the same way to a native install.
- [docs/PLUGINS.md](PLUGINS.md) — the plugin sandboxing model.
