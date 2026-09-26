# Native install (no Docker)

Docker running on a VM or bare metal is a fully supported, common way to run
PrivacyShield in an institutional setting (see the main [README](../README.md)
and [docs/HTTPS.md](HTTPS.md)). This doc is for the other real case: **no
container runtime at all** — often by policy, not by choice, at institutions
whose IT department doesn't run Docker. PrivacyShield runs as an ordinary
native process either way: systemd on Linux, a Windows Service on Windows.

If you *can* use Docker, it's the lower-maintenance path (one image, one
`docker compose up -d`, automatic HTTPS via one script) — this doc is for
when that's genuinely not an option.

## Linux (Debian/Ubuntu)

### What you end up with

```
/opt/privacyshield/
├── app/            the backend, laid out as an importable Python package
├── venv/           Python virtual environment
├── frontend/dist/  the built React frontend (static files)
├── data/           settings, uploaded logos, plugin storage, screenshots
└── .env            configuration (same keys as .env.example)
```

- **systemd** runs the API (`uvicorn app.main:app`) as the `privacyshield`
  system user, on `127.0.0.1:8000` only — nothing external talks to it
  directly.
- **nginx** serves the built frontend and reverse-proxies `/api/` to that
  local port — this is PrivacyShield's actual public-facing surface.
- **certbot** (optional, for HTTPS) edits the nginx site directly and renews
  itself via its own systemd timer.

This mirrors the Docker image closely on purpose — same Python dependencies,
same `app` package layout (main.py's relative imports need it), same
Playwright/Firefox setup for the opt-out automation engine, same optional
SQLCipher encryption.

### Install

Distro support: `deploy/native/install.sh` targets **Debian/Ubuntu** (it uses
`apt-get`). On RHEL/Rocky/openSUSE/other distros, install the equivalent
packages by hand (the script's apt list documents exactly what's needed) and
run the venv/pip/npm steps yourself — the systemd unit and nginx config are
distro-agnostic.

```
git clone https://github.com/rlnunez/Privacy-Shield.git privacyshield
cd privacyshield
sudo ./deploy/native/install.sh
```

This creates a `privacyshield` system user, installs OS packages (Playwright's
Firefox dependencies, `bubblewrap`+`libseccomp` for plugin sandboxing,
`libldap`/`libsasl` headers, `xmlsec1`, `nginx`, `rsync`), builds a venv,
installs Python dependencies, installs Playwright's Firefox, compiles the
plugin gRPC stubs, builds the frontend, and installs the systemd unit. On
first run it also creates `/opt/privacyshield/.env` from `.env.example` with
a freshly generated `SECRET_KEY`.

**If Playwright's Firefox download fails** (common behind a corporate
firewall/proxy that blocks Microsoft's CDN, `*.azureedge.net`) — the script
warns and keeps going rather than aborting; the app still works, but
automated opt-out form submission won't until you retry it manually once
network access allows it (the warning prints the exact command). Everything
else — SSO/LDAP/SIP2 sign-in, manual opt-outs, the dashboard, reporting — is
unaffected either way.

Then, following the script's own final printout:

```
# 1. Review the config
sudo nano /opt/privacyshield/.env        # database, email, etc — see .env.example

# 2. Start the API
sudo systemctl enable --now privacyshield-api
sudo systemctl status privacyshield-api   # should be "active (running)"
curl http://127.0.0.1:8000/api/health     # {"status":"ok"}

# 3. Install the nginx site
sudo cp deploy/native/nginx-privacyshield.conf.example /etc/nginx/sites-available/privacyshield
sudo nano /etc/nginx/sites-available/privacyshield   # replace YOUR_DOMAIN
sudo ln -s /etc/nginx/sites-available/privacyshield /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 4. Open http://your-server/ — the first user to register becomes the super admin

# 5. Turn on HTTPS (see docs/HTTPS.md's Native section for the full explanation)
sudo apt-get install certbot python3-certbot-nginx
sudo ./scripts/enable-https-native.sh --domain privacy.yourlibrary.org --email it@yourlibrary.org
sudo systemctl restart privacyshield-api
```

### Updating

```
cd privacyshield && git pull
sudo ./deploy/native/install.sh --update
sudo systemctl restart privacyshield-api
sudo systemctl reload nginx
```

`--update` re-runs the build steps (venv/pip, proto compile, frontend build)
without touching `.env` or `/opt/privacyshield/data`.

### Database migrations, backups, logs

- Migrations run automatically at API startup (same as the Docker image) —
  `sudo systemctl restart privacyshield-api` applies them.
- SQLite lives at whatever `SETTINGS_FILE`'s directory implies unless you
  set `DATABASE_URL` to Postgres — back up `/opt/privacyshield/data/` the
  same way you'd back up the Docker `app_data` volume.
- Logs: `sudo journalctl -u privacyshield-api -f` (the API),
  `sudo journalctl -u nginx` / `/var/log/nginx/error.log` (nginx),
  `sudo journalctl -u certbot` (renewal, once HTTPS is on).

### Plugin sandboxing

The plugin system's OS-level sandboxing uses Linux namespaces via
`bubblewrap` — this works the same on a native install as it does in the
Docker image, since it's a kernel feature, not a container-runtime one. If
you enable the plugin system and plugins fail to start, the first thing to
try is loosening `deploy/native/privacyshield-api.service`'s hardening
(`ProtectSystem`/`ProtectHome`) — see the comments in that file — before
troubleshooting further. See [docs/PLUGINS.md](PLUGINS.md).

## Windows Server

Windows has no direct systemd equivalent, so the pieces map slightly
differently, but the shape is the same: something supervises the API
process, and IIS is the public-facing web server.

### What you end up with

- **A Windows Service**, running the API (`uvicorn app.main:app`) on
  `127.0.0.1:8000`, registered via [NSSM](https://nssm.cc/) (a small,
  well-established open-source tool for running any executable as a Windows
  Service — there's no built-in equivalent of a systemd unit file).
- **IIS**, serving the built frontend as static files and reverse-proxying
  `/api/` to that local port, via the free **Application Request Routing
  (ARR)** and **URL Rewrite** modules.
- **win-acme**, for HTTPS — obtains a Let's Encrypt certificate, installs it
  into IIS's site binding, and registers its own renewal task. This is the
  Windows-side equivalent of what certbot does for nginx, or what Caddy does
  in the Docker managed option.

### Install

**Option 1 — automated (steps 2-6 below):**
```powershell
git clone https://github.com/rlnunez/Privacy-Shield.git C:\PrivacyShield
cd C:\PrivacyShield
.\deploy\native\install-native.ps1
```
This does the venv, `pip install`, Playwright's Firefox (best-effort — see
`-SkipPlaywright` if that download is blocked by a corporate proxy, same as
the Linux note above), the `app`-package layout, proto stub compilation, and
the frontend build for you, then prints the exact commands for steps 7-9
below (NSSM, IIS, win-acme) — those aren't reliably automatable across
Windows Server versions the way a single script can handle Linux's systemd +
certbot, so they stay manual. Skip ahead to step 7.

**Option 2 — manual**, if you'd rather do each step yourself or hit something
the script doesn't handle for your setup:

1. **Install Python 3.12** and **Node.js LTS** (for building the frontend).
2. **Clone the repo** and set up the backend:
   ```powershell
   git clone https://github.com/rlnunez/Privacy-Shield.git C:\PrivacyShield
   cd C:\PrivacyShield\backend
   python -m venv venv
   .\venv\Scripts\pip install -r requirements.txt
   .\venv\Scripts\playwright install firefox
   ```
   (If the Playwright download fails behind a corporate proxy, the same note
   as the Linux section applies — the app still works; automated opt-outs
   won't until you can retry that command.)
3. **Lay the backend out as the `app` package**, same reason as Linux (the
   code uses relative imports): copy `backend\` to `C:\PrivacyShield\app\`,
   and create empty `__init__.py` files in `app\`, `app\models\`,
   `app\routers\`, and `app\core\`.
4. **Compile the plugin protocol stubs** (best-effort — the plugin system
   just stays inactive if this fails):
   ```powershell
   cd C:\PrivacyShield
   .\backend\venv\Scripts\python -m grpc_tools.protoc -Iapp\plugins\proto --python_out=app\plugins\proto --grpc_python_out=app\plugins\proto app\plugins\proto\plugin.proto
   ```
   Then edit `app\plugins\proto\plugin_pb2_grpc.py`, changing
   `import plugin_pb2 as` to `from . import plugin_pb2 as`, and add an empty
   `app\plugins\proto\__init__.py`.
5. **Build the frontend:**
   ```powershell
   cd C:\PrivacyShield\frontend
   npm install
   npm run build
   ```
   (`frontend\dist\` is what IIS will serve.)
6. **Create `.env`:**
   ```powershell
   cd C:\PrivacyShield
   Copy-Item .env.example .env
   ```
   Edit it: set `SECRET_KEY` to a random value, add
   `SETTINGS_FILE=C:\PrivacyShield\data\privacyshield_settings.json` and
   `LOGO_PATH=C:\PrivacyShield\data\logo`, and create that `data` folder.
7. **Register the Windows Service with NSSM:**
   ```powershell
   nssm install PrivacyShieldAPI "C:\PrivacyShield\backend\venv\Scripts\uvicorn.exe" "app.main:app --host 127.0.0.1 --port 8000 --workers 2"
   nssm set PrivacyShieldAPI AppDirectory "C:\PrivacyShield"
   nssm set PrivacyShieldAPI AppEnvironmentExtra (Get-Content .env | Where-Object { $_ -match '=' })
   nssm start PrivacyShieldAPI
   ```
   Confirm it's up: `Invoke-WebRequest http://127.0.0.1:8000/api/health`
   should return `{"status":"ok"}`.
8. **Set up IIS:**
   - Install the **Application Request Routing (ARR)** and **URL Rewrite**
     modules (free, from Microsoft's IIS download page).
   - In IIS Manager, enable ARR's proxy feature (Server node → Application
     Request Routing Cache → Server Proxy Settings → **Enable proxy**).
   - Create a site with its physical path pointed at
     `C:\PrivacyShield\frontend\dist`.
   - Add a URL Rewrite rule: requests to `/api/*` reverse-proxy to
     `http://127.0.0.1:8000/{R:0}`; everything else falls through to
     `index.html` (a standard SPA rewrite rule — IIS's URL Rewrite has a
     built-in template for this).
   - In that rule's **Server Variables**, add/set `HTTP_X_FORWARDED_PROTO` to
     `https` once HTTPS is on (step 9) so PrivacyShield knows the original
     request scheme.
9. **Turn on HTTPS with win-acme:**
   - Download [win-acme](https://www.win-acme.com/) and run `wacs.exe`.
   - Point it at your IIS site; it obtains a Let's Encrypt certificate,
     installs it into the site's HTTPS binding, and registers a scheduled
     task for renewal — no further action needed.
   - Set `FRONTEND_URL=https://your-domain` in `.env`, update the NSSM
     service's environment (`nssm set PrivacyShieldAPI AppEnvironmentExtra ...`
     again, or `nssm edit PrivacyShieldAPI`), and restart it:
     `nssm restart PrivacyShieldAPI`.
10. Open `https://your-domain/` — the first user to register becomes the
    super admin.

### Updating

```powershell
cd C:\PrivacyShield
git pull
.\deploy\native\install-native.ps1 -Update    # or re-run steps 2-5 manually
nssm restart PrivacyShieldAPI
```

### Confirming HTTPS actually worked (either OS)

Once you're logged in as a super admin, the **dashboard** shows a live check
(with a **Check again** button) confirming whether the certificate is
actually valid — a real answer, not a guess from the browser's own address
bar. This is the same check used on the Docker/managed path; see
[docs/HTTPS.md](HTTPS.md#confirming-it-actually-worked) for why the app
can't just run these steps and show you the output itself (it deliberately
has no OS-level service control or live access to `.env`, on either
platform).

## See also

- [docs/HTTPS.md](HTTPS.md) — the Docker (managed), native, and external
  reverse-proxy paths compared side by side, plus troubleshooting.
- [docs/SSO.md](SSO.md) — LDAP/SIP2/OIDC/SAML setup; the reverse-proxy
  section there applies the same way to a native install.
- [docs/PLUGINS.md](PLUGINS.md) — the plugin sandboxing model.
