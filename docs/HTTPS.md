# HTTPS

OpenOptOut handles passwords, SSO tokens, and personal data — it should always be reached over HTTPS in production. Which path applies depends on how OpenOptOut itself is running here — **not** on how big the deployment is. Docker on bare metal and Docker on a VM are identical from OpenOptOut's side (Docker doesn't care which); a genuinely native install (no containers at all) is the real technical fork. The setup wizard's **deployment** step (or the scripts directly) asks which situation applies:

| Situation | Choose |
|---|---|
| Running via **Docker** (bare metal or a VM), nothing else already using ports 80/443 | **Managed** — OpenOptOut runs its own front door (Caddy, Traefik, or Cloudflare Tunnel) and keeps the certificate renewed |
| **Native install, no containers** (systemd on Linux, a Windows Service on Windows), nothing else already using ports 80/443 | **Native** — certbot (Linux) or win-acme (Windows) handles it directly on the host |
| Something else already terminates TLS in front of OpenOptOut — IIS, nginx, Traefik, a load balancer — whether OpenOptOut itself runs in Docker or natively | **External** — point that existing proxy at OpenOptOut; don't run either HTTPS script |
| Still deciding, or genuinely internal-only for now | **Neither** — plain HTTP, with a standing warning until you pick one |

Choosing wrong mostly just means extra noise (a nag you don't need, or missing one you do) — nothing is destructive, and both scripts have a matching `--disable`/`-Disable`. The one thing to get right is: **don't run the managed or native option if something else on this server already owns ports 80/443** — they'll fight each other for the ports.

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
| Compose profile / certificate volume | `https-caddy-extended` (or `https` for stock Caddy with rate limits off) / `caddy_data` | `https-traefik` / `traefik_data` |

OpenOptOut's Traefik container never gets the Docker socket and doesn't use Docker labels: its routing comes only from a config file generated at startup from `.env` (`deploy/traefik/entrypoint.sh`), the same way the Caddy container works. If you want an existing, shared Traefik that routes many services by Docker labels, that's **Option C (External)**, not this.

### Question 2 — Where should the certificate come from? (Caddy and Traefik only)

| Choice (`--cert`) | What it needs | What it's for |
|---|---|---|
| **Let's Encrypt** (`letsencrypt`) | A DNS record pointing at this server, and ports **80 and 443 reachable from the internet** | A server with a normal public connection |
| **Let's Encrypt via Cloudflare DNS** (`cloudflare-dns`) | Your domain's DNS hosted on Cloudflare (the free plan is fine) and a Cloudflare API token. **No open ports.** | Home connections, LAN-only installs, and anywhere ports 80/443 can't be reached from outside |
| **None for now** (`none`) | Nothing | Plain HTTP through the front door, so you can set up a certificate later. Testing only — not for real people's data |
| **Advanced** (`advanced`) | Depends — see [Advanced modes](#advanced-modes) | Let's Encrypt's test service, your own ACME CA, Caddy's private CA, or your own certificate files |

> **For many home users, Let's Encrypt via Cloudflare DNS is the only option that works.** Plenty of home internet providers block incoming ports 80 and 443, or put several homes behind one shared public IP address (often called CGNAT). Either way, Let's Encrypt can't reach your server to check it, and plain Let's Encrypt will never issue a certificate — no matter how the router is set up. Cloudflare DNS sidesteps this: instead of connecting to your server, Let's Encrypt checks a temporary DNS record that OpenOptOut creates through Cloudflare. Nothing has to reach your server from the internet, and **Cloudflare only ever sees that DNS record — never your traffic**. (People on your home network can then use `https://your.domain`; reaching it from outside your home is a separate question — see Option D.)

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

Pick **Advanced** in the menu, or pass `--mode` (with `--cert cloudflare-dns`, `letsencrypt-staging` and `acme` also work):

| `--mode` | Use for |
|---|---|
| `letsencrypt-staging` | Let's Encrypt's **test** environment — untrusted certificates, but no rate limits. Try this first, then switch to `letsencrypt` once it works. |
| `acme` | Your own ACME server (e.g. an internal `step-ca`). Needs `--acme-ca <directory URL>`, and `--acme-ca-root <file>` if it uses an internal CA browsers won't already trust. |
| `internal` | Caddy's own private CA. LAN-only — browsers warn until that CA's root is installed on client devices. Caddy only. |
| `custom` | Certificate files you already have. Put `fullchain.pem` and `privkey.pem` in `deploy/certs/` first. |

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

### Confirming it actually worked

The setup wizard and the two scripts can only tell you what they *tried* to do — the certificate itself is requested by the front-door container after you restart, outside of anything the wizard runs. Once you're logged back in, the **dashboard** shows a live check (and a **Check again** button) confirming whether the certificate actually came up, using the same read-only check the daily certificate monitor uses — so you get a real answer, not a guess from whether your own browser happens to say `https://` yet.

**Why doesn't the wizard just run the script and show the output itself?** Because it would need something the app is deliberately never given: access to the host's Docker daemon (to bring up the front-door container) and to the host's `.env` file (which isn't mounted into the `api` container — env vars are baked in at container creation by `docker compose`, not read from a live file afterward). Handing the running app that kind of host-level control would mean anything that ever compromises it — a bug, or a misbehaving plugin, given the plugin system — could reach the whole server, not just OpenOptOut's own data. That's a host-level step on purpose; the live status check above is the honest substitute.

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

If OpenOptOut becomes popular, a data broker could try to knock instances offline with floods of traffic. The design already helps: every family or organization runs its own copy, so there is no central server to take down — an attacker has to find and target each instance one by one. What's left to protect is each instance's own address. In order of strength:

| Protection | Stops | Cost |
|---|---|---|
| **Don't expose it publicly** | Everything from the internet — there's nothing to attack | Use it at home, or through a VPN when away |
| **Rate limits** (on by default, Caddy and Traefik) | One source hammering the site or guessing passwords | None for normal use |
| **Cloudflare's proxy** (opt-in, Caddy and Traefik) | Large floods from many sources; hides this server's address | Cloudflare can see all traffic |
| **Cloudflare Tunnel** ([Option D](#option-d--cloudflare-tunnel)) | Large floods; no open ports and no visible address at all | Cloudflare can see all traffic |

### 1. Recommended for most families: don't be public

A family instance rarely needs to be reachable from the whole internet. Run it on your home network with a **Let's Encrypt via Cloudflare DNS** certificate (real HTTPS, no open ports), and when you're away, reach home through a VPN (your router's built-in WireGuard/OpenVPN, or a service like Tailscale). With no ports open, there's nothing for anyone outside to flood. The opt-out requests OpenOptOut *sends* still go out normally.

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

- Cloudflare **Authenticated Origin Pulls** for the Cloudflare proxy mode, so only *your* Cloudflare zone can reach the server, not any Cloudflare customer's traffic.
- A ready-made set of Cloudflare rate-limiting / WAF rules to paste in for Cloudflare Tunnel users.

- DNS providers other than Cloudflare for DNS-01 certificates (Route 53, DigitalOcean, deSEC, …). Traefik already supports dozens through the same mechanism and Caddy has a module per provider, so each is mostly a menu entry plus a token. On the native path, certbot has its own DNS-01 plugins you can use directly (outside `enable-https-native.sh`, which is HTTP-01 via the nginx plugin only).
