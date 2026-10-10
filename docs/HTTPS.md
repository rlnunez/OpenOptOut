# HTTPS

OpenOptOut handles passwords, SSO tokens, and personal data — it should always be reached over HTTPS in production. Which path applies depends on how OpenOptOut itself is running here — **not** on how big the deployment is. Docker on bare metal and Docker on a VM are identical from OpenOptOut's side (Docker doesn't care which); a genuinely native install (no containers at all) is the real technical fork. The setup wizard's **deployment** step (or the scripts directly) asks which situation applies:

| Situation | Choose |
|---|---|
| Running via **Docker** (bare metal or a VM), nothing else already using ports 80/443 | **Managed** — OpenOptOut runs its own front door (Caddy, Traefik, or Cloudflare Tunnel) and keeps the certificate renewed |
| **Native install, no containers** (systemd on Linux, a Windows Service on Windows), nothing else already using ports 80/443 | **Native** — certbot (Linux) or win-acme (Windows) handles it directly on the host |
| Something else already terminates TLS in front of OpenOptOut — IIS, nginx, Traefik, a load balancer — whether OpenOptOut itself runs in Docker or natively | **External** — point that existing proxy at OpenOptOut; don't run either HTTPS script |
| Still deciding, or genuinely internal-only for now | **Neither** — plain HTTP, with a standing warning until you pick one |

Changing configurations later is non-destructive via `--disable` / `-Disable`. Note: **do not run the managed or native option if another service already binds ports 80/443**.

## Option A — Managed (Docker + OpenOptOut's own front door)

Best for Docker with nothing else listening on 80/443 — bare metal or a VM, it makes no difference. A front door runs as an extra container, gets a certificate automatically, renews it before it expires, and redirects plain HTTP to HTTPS.

The script (and the setup wizard) asks two questions.

### Question 1 — How should people reach OpenOptOut?

| Choice | Pick it when | |
|---|---|---|
| **Caddy** (default) | You have no preference. Simplest. | Option A |
| **Traefik** | Your team already runs and monitors Traefik elsewhere and wants one tool to know. | Option A |
| **Cloudflare Tunnel** | You can't or won't open any ports, and you accept that **Cloudflare can see all traffic**. | [Option D](#option-d--cloudflare-tunnel) |

Caddy and Traefik give the same security headers, HTTP→HTTPS redirect, HTTP/3, and certificate monitoring. Differences:

| | Caddy (default) | Traefik |
|---|---|---|
| Let's Encrypt, Let's Encrypt via Cloudflare DNS, none, and the advanced `letsencrypt-staging` / `acme` / `custom` modes | ✅ | ✅ |
| `internal` (private CA for LAN-only use) | ✅ | ❌ — use `custom` with your own certificate instead |
| Wildcard names in `DOMAIN` | ✅ (with a CA that allows it) | ❌ — list each name |
| Rate limits and Cloudflare DNS | An "extended" Caddy with both modules, built locally the first time it starts — about a minute (`caddy-extended` service, `deploy/caddy/Dockerfile`) | Built in, no extra build |
| InCommon certificates (beta), and account credentials / key types for other ACME CAs | Built in | Built in |
| Compose profile / certificate volume | `https-caddy-extended` (or `https` for stock Caddy with rate limits off) / `caddy_data` | `https-traefik` / `traefik_data` |

**Module Comparison:** Traefik includes rate limiting, Cloudflare DNS, and InCommon credentials natively without additional builds. Caddy handles core certificates natively and adds Cloudflare DNS and rate limiting via modules in an extended build (`caddy-extended`, built locally on first start). Both provide equivalent security posture.

The Traefik container does not mount the Docker socket or read Docker labels; configuration is generated strictly from `.env` via `deploy/traefik/entrypoint.sh`. For existing Traefik installations routing by Docker labels, use **Option C (External)**.

### Question 2 — Where should the certificate come from? (Caddy and Traefik only)

| Choice (`--cert`) | What it needs | What it's for |
|---|---|---|
| **Let's Encrypt** (`letsencrypt`) | A DNS record pointing at this server, and ports **80 and 443 reachable from the internet** | A server with a normal public connection |
| **Let's Encrypt via Cloudflare DNS** (`cloudflare-dns`) | Your domain's DNS hosted on Cloudflare (the free plan is fine) and a Cloudflare API token. **No open ports.** | Home connections, LAN-only installs, and anywhere ports 80/443 can't be reached from outside |
| **None for now** (`none`) | Nothing | Plain HTTP through the front door, so you can set up a certificate later. Testing only — not for real people's data |
| **Advanced** (`advanced`) | Depends — see [Advanced modes](#advanced-modes) | Let's Encrypt's test service, your own ACME CA, Caddy's private CA, or your own certificate files |

> [!TIP]
> If your ISP blocks inbound ports 80/443 or uses CGNAT (shared public IP), standard HTTP validation will fail. **Let's Encrypt via Cloudflare DNS** solves this by validating via temporary DNS TXT records without open inbound ports. Cloudflare only sees the DNS record, never your application traffic.

#### Setting up Cloudflare DNS

You can choose this now and finish the Cloudflare part later — the script saves everything else and tells you what's left.

1. Put your domain's DNS on Cloudflare (Cloudflare dashboard → **Add a domain**, then change the nameservers at your registrar).
2. Add a DNS record for the name you'll use (e.g. `privacy.example.org`) pointing at this server's address. A private LAN address like `192.168.1.20` is fine for home-only use. Leave it **DNS only** (grey cloud) — orange-cloud proxying would send your traffic through Cloudflare, which this option is meant to avoid.
3. Create an API token: **My Profile → API Tokens → Create Token → "Edit zone DNS"** template, limited to just this domain's zone.
4. Give it to the script when asked (typing is hidden), or add it to `.env` yourself later:
   ```
   CLOUDFLARE_API_TOKEN=your-token-here
   ```
5. `docker compose up -d --build`. The first certificate can take a few minutes while the DNS record spreads.

The token can only edit DNS for that one zone. It lives in `.env` (keep that file private — it already holds `SECRET_KEY`) and is only passed to the front-door container; it's never written into a config file. `--disable` removes it.

### Running it

**Linux / macOS:**
```
./scripts/enable-https.sh
```

**Windows** (Docker Desktop, or Docker Engine on Windows Server — the containers are still Linux containers either way, only the host-side helper script differs):
```
.\scripts\enable-https.ps1
```
If double-clicking `.ps1` files is blocked by execution policy (the Windows default), either double-click `scripts\enable-https.cmd` instead — it bypasses the policy for that one script, not system-wide — or run from a prompt:
```
powershell -ExecutionPolicy Bypass -File .\scripts\enable-https.ps1
```

If you went through the setup wizard, its summary shows the exact command for your choices, with a copy button.

Both scripts take the same options and write the same `.env` keys (flag names differ only in case/style — `--domain` vs `-Domain`). Interactive prompts, or fully flagged for scripting:

```
# Caddy + Let's Encrypt
./scripts/enable-https.sh --proxy caddy --cert letsencrypt --domain privacy.yourlibrary.org --email it@yourlibrary.org --yes
.\scripts\enable-https.ps1 -Proxy caddy -Cert letsencrypt -Domain privacy.yourlibrary.org -Email it@yourlibrary.org -Yes

# Traefik + Let's Encrypt via Cloudflare DNS (token now, or add it to .env later)
./scripts/enable-https.sh --proxy traefik --cert cloudflare-dns --domain home.example.org --cf-token "$TOKEN" --yes
.\scripts\enable-https.ps1 -Proxy traefik -Cert cloudflare-dns -Domain home.example.org -CfToken $Token -Yes

# Caddy, no certificate yet
./scripts/enable-https.sh --proxy caddy --cert none --yes

# Public instance behind Cloudflare's proxy for DDoS protection (Cloudflare sees all traffic)
./scripts/enable-https.sh --proxy traefik --cert cloudflare-dns --cloudflare-proxy --domain privacy.example.org --yes
```

After the certificate question, the script asks one more thing only when it applies: whether to put the site behind Cloudflare's proxy (offered with the Cloudflare DNS certificate). Rate limits are on without asking; see [Protecting against floods](#protecting-against-floods-ddos).

Older commands using only `--mode` (e.g. `--mode letsencrypt`) still work.

#### Advanced modes

Pick **Advanced** in the menu, or pass `--mode` (with `--cert cloudflare-dns`, `letsencrypt-staging`, `acme` and `incommon` also work):

| `--mode` | Use for |
|---|---|
| `letsencrypt-staging` | Let's Encrypt's **test** environment — untrusted certificates, but no rate limits. Try this first, then switch to `letsencrypt` once it works. |
| `acme` | Your own ACME server (e.g. an internal `step-ca`) or a commercial CA. Needs `--acme-ca <directory URL>`, and `--acme-ca-root <file>` if it uses an internal CA browsers won't already trust. If the CA gave you account credentials (External Account Binding), add `--eab-kid` and `--eab-hmac` (the script also asks); if it requires a key type, add `--key-type rsa2048` (or `rsa4096`, `p256`, `p384`). |
| `incommon` | **Beta, untested.** InCommon certificates for universities — see [InCommon](#incommon-certificates-beta) below. |
| `internal` | Caddy's own private CA. LAN-only — browsers warn until that CA's root is installed on client devices. Caddy only. |
| `custom` | Certificate files you already have. Put `fullchain.pem` and `privkey.pem` in `deploy/certs/` first. |

#### InCommon certificates (beta)

> **Beta — untested against a live account.** OpenOptOut's InCommon support has been tested end to end against a test certificate authority configured the same way (`deploy/tests/incommon_e2e.sh`), but not yet against a real CERTInext account. If you try it at your institution, please report how it goes.

Universities and research institutions that belong to InCommon get free, publicly trusted certificates through the InCommon Certificate Service. OpenOptOut supports CERTInext, the provider InCommon institutions use, over ACME — so certificates are issued and renewed automatically, just like Let's Encrypt. This is mostly useful for universities; if your organization isn't an InCommon member, use Let's Encrypt instead.

**This information is required during setup** — the script asks for all three and won't continue without them, so get them from your campus IT (the team that runs your InCommon certificate service) first:

| What | Looks like | Notes |
|---|---|---|
| **ACME server address** (directory URL) | `https://acme-us.certinext.io/v1/directory` | Pre-filled with this common address. Some institutions get a per-account address instead — use whatever campus IT gives you. |
| **ACME key ID** (EAB key ID) | A short identifier | Ties OpenOptOut to your department's InCommon account. |
| **ACME HMAC key** (EAB HMAC key) | A long string of letters, digits, `-` and `_` | A secret. CERTInext shows it only once when campus IT creates it, so if it's lost they'll need to issue a new pair. Typing is hidden when you enter it. |

Your domain must also be one your campus IT has authorized for that account. Many institutions validate their domains with CERTInext once a year, in which case certificates are issued without any per-certificate check and you don't need ports 80/443 open for this. Otherwise the usual check applies: port 80 reachable from the internet, or — if your domain's DNS is on Cloudflare — the DNS check with `--cert cloudflare-dns --mode incommon`.

Run it:
```
./scripts/enable-https.sh --proxy traefik --mode incommon --domain privacy.university.edu
.\scripts\enable-https.ps1 -Proxy traefik -Mode incommon -Domain privacy.university.edu
```
(In the setup wizard: pick Caddy or Traefik, open **Advanced** under the certificate question, and choose **InCommon (CERTInext)**. The wizard then gives you the command above; it never stores the secret itself.) Or fully flagged, for automation: add `--acme-ca URL --eab-kid ID --eab-hmac KEY` (`-AcmeCa`, `-EabKid`, `-EabHmac` on Windows).

What OpenOptOut does with them:
- Uses RSA 2048-bit certificate keys automatically, which CERTInext requires (Caddy would otherwise default to a different key type).
- Keeps the HMAC key out of files on disk: it's stored in `.env` like your other secrets, Caddy reads it only when starting and is told not to save its loaded configuration, and Traefik's generated configuration lives in memory only.
- The dashboard's certificate check fully verifies InCommon certificates (they're publicly trusted), so a failed renewal shows up as a warning before the certificate expires.

Both front doors support InCommon with nothing extra to install (see the table in Question 1).

Requirements for plain `letsencrypt` (HTTP check):
- A DNS **A/AAAA record** for the domain pointing at this server (the script checks this and warns if it doesn't resolve yet).
- Ports **80 and 443** reachable from the internet (router/firewall port-forwarding if this is behind NAT; on Windows Server, also check Windows Defender Firewall allows inbound 80/443 to Docker's networking). If your provider blocks them or shares your IP, use Cloudflare DNS instead.
- Let's Encrypt has rate limits per domain per week — use `letsencrypt-staging` while testing to avoid hitting them.

What the script actually changes, all in `.env` (backed up first):

```
COMPOSE_PROFILES=https-caddy-extended   # https (stock Caddy, rate limits off) | https-traefik
FRONT_DOOR=caddy               # or traefik
HTTPS_CHECK_HOST=caddy         # or traefik — which container the certificate monitor checks
HTTPS_MODE=letsencrypt         # or none, or an advanced mode
ACME_CHALLENGE=http            # cloudflare for Let's Encrypt via Cloudflare DNS
CLOUDFLARE_API_TOKEN=...       # only with Cloudflare DNS, if you gave it to the script
ACME_EAB_KID=... / ACME_EAB_HMAC=...   # only with InCommon (or an ACME CA that issued account credentials)
ACME_KEY_TYPE=rsa2048          # set automatically for InCommon
RATE_LIMIT=on                  # off with --no-rate-limit (see "Protecting against floods")
CLOUDFLARE_PROXY=off           # on with --cloudflare-proxy
DOMAIN=privacy.yourlibrary.org
ACME_EMAIL=it@yourlibrary.org
WEB_BIND=127.0.0.1     # the web container stops being reachable directly
WEB_PORT=8080          # the front door owns 80/443 instead
TRUSTED_PROXY_HOPS=2   # front door + nginx in front: sign-in limits find the client IP (3 behind Cloudflare's proxy)
FRONTEND_URL=https://privacy.yourlibrary.org
```

Then:

```
docker compose up -d --build
docker compose logs -f caddy-extended   # watch it obtain the certificate (the script prints the right name: caddy, caddy-extended, or traefik)
```

Open `https://privacy.yourlibrary.org`. The first certificate can take up to a minute (a few minutes with Cloudflare DNS). Caddy stores its certificates and ACME account in the `caddy_data` Docker volume (Traefik: `traefik_data`) — **keep that volume** across restarts and upgrades; deleting it means requesting a fresh certificate, and doing that too often risks rate limits.

Switching later is safe: rerun the script with different answers, then `docker compose down && docker compose up -d --build`. A different front door requests its own certificate (the old one stays in the other volume), so on `letsencrypt` avoid switching back and forth repeatedly.

To turn it back off: `./scripts/enable-https.sh --disable` (or `.\scripts\enable-https.ps1 -Disable` on Windows), then `docker compose down && docker compose up -d`.

Once restarted, the **Settings > HTTPS** and **Dashboard** screens run a live read-only verification check against the front door (with a **Check again** trigger) to confirm certificate health.

> [!NOTE]
> The setup wizard does not execute host scripts or reload Docker directly: the application container is intentionally sandboxed without access to the host's Docker socket or host environment files.

## Option B — Native (no containers — certbot / win-acme)

Best for a genuinely native install: no Docker at all, OpenOptOut running as its own process (systemd on Linux, a Windows Service on Windows), with nothing else already listening on ports 80/443. This is common at institutions that can't or don't run container runtimes — see [docs/NATIVE_INSTALL.md](NATIVE_INSTALL.md) for the full install walkthrough; this section only covers turning on HTTPS once that's done.

**Linux** — nginx serves the frontend and proxies `/api/` to the systemd-run process (see `deploy/native/nginx-openoptout.conf.example`); certbot's nginx plugin adds the TLS server block and HTTP→HTTPS redirect for you:

```
sudo apt-get install certbot python3-certbot-nginx   # if not already installed
sudo ./scripts/enable-https-native.sh --domain privacy.yourlibrary.org --email it@yourlibrary.org
```

Same shape as the Docker script: `--staging` first to test against Let's Encrypt's staging environment (avoids rate limits), a DNS preflight check, an `.env` backup, and `--disable` to revert. certbot installs its own systemd timer for renewal (`systemctl list-timers | grep certbot`) — nothing else to maintain. After it runs, restart the API service so it picks up the updated `.env`: `sudo systemctl restart openoptout-api`.

**Windows** — IIS serves the frontend and reverse-proxies to the Windows Service running the API, and **win-acme** gets and renews the certificate directly in IIS. This is closer to a one-time IIS Manager setup than a single script (see [docs/NATIVE_INSTALL.md](NATIVE_INSTALL.md) for the full walkthrough); the short version:

1. Install [win-acme](https://www.win-acme.com/) (a free, well-established tool for exactly this — obtains a Let's Encrypt certificate and installs it into IIS's certificate store and site binding, then registers a scheduled task for renewal).
2. Run `wacs.exe`, point it at your IIS site, and let it bind the certificate.
3. In IIS's URL Rewrite rule for the reverse-proxy, add/set the `HTTP_X_FORWARDED_PROTO` server variable to `https` (IIS/ARR doesn't always set this on its own).
4. Set `FRONTEND_URL=https://your-domain` in `.env` and restart the API Windows Service.

## Option C — External (a reverse proxy you already run)

Best for deployments where something else already terminates TLS in front of OpenOptOut for other reasons — a load balancer, another team's nginx or Traefik, or IIS handling several services on the same Windows Server — whether OpenOptOut itself runs in Docker or natively. Don't run the managed or native option here — either would try to bind ports 80 and 443 that your existing proxy is already using.

1. In the setup wizard's deployment step (or Settings, if you skipped it), choose **"Something else already terminates HTTPS"**. This just records the choice so OpenOptOut stops suggesting the managed/native options and stops warning about plain HTTP once you're actually being reached over `https://` — it doesn't change how the app runs.
2. Point your existing proxy at OpenOptOut's web-serving port: the `web` container's port (`WEB_PORT` in `.env`, default `80`) on the Docker path, or nginx/IIS's own port on the native path — either way, that's already set up to serve the frontend and proxy `/api/` internally, so pointing your outer proxy at just that one port and letting it handle everything works for most setups.
3. Have your proxy forward `X-Forwarded-Proto` and `X-Forwarded-For` (most reverse proxies do this by default; for IIS/ARR you may need to add the `HTTP_X_FORWARDED_PROTO` server variable explicitly) so the app knows requests arrived over HTTPS.
4. Set `FRONTEND_URL` in `.env` to your public HTTPS address regardless of how TLS gets there — it's what SSO redirects (OIDC, SAML) are built from. See [docs/SSO.md](SSO.md#behind-a-reverse-proxy-or-https-terminator).
5. Leave `HTTPS_MODE`/`DOMAIN` unset (or don't run either enable-https script) — on the Docker path that leaves every front-door container off (each only starts with its own Compose profile), and either way the certificate monitor won't try to check a front door that isn't OpenOptOut's to check.

## Option D — Cloudflare Tunnel

> ⚠ **Cloudflare decrypts all traffic to this site.** With a tunnel, HTTPS ends at Cloudflare's servers, not yours. Cloudflare can see everything people send and receive through OpenOptOut: names, home addresses, phone numbers, email addresses, and sign-in tokens. OpenOptOut exists to keep that data out of other companies' hands, so think about whether that's acceptable for the people whose data you're protecting. If all you need is a certificate without opening ports, **Let's Encrypt via Cloudflare DNS** (Option A) doesn't have this problem.

What you get in exchange: OpenOptOut reachable at `https://your.domain` from anywhere, with **no open ports, no public IP, and no router setup**. A small `cloudflared` container dials out to Cloudflare, and Cloudflare serves HTTPS and passes requests back through that connection. It works behind shared-IP (CGNAT) connections and providers that block ports 80/443, Cloudflare handles the certificate, and the site sits behind Cloudflare's DDoS protection.

1. Your domain's DNS must be on Cloudflare (as in Option A's Cloudflare DNS steps).
2. Cloudflare dashboard → **Zero Trust → Networks → Tunnels → Create a tunnel** → **Cloudflared**. Name it, and copy the token from the install command it shows (the long value after `--token`). You don't need to install anything it suggests — OpenOptOut's container does that part.
3. On the tunnel, add a **public hostname**: your name (e.g. `privacy.example.org`) → Service type **HTTP**, URL **`web:80`**.
4. Run the script and choose **Cloudflare Tunnel** (you'll be shown the warning above and asked to type `yes`):
   ```
   ./scripts/enable-https.sh --proxy cloudflare-tunnel --domain privacy.example.org
   .\scripts\enable-https.ps1 -Proxy cloudflare-tunnel -Domain privacy.example.org
   ```
   Paste the token when asked (typing is hidden), or leave it blank and add `CLOUDFLARE_TUNNEL_TOKEN=...` to `.env` later.
5. `docker compose up -d`, then `docker compose logs -f cloudflared` until it says the connection is registered.

There's no certificate question — Cloudflare issues and renews it, so the dashboard's certificate check says so instead of checking. The script sets `COMPOSE_PROFILES=cloudflare-tunnel`, `FRONT_DOOR=cloudflare-tunnel`, `HTTPS_MODE=cloudflare-tunnel`, `TRUSTED_PROXY_HOPS=2` (cloudflared + nginx), and keeps the web container on `127.0.0.1` so nothing listens publicly.

## Protecting against floods (DDoS)

To protect self-hosted instances against traffic floods, brute-force attempts, and resource exhaustion, OpenOptOut supports tiered defenses:

| Protection | Stops | Cost |
|---|---|---|
| **Don't expose publicly** | Inbound internet attacks | Use on home LAN, or connect via VPN |
| **Rate limits** (default on Caddy & Traefik) | Rapid hammering & password guessing | None for normal use |
| **Cloudflare Proxy** (opt-in) | Distributed volumetric floods; conceals server IP | Cloudflare decrypts edge traffic |
| **Cloudflare Tunnel** ([Option D](#option-d--cloudflare-tunnel)) | Large floods; zero open ports | Cloudflare decrypts edge traffic |

### 1. Private Hosting (Recommended for Home / Family)

For household deployments, avoid opening ports 80/443 to the internet. Deploy using **Let's Encrypt via Cloudflare DNS** for automated valid certificates, and connect remotely through a VPN (such as WireGuard or Tailscale). Outbound broker removal requests operate normally without requiring inbound public access.

### 2. Rate limits (both front doors, on by default)

Caddy and Traefik both limit how fast any one visitor can send requests, before anything reaches OpenOptOut:

| Setting | Default | What it covers |
|---|---|---|
| `RATE_LIMIT_PER_MINUTE` | 1200 | Every request to the site, per visitor |
| `AUTH_RATE_LIMIT_PER_MINUTE` | 60 | Sign-in endpoints (`/api/auth/…`), per visitor — signing in is deliberately slow work for the server, so floods there are the cheapest way to overload it |

Over the limit, visitors get **429 Too Many Requests** until the minute rolls over. These sit in front of OpenOptOut's own sign-in lockouts, which still apply. Slow-header connections are also cut off (after 10 seconds in Caddy).

- Change them: `./scripts/enable-https.sh … --rate-limit 2400 --auth-rate-limit 120` (Windows: `-RateLimit`, `-AuthRateLimit`), or edit `.env` and `docker compose up -d`.
- **Many people behind one IP** (a library, school, or office network) count as one visitor. Raise the limits if they hit 429s.
- Turn off: `--no-rate-limit` (`-NoRateLimit`). The wizard has the same checkbox.
- Caddy needs its extended build for this (built automatically the first time; see the table in Question 1). Traefik has it built in. The two count slightly differently — Caddy allows up to the limit within any one-minute window; Traefik allows a steady rate with a short burst (about ten seconds' worth, so pages still load all their files at once) — but both land on about the same number per minute.
- Cloudflare Tunnel doesn't go through Caddy or Traefik. Use Cloudflare's own rate-limiting rules in its dashboard there; OpenOptOut's sign-in lockouts still apply.

### 3. Behind Cloudflare's proxy

> ⚠ **Cloudflare decrypts all traffic to this site.** Like the tunnel, HTTPS ends at Cloudflare's servers, so Cloudflare can see everything people send and receive through OpenOptOut: names, home addresses, phone numbers, email addresses, and sign-in tokens. Use this only for instances that are public and big enough to be a target.

Cloudflare's network sits in front of your server: it absorbs large floods, filters known attack traffic, and keeps your server's real address out of DNS. OpenOptOut's front door then **accepts connections only from Cloudflare's published IP ranges** and drops everything else — so an attacker who finds the real address can't get past the front door directly. It also takes each visitor's real address from Cloudflare (`CF-Connecting-IP`), trusting that header *only* because nobody else can connect, so rate limits and sign-in lockouts still apply per visitor.

Requirements: the **Let's Encrypt via Cloudflare DNS** certificate (or `--mode custom` with a [Cloudflare Origin certificate](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/)), and ports 80/443 reachable from the internet (they'll only let Cloudflare in). If your internet provider blocks those ports, use Cloudflare Tunnel instead.

1. Run the script, choose Caddy or Traefik and **Let's Encrypt via Cloudflare DNS**, then answer `yes` to the Cloudflare proxy question — or `--cloudflare-proxy` / `-CloudflareProxy`, or the wizard's checkbox.
2. Cloudflare dashboard → **DNS**: point the record at this server's public IP and set it to **Proxied** (orange cloud).
3. **SSL/TLS → Overview**: set encryption mode to **Full (strict)**. ("Flexible" would send traffic between Cloudflare and your server unencrypted.)
4. Forward ports 80 and 443 to this server, then `docker compose up -d --build`.

The script sets `CLOUDFLARE_PROXY=on` and `TRUSTED_PROXY_HOPS=3` (Cloudflare + front door + nginx).

**Keep Cloudflare's IP list current.** The allowed ranges ship in `deploy/cloudflare/ip-ranges.txt`. Cloudflare rarely changes them, but if it adds one, visitors routed through it would be refused. Refresh now and then (it validates the download and never writes an empty list):
```
./scripts/update-cloudflare-ips.sh
docker compose up -d --force-recreate caddy-extended    # or traefik
```

**What this doesn't cover:** any Cloudflare customer's traffic also comes from Cloudflare's addresses, so the IP check alone can't tell *your* Cloudflare traffic from someone else's. Cloudflare's [Authenticated Origin Pulls](https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/) closes that gap and is a planned follow-up. And if an attacker already knows your real IP from before, they can still try to saturate your internet connection itself — the front door drops their connections, but the bandwidth is used. Changing your public IP after moving behind Cloudflare fixes that.

## Monitoring

If you're on the managed or native option, the daily certificate check also watches OpenOptOut's own HTTPS certificate, the same way it watches LDAP, SIP2, and SAML — see [docs/SSO.md](SSO.md#certificate-reminders). A failed automatic renewal shows up as a dashboard warning before it actually expires. On the Docker path this reaches the front-door container (`caddy` or `traefik`) over the internal Docker network; on the native path, set `HTTPS_CHECK_HOST=127.0.0.1` in `.env` (`enable-https-native.sh` does this for you) so it checks the local nginx/IIS instead. This check is skipped for `internal` mode (Caddy renews its own private CA itself) and Cloudflare Tunnel (Cloudflare holds the certificate), shows "no certificate yet" for `none`, and does nothing at all when HTTPS isn't configured through OpenOptOut (the external option).

## Troubleshooting

- **Certificate never issued / times out:** Docker path — `docker compose logs -f caddy-extended` (or `caddy` / `traefik`); native path — `sudo journalctl -u certbot` or the output of `enable-https-native.sh` itself. Usually DNS not pointing here yet, or ports 80/443 not actually reachable from the internet (check port forwarding, not just a local firewall rule).
- **Cloudflare DNS certificate never issued:** `docker compose logs caddy-extended` (or `traefik`). Check that `CLOUDFLARE_API_TOKEN` is set in `.env`, that the token has **Zone → DNS → Edit** for *this* domain's zone, and that the domain's nameservers really are Cloudflare's. The container refuses to start without a token and says so in plain words. After adding the token, `docker compose up -d --build`.
- **"This Caddy build has no Cloudflare DNS support" / "no rate limiting":** `.env` asks for a feature the stock `caddy` service doesn't have. Rerun `enable-https.sh` (it sets `COMPOSE_PROFILES=https-caddy-extended`), then `docker compose down && docker compose up -d --build`.
- **Caddy logs "rate limiting is OFF":** an older `.env` is still on the stock `caddy` service. It keeps working without limits; rerun `enable-https.sh` to switch to the extended build with limits on.
- **InCommon (beta) certificate never arrives:** `docker compose logs caddy-extended` (or `traefik`). An "account" or "unauthorized" error usually means the key ID or HMAC key is wrong or was revoked; an error naming your domain usually means it isn't authorized for that account yet. Confirm all three values and the domain with campus IT, then rerun the script — it asks for them again.
- **People get "429 Too Many Requests":** the rate limits are doing their job, or are too tight for your setup — common when many people share one public IP (a library, office, or school network). Raise them with `--rate-limit` / `--auth-rate-limit` (see [Protecting against floods](#protecting-against-floods-ddos)).
- **Behind Cloudflare's proxy, the site won't load at all:** check the DNS record is **Proxied** (orange cloud) and SSL/TLS mode is **Full (strict)**. Connections that don't come from Cloudflare are dropped on purpose — including you visiting the server's IP directly. If Cloudflare added new IP ranges, run `./scripts/update-cloudflare-ips.sh` and restart the front door.
- **Plain Let's Encrypt times out at home even with ports forwarded:** your internet provider may block incoming 80/443 or share your public IP between homes (CGNAT — your router's WAN address won't match what websites report as your IP). Port forwarding can't fix either; switch to `--cert cloudflare-dns`.
- **Cloudflare Tunnel shows "Bad gateway" or won't connect:** the tunnel's public hostname must point to `HTTP` → `web:80` (not `localhost`), and `CLOUDFLARE_TUNNEL_TOKEN` must be the tunnel's token. `docker compose logs cloudflared` shows which.
- **"too many certificates" / rate limited:** switch to `--mode letsencrypt-staging` (Docker) or `--staging` (native) while you finish testing, then switch back.
- **Browser shows "not secure" / self-signed warning:** expected for `internal` mode until that CA's root is installed on client devices; for `letsencrypt`/`acme`, check the logs above for the actual issuance error rather than assuming it's trusted.
- **SSO redirects go to the wrong address:** `FRONTEND_URL` doesn't match what people actually type into their browser (see the SSO doc's reverse-proxy section).
- **Reused an old `.env` and HTTPS didn't turn on (Docker path):** confirm `COMPOSE_PROFILES` is actually set (`https`, `https-caddy-extended`, `https-traefik`, or `cloudflare-tunnel`) — Compose only starts the front-door service when its profile is active.
- **Traefik container exits right away:** `docker compose logs traefik` — it refuses `HTTPS_MODE=internal` and wildcard domains with a plain-English message saying what to use instead.
- **Dashboard HTTPS check can't connect after switching proxies:** `HTTPS_CHECK_HOST` must name the running front door (`caddy` or `traefik`); rerunning `enable-https` sets it.
- **Native path: nginx site not found:** `enable-https-native.sh` looks for `/etc/nginx/sites-available/openoptout` or `/etc/nginx/conf.d/openoptout.conf` (or legacy `privacyshield`) — pass `--nginx-site PATH` if yours lives elsewhere, or install it first from `deploy/native/nginx-openoptout.conf.example`.

## Follow-ups (not built yet)

- Cloudflare **Authenticated Origin Pulls** for the Cloudflare proxy mode, ensuring only your Cloudflare zone reaches the server.
- Preconfigured Cloudflare rate-limiting / WAF rulesets for Cloudflare Tunnel deployments.
- Extended DNS-01 ACME provider support (AWS Route 53, DigitalOcean, deSEC, etc.).

