# HTTPS

PrivacyShield handles passwords, SSO tokens, and personal data — it should
always be reached over HTTPS in production. Which path applies depends on how
PrivacyShield itself is running here — **not** on how big the deployment is.
Docker on bare metal and Docker on a VM are identical from PrivacyShield's
side (Docker doesn't care which); a genuinely native install (no containers
at all) is the real technical fork. The setup wizard's **deployment** step
(or the scripts directly) asks which situation applies:

| Situation | Choose |
|---|---|
| Running via **Docker** (bare metal or a VM), nothing else already using ports 80/443 | **Managed** — let PrivacyShield's own Caddy container get and renew certificates |
| **Native install, no containers** (systemd on Linux, a Windows Service on Windows), nothing else already using ports 80/443 | **Native** — certbot (Linux) or win-acme (Windows) handles it directly on the host |
| Something else already terminates TLS in front of PrivacyShield — IIS, nginx, Traefik, a load balancer — whether PrivacyShield itself runs in Docker or natively | **External** — point that existing proxy at PrivacyShield; don't run either HTTPS script |
| Still deciding, or genuinely internal-only for now | **Neither** — plain HTTP, with a standing warning until you pick one |

Choosing wrong mostly just means extra noise (a nag you don't need, or missing
one you do) — nothing is destructive, and both scripts have a matching
`--disable`/`-Disable`. The one thing to get right is: **don't run the
managed or native option if something else on this server already owns ports
80/443** — they'll fight each other for the ports.

## Option A — Managed (Docker + the built-in Caddy container)

Best for Docker with nothing else listening on 80/443 — bare metal or a VM,
it makes no difference. Caddy runs as an extra container, gets a certificate
automatically, renews it before it expires, and redirects plain HTTP to
HTTPS.

**Linux / macOS:**
```
./scripts/enable-https.sh
```

**Windows** (Docker Desktop, or Docker Engine on Windows Server — the
containers are still Linux containers either way, only the host-side helper
script differs):
```
.\scripts\enable-https.ps1
```
If double-clicking `.ps1` files is blocked by execution policy (the Windows
default), either double-click `scripts\enable-https.cmd` instead — it bypasses
the policy for that one script, not system-wide — or run from a prompt:
```
powershell -ExecutionPolicy Bypass -File .\scripts\enable-https.ps1
```

Both scripts take the same options and write the same `.env` keys (flag names
differ only in case/style — `--domain` vs `-Domain`):

Interactive prompts, or fully flagged for scripting:

```
./scripts/enable-https.sh --mode letsencrypt --domain privacy.yourlibrary.org --email it@yourlibrary.org --yes
.\scripts\enable-https.ps1 -Mode letsencrypt -Domain privacy.yourlibrary.org -Email it@yourlibrary.org -Yes
```

Modes:

| `--mode` | Use for |
|---|---|
| `letsencrypt` | A public server with DNS pointing at it and ports 80+443 reachable from the internet. |
| `letsencrypt-staging` | The same, but against Let's Encrypt's **test** environment — untrusted certificates, but no rate limits. Try this first, then switch to `letsencrypt` once it works. |
| `acme` | Your own ACME server (e.g. an internal `step-ca`). Needs `--acme-ca <directory URL>`, and `--acme-ca-root <file>` if it uses an internal CA browsers won't already trust. |
| `internal` | Caddy's own private CA. LAN-only — browsers warn until that CA's root is installed on client devices. |
| `custom` | Certificate files you already have. Put `fullchain.pem` and `privkey.pem` in `deploy/certs/` first. |

Requirements for `letsencrypt`:
- A DNS **A/AAAA record** for the domain pointing at this server (the script
  checks this and warns if it doesn't resolve yet).
- Ports **80 and 443** reachable from the internet (router/firewall
  port-forwarding if this is behind NAT; on Windows Server, also check Windows
  Defender Firewall allows inbound 80/443 to Docker's networking).
- Let's Encrypt has rate limits per domain per week — use `letsencrypt-staging`
  while testing to avoid hitting them.

What the script actually changes, all in `.env` (backed up first):

```
COMPOSE_PROFILES=https
HTTPS_MODE=letsencrypt
DOMAIN=privacy.yourlibrary.org
ACME_EMAIL=it@yourlibrary.org
WEB_BIND=127.0.0.1     # the web container stops being reachable directly
WEB_PORT=8080          # Caddy owns 80/443 instead
FRONTEND_URL=https://privacy.yourlibrary.org
```

Then:

```
docker compose up -d --build
docker compose logs -f caddy      # watch it obtain the certificate
```

Open `https://privacy.yourlibrary.org`. The first certificate can take up to a
minute. Caddy stores its certificates and ACME account in the `caddy_data`
Docker volume — **keep that volume** across restarts and upgrades; deleting it
means requesting a fresh certificate, and doing that too often risks rate
limits.

To turn it back off: `./scripts/enable-https.sh --disable` (or
`.\scripts\enable-https.ps1 -Disable` on Windows), then
`docker compose down && docker compose up -d`.

### Confirming it actually worked

The setup wizard and the two scripts can only tell you what they *tried* to
do — the certificate itself is requested by the `caddy` container after you
restart, outside of anything the wizard runs. Once you're logged back in, the
**dashboard** shows a live check (and a **Check again** button) confirming
whether the certificate actually came up, using the same read-only check the
daily certificate monitor uses — so you get a real answer, not a guess from
whether your own browser happens to say `https://` yet.

**Why doesn't the wizard just run the script and show the output itself?**
Because it would need something the app is deliberately never given: access
to the host's Docker daemon (to bring up the `caddy` container) and to the
host's `.env` file (which isn't mounted into the `api` container — env vars
are baked in at container creation by `docker compose`, not read from a live
file afterward). Handing the running app that kind of host-level control
would mean anything that ever compromises it — a bug, or a misbehaving plugin,
given the plugin system — could reach the whole server, not just PrivacyShield's
own data. That's a host-level step on purpose; the live status check above is
the honest substitute.

## Option B — Native (no containers — certbot / win-acme)

Best for a genuinely native install: no Docker at all, PrivacyShield running
as its own process (systemd on Linux, a Windows Service on Windows), with
nothing else already listening on ports 80/443. This is common at
institutions that can't or don't run container runtimes — see
[docs/NATIVE_INSTALL.md](NATIVE_INSTALL.md) for the full install walkthrough;
this section only covers turning on HTTPS once that's done.

**Linux** — nginx serves the frontend and proxies `/api/` to the systemd-run
process (see `deploy/native/nginx-privacyshield.conf.example`); certbot's
nginx plugin adds the TLS server block and HTTP→HTTPS redirect for you:

```
sudo apt-get install certbot python3-certbot-nginx   # if not already installed
sudo ./scripts/enable-https-native.sh --domain privacy.yourlibrary.org --email it@yourlibrary.org
```

Same shape as the Docker script: `--staging` first to test against Let's
Encrypt's staging environment (avoids rate limits), a DNS preflight check, an
`.env` backup, and `--disable` to revert. certbot installs its own systemd
timer for renewal (`systemctl list-timers | grep certbot`) — nothing else to
maintain. After it runs, restart the API service so it picks up the updated
`.env`: `sudo systemctl restart privacyshield-api`.

**Windows** — IIS serves the frontend and reverse-proxies to the Windows
Service running the API, and **win-acme** gets and renews the certificate
directly in IIS. This is closer to a one-time IIS Manager setup than a single
script (see [docs/NATIVE_INSTALL.md](NATIVE_INSTALL.md) for the full
walkthrough); the short version:

1. Install [win-acme](https://www.win-acme.com/) (a free, well-established
   tool for exactly this — obtains a Let's Encrypt certificate and installs
   it into IIS's certificate store and site binding, then registers a
   scheduled task for renewal).
2. Run `wacs.exe`, point it at your IIS site, and let it bind the certificate.
3. In IIS's URL Rewrite rule for the reverse-proxy, add/set the
   `HTTP_X_FORWARDED_PROTO` server variable to `https` (IIS/ARR doesn't
   always set this on its own).
4. Set `FRONTEND_URL=https://your-domain` in `.env` and restart the API
   Windows Service.

## Option C — External (a reverse proxy you already run)

Best for deployments where something else already terminates TLS in front of
PrivacyShield for other reasons — a load balancer, another team's nginx or
Traefik, or IIS handling several services on the same Windows Server — whether
PrivacyShield itself runs in Docker or natively. Don't run the managed or
native option here — either would try to bind ports 80 and 443 that your
existing proxy is already using.

1. In the setup wizard's deployment step (or Settings, if you skipped it),
   choose **"Something else already terminates HTTPS"**. This just records the
   choice so PrivacyShield stops suggesting the managed/native options and
   stops warning about plain HTTP once you're actually being reached over
   `https://` — it doesn't change how the app runs.
2. Point your existing proxy at PrivacyShield's web-serving port: the `web`
   container's port (`WEB_PORT` in `.env`, default `80`) on the Docker path,
   or nginx/IIS's own port on the native path — either way, that's already
   set up to serve the frontend and proxy `/api/` internally, so pointing your
   outer proxy at just that one port and letting it handle everything works
   for most setups.
3. Have your proxy forward `X-Forwarded-Proto` and `X-Forwarded-For` (most
   reverse proxies do this by default; for IIS/ARR you may need to add the
   `HTTP_X_FORWARDED_PROTO` server variable explicitly) so the app knows
   requests arrived over HTTPS.
4. Set `FRONTEND_URL` in `.env` to your public HTTPS address regardless of how
   TLS gets there — it's what SSO redirects (OIDC, SAML) are built from. See
   [docs/SSO.md](SSO.md#behind-a-reverse-proxy-or-https-terminator).
5. Leave `HTTPS_MODE`/`DOMAIN` unset (or don't run either enable-https
   script) — on the Docker path that leaves the `caddy` container off (it
   only starts with the `https` Compose profile), and either way the
   certificate monitor won't try to check a front door that isn't
   PrivacyShield's to check.

## Monitoring

If you're on the managed or native option, the daily certificate check also
watches PrivacyShield's own HTTPS certificate, the same way it watches LDAP,
SIP2, and SAML — see [docs/SSO.md](SSO.md#certificate-reminders). A failed
automatic renewal shows up as a dashboard warning before it actually expires.
On the Docker path this reaches the `caddy` container over the internal
Docker network; on the native path, set `HTTPS_CHECK_HOST=127.0.0.1` in
`.env` (`enable-https-native.sh` does this for you) so it checks the local
nginx/IIS instead. This check is skipped for `internal` mode (Caddy renews
its own private CA itself) and does nothing at all when HTTPS isn't
configured through PrivacyShield (the external option).

## Troubleshooting

- **Certificate never issued / times out:** Docker path —
  `docker compose logs -f caddy`; native path — `sudo journalctl -u certbot`
  or the output of `enable-https-native.sh` itself. Usually DNS not pointing
  here yet, or ports 80/443 not actually reachable from the internet (check
  port forwarding, not just a local firewall rule).
- **"too many certificates" / rate limited:** switch to
  `--mode letsencrypt-staging` (Docker) or `--staging` (native) while you
  finish testing, then switch back.
- **Browser shows "not secure" / self-signed warning:** expected for
  `internal` mode until that CA's root is installed on client devices; for
  `letsencrypt`/`acme`, check the logs above for the actual issuance error
  rather than assuming it's trusted.
- **SSO redirects go to the wrong address:** `FRONTEND_URL` doesn't match what
  people actually type into their browser (see the SSO doc's reverse-proxy
  section).
- **Reused an old `.env` and HTTPS didn't turn on (Docker path):** confirm
  `COMPOSE_PROFILES=https` is actually set — Compose only starts the `caddy`
  service when that profile is active.
- **Native path: nginx site not found:** `enable-https-native.sh` looks for
  `/etc/nginx/sites-available/privacyshield` or
  `/etc/nginx/conf.d/privacyshield.conf` — pass `--nginx-site PATH` if yours
  lives elsewhere, or install it first from
  `deploy/native/nginx-privacyshield.conf.example`.

## Follow-ups (not built yet)

- DNS-01 ACME challenges, for certificates on hosts that can't open ports
  80/443 to the internet at all. `HTTPS_MODE=acme` (Docker) already supports
  pointing at any ACME server that does this itself (an internal `step-ca`,
  for example); on the native path, certbot has its own DNS-01 plugins you
  can use directly (outside `enable-https-native.sh`, which is HTTP-01 via
  the nginx plugin only). A bundled DNS-01 provider for the Docker path is
  future work.
