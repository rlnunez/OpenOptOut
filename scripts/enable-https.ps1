<#
==============================================================================
Set up OpenOptOut's front door: how people reach it, and how it gets HTTPS. Windows PowerShell / PowerShell 7 port of enable-https.sh — same questions, same flags (PowerShell-style names), same .env keys, same docker compose commands afterward. Works whether Docker Desktop or Docker Engine is running on this Windows Server (the containers are still Linux containers either way).

  .\scripts\enable-https.ps1                       # interactive: asks two questions
  .\scripts\enable-https.ps1 -Proxy caddy -Cert letsencrypt -Domain privacy.lib.org -Email it@lib.org
  .\scripts\enable-https.ps1 -Proxy traefik -Cert cloudflare-dns -Domain home.example.org
  .\scripts\enable-https.ps1 -Proxy cloudflare-tunnel -Domain home.example.org
  .\scripts\enable-https.ps1 -Disable              # back to plain HTTP, no front door

Step 1, -Proxy:  caddy (default) | traefik | cloudflare-tunnel
Step 2, -Cert (Caddy/Traefik only):
         letsencrypt      Let's Encrypt; ports 80+443 must be reachable from the internet
         cloudflare-dns   Let's Encrypt via Cloudflare DNS; no open ports needed. For many home internet plans this is the only option that works. Token: -CfToken, or add it to .env later.
         none             No certificate yet; plain HTTP through the proxy
         advanced         Choose a -Mode below
Step 3 (only with cloudflare-dns or custom), -CloudflareProxy:
         Put the site behind Cloudflare's proxy for DDoS protection. The server then accepts connections ONLY from Cloudflare. Cloudflare decrypts and can see all traffic.
Rate limits (Caddy/Traefik; on by default):
         -NoRateLimit   -RateLimit N (per visitor per minute, default 1200)
         -AuthRateLimit N (sign-in attempts per visitor per minute, default 60)
Advanced: -Mode letsencrypt|letsencrypt-staging|acme|incommon|internal|custom|none
         -AcmeCa URL  -AcmeCaRoot FILE
         -Mode incommon (BETA, untested): InCommon certificates via CERTInext, mostly for universities. Requires -EabKid, -EabHmac and -AcmeCa (default https://acme-us.certinext.io/v1/directory) from campus IT; asked for during setup if not given.
         -EabKid K -EabHmac H   account credentials (External Account Binding) for -Mode acme with CAs that issue them
         -KeyType rsa2048|rsa4096|p256|p384   for CAs that require a key type (incommon always uses rsa2048)
Other:   -Domain D  -Email E  -CfToken T  -TunnelToken T
         -EnvFile PATH (default .env)  -Yes (no prompts; use defaults)

Writes settings to .env (a timestamped backup is made first), then tells you the one command to run.

If double-clicking is blocked by execution policy, either run scripts\enable-https.cmd instead (it bypasses policy for this script only), or run from a PowerShell prompt:
    powershell -ExecutionPolicy Bypass -File .\scripts\enable-https.ps1
==============================================================================
#>
[CmdletBinding()]
param(
    [ValidateSet("caddy", "traefik", "cloudflare-tunnel")]
    [string]$Proxy,
    [ValidateSet("letsencrypt", "cloudflare-dns", "none", "advanced")]
    [string]$Cert,
    [ValidateSet("letsencrypt", "letsencrypt-staging", "acme", "incommon", "internal", "custom", "none")]
    [string]$Mode,
    [string]$Domain,
    [string]$Email,
    [string]$AcmeCa,
    [string]$AcmeCaRoot,
    [string]$CfToken,
    [string]$TunnelToken,
    [string]$EabKid,
    [string]$EabHmac,
    [ValidateSet("", "rsa2048", "rsa4096", "p256", "p384")]
    [string]$KeyType = "",
    [switch]$CloudflareProxy,
    [switch]$NoRateLimit,
    [int]$RateLimit = 0,
    [int]$AuthRateLimit = 0,
    [string]$EnvFile = ".env",
    [switch]$Yes,
    [switch]$Disable
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Fail($msg) { Write-Host "Error: $msg" -ForegroundColor Red; exit 1 }
function Warn($msg) { Write-Host "Warning: $msg" -ForegroundColor Yellow }

# Prompt only when a person is actually at the console. With -Yes, when stdin is redirected (piped input / non-interactive launch), or when there's no interactive session at all (Scheduled Tasks, CI, a Windows service), never block: use the default — required values still missing are then caught by validation. This mirrors the bash version's "$YES = 1 || ! -t 0" check.
function Ask([string]$Prompt, [string]$Default = "") {
    $noConsole = -not [Environment]::UserInteractive
    $piped = $false
    try { $piped = [Console]::IsInputRedirected } catch { $piped = $false }
    if ($Yes -or $noConsole -or $piped) { return $Default }
    $suffix = if ($Default) { " [$Default]" } else { "" }
    $ans = Read-Host "$Prompt$suffix"
    if ([string]::IsNullOrEmpty($ans)) { return $Default }
    return $ans
}

function Test-ValidDomain([string]$d) {
    return $d -match '^[A-Za-z0-9*.-]+(,\s*[A-Za-z0-9*.-]+)*$'
}
function Test-ValidEmail([string]$e) {
    return $e -match '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
}

# ── .env helpers ─────────────────────────────────────────────────────────────
# Same behavior as the bash version's set_env/unset_env: replace an existing UNCOMMENTED "KEY=..." line in place (preserving every other line, comments included, and their order); otherwise append a new line.
#
# Read/write raw UTF-8 without a BOM via .NET directly, rather than
# Get-Content/Set-Content: their DEFAULT encoding differs between Windows PowerShell 5.1 (system codepage on read; UTF-8 WITH a BOM on write with -Encoding utf8) and PowerShell 7 (UTF-8 no BOM) — either mismatch can silently corrupt non-ASCII characters in .env, or hand docker compose a leading BOM byte some versions don't strip. A fixed, explicit encoding avoids depending on which PowerShell happens to be running this.
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Read-EnvLines([string]$Path) {
    if (-not (Test-Path $Path -PathType Leaf)) { return @() }
    return [System.IO.File]::ReadAllLines((Resolve-Path $Path).Path, [System.Text.Encoding]::UTF8)
}
function Write-EnvLines([string]$Path, [string[]]$Lines) {
    $full = if (Test-Path $Path -PathType Leaf) { (Resolve-Path $Path).Path } `
            else { Join-Path (Get-Location) $Path }
    [System.IO.File]::WriteAllLines($full, $Lines, $Utf8NoBom)
}
function Set-EnvVar([string]$Path, [string]$Key, [string]$Value) {
    $lines = Read-EnvLines $Path
    $pattern = "^$([regex]::Escape($Key))="
    $found = $false
    $out = @(foreach ($line in $lines) {
        if ($line -match $pattern) { $found = $true; "$Key=$Value" } else { $line }
    })
    if (-not $found) { $out = @($out) + "$Key=$Value" }
    Write-EnvLines $Path $out
}
function Remove-EnvVar([string]$Path, [string]$Key) {
    if (-not (Test-Path $Path -PathType Leaf)) { return }
    $pattern = "^$([regex]::Escape($Key))="
    $lines = @(Read-EnvLines $Path | Where-Object { $_ -notmatch $pattern })
    Write-EnvLines $Path $lines
}
function Backup-EnvFile([string]$Path) {
    if (Test-Path $Path -PathType Leaf) {
        $stamp = Get-Date -Format "yyyyMMddHHmmss"
        Copy-Item -Path $Path -Destination "$Path.bak.$stamp"
        Write-Host "Backed up $Path"
    }
}

function Test-Interactive {
    $noConsole = -not [Environment]::UserInteractive
    $piped = $false
    try { $piped = [Console]::IsInputRedirected } catch { $piped = $false }
    return -not ($Yes -or $noConsole -or $piped)
}
# Same as Ask, without echoing what's typed (tokens).
function Ask-Secret([string]$Prompt) {
    if (-not (Test-Interactive)) { return "" }
    $sec = Read-Host $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
# Tokens go into .env, so allow only their real character sets (no newlines/quotes).
function Test-ValidCfToken([string]$t) { return $t -cmatch '^[A-Za-z0-9_-]{20,}$' }
function Test-ValidTunnelToken([string]$t) { return $t -cmatch '^[A-Za-z0-9+/=_.-]{20,}$' }
function Test-HasEnv([string]$Path, [string]$Key) {
    $pattern = "^$([regex]::Escape($Key))=."
    return [bool](@(Read-EnvLines $Path | Where-Object { $_ -match $pattern }).Count)
}

$FrontDoorKeys = @("COMPOSE_PROFILES", "FRONT_DOOR", "HTTPS_CHECK_HOST", "HTTPS_MODE", "ACME_CHALLENGE",
                   "DOMAIN", "ACME_EMAIL", "ACME_CA", "ACME_CA_ROOT", "ACME_EAB_KID", "ACME_EAB_HMAC", "ACME_KEY_TYPE", "WEB_BIND", "WEB_PORT", "TRUSTED_PROXY_HOPS",
                   "RATE_LIMIT", "CLOUDFLARE_PROXY")

# ── -Disable ───────────────────────────────────────────────────────────────
if ($Disable) {
    Backup-EnvFile $EnvFile
    # Tokens too: no reason to keep Cloudflare credentials around with this off.
    foreach ($k in ($FrontDoorKeys + @("RATE_LIMIT_PER_MINUTE", "AUTH_RATE_LIMIT_PER_MINUTE",
                                       "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_TUNNEL_TOKEN"))) {
        Remove-EnvVar $EnvFile $k
    }
    Set-EnvVar $EnvFile "FRONTEND_URL" "http://localhost"
    Write-Host "Front door disabled. Run:  docker compose down; docker compose up -d"
    exit 0
}

if (-not (Test-Path $EnvFile)) {
    Fail "$EnvFile not found. Create it first (Copy-Item .env.example .env)."
}

# ── step 1: front door ──────────────────────────────────────────────────────
if (-not $Proxy) {
    if (Test-Interactive) {
        Write-Host "How should people reach OpenOptOut?"
        Write-Host "  1) Caddy              Built-in front door. Recommended if you have no preference."
        Write-Host "  2) Traefik            Built-in front door, for teams that already use Traefik."
        Write-Host "  3) Cloudflare Tunnel  No open ports or router setup at all."
        Write-Host "                        WARNING: Cloudflare decrypts and can see all traffic." -ForegroundColor Yellow
        switch (Ask "Choose 1-3" "1") {
            "1" { $Proxy = "caddy" }
            "2" { $Proxy = "traefik" }
            "3" { $Proxy = "cloudflare-tunnel" }
            default { Fail "Please choose 1-3." }
        }
        Write-Host ""
    } else { $Proxy = "caddy" }
}

# ── Cloudflare Tunnel: its own short path (Cloudflare holds the certificate) ─
if ($Proxy -eq "cloudflare-tunnel") {
    if ($Cert -or $Mode) { Fail "-Cert/-Mode don't apply to Cloudflare Tunnel: Cloudflare issues the certificate." }
    if ($CloudflareProxy) { Fail "-CloudflareProxy doesn't apply to Cloudflare Tunnel: tunnel traffic already goes through Cloudflare." }
    Write-Host "────────────────────────────────────────────────────────────────────────────────" -ForegroundColor Yellow
    Write-Host " WARNING: with Cloudflare Tunnel, Cloudflare decrypts ALL traffic to this site." -ForegroundColor Yellow
    Write-Host " Cloudflare's servers can see everything people send and receive here: names," -ForegroundColor Yellow
    Write-Host " home addresses, phone numbers, email addresses, and sign-in tokens." -ForegroundColor Yellow
    Write-Host " If that isn't acceptable, choose Caddy or Traefik with `"Let's Encrypt via" -ForegroundColor Yellow
    Write-Host " Cloudflare DNS`" instead: no open ports needed, and Cloudflare only ever sees a" -ForegroundColor Yellow
    Write-Host " DNS record, never your traffic." -ForegroundColor Yellow
    Write-Host "────────────────────────────────────────────────────────────────────────────────" -ForegroundColor Yellow
    if (Test-Interactive) {
        if ((Ask "Type yes to use Cloudflare Tunnel anyway") -ne "yes") { Fail "Cancelled. Nothing was changed." }
    }
    if (-not $Domain) { $Domain = Ask "Public hostname you set (or will set) on the tunnel (e.g. privacy.example.org)" }
    if ($Domain -notmatch '^[A-Za-z0-9.-]+$') { Fail "Enter one hostname, like privacy.example.org (got: $Domain)." }
    if (-not $TunnelToken -and -not (Test-HasEnv $EnvFile "CLOUDFLARE_TUNNEL_TOKEN")) {
        $TunnelToken = Ask-Secret "Tunnel token from the Cloudflare dashboard (blank = add it to .env later)"
    }
    if ($TunnelToken -and -not (Test-ValidTunnelToken $TunnelToken)) { Fail "That doesn't look like a tunnel token (copy the long value after --token)." }

    Backup-EnvFile $EnvFile
    foreach ($k in $FrontDoorKeys) { Remove-EnvVar $EnvFile $k }
    Set-EnvVar $EnvFile "COMPOSE_PROFILES" "cloudflare-tunnel"
    Set-EnvVar $EnvFile "FRONT_DOOR" "cloudflare-tunnel"
    Set-EnvVar $EnvFile "HTTPS_MODE" "cloudflare-tunnel"   # tells the certificate monitor not to check
    Set-EnvVar $EnvFile "DOMAIN" $Domain
    if ($TunnelToken) { Set-EnvVar $EnvFile "CLOUDFLARE_TUNNEL_TOKEN" $TunnelToken }
    Set-EnvVar $EnvFile "WEB_BIND" "127.0.0.1"
    Set-EnvVar $EnvFile "WEB_PORT" "8080"
    Set-EnvVar $EnvFile "TRUSTED_PROXY_HOPS" "2"   # cloudflared + nginx in front of the API
    Set-EnvVar $EnvFile "FRONTEND_URL" "https://$Domain"
    Write-Host ""
    Write-Host "Settings saved to $EnvFile."
    if (-not (Test-HasEnv $EnvFile "CLOUDFLARE_TUNNEL_TOKEN")) {
        Write-Host "Before starting, finish the Cloudflare side (docs/HTTPS.md, Option D):"
        Write-Host "  1. Cloudflare dashboard > Zero Trust > Networks > Tunnels > Create a tunnel (Cloudflared)."
        Write-Host "  2. Copy its token into $EnvFile as  CLOUDFLARE_TUNNEL_TOKEN=..."
        Write-Host "  3. Add a public hostname: $Domain  ->  Service: HTTP, URL: web:80"
        Write-Host "Then run:  docker compose up -d"
    } else {
        Write-Host "In the Cloudflare dashboard, make sure the tunnel's public hostname is"
        Write-Host "  $Domain  ->  Service: HTTP, URL: web:80"
        Write-Host "Then run:  docker compose up -d   and open https://$Domain"
    }
    Write-Host "Watch progress:  docker compose logs -f cloudflared"
    Write-Host "If you use Google/Microsoft sign-in or SAML, update their redirect URLs to https://$Domain (docs/SSO.md)."
    exit 0
}

# ── step 2: certificate (Caddy / Traefik) ───────────────────────────────────
if (-not $Cert -and -not $Mode) {
    if (Test-Interactive) {
        Write-Host "Where should the HTTPS certificate come from?"
        Write-Host "  1) Let's Encrypt                     Free and automatic. Ports 80 and 443 must"
        Write-Host "                                       be reachable from the internet."
        Write-Host "  2) Let's Encrypt via Cloudflare DNS  Free and automatic, NO open ports needed."
        Write-Host "                                       Your domain's DNS must be on Cloudflare."
        Write-Host "                                       Cloudflare sees only a DNS record, never"
        Write-Host "                                       your traffic. For many home internet plans"
        Write-Host "                                       (blocked ports, shared IP) this is the only"
        Write-Host "                                       option that works."
        Write-Host "  3) None for now                      Plain HTTP. Add a certificate later by"
        Write-Host "                                       running this script again."
        Write-Host "  4) Advanced                          Test service, your own CA, or your own files."
        switch (Ask "Choose 1-4" "1") {
            "1" { $Cert = "letsencrypt" }
            "2" { $Cert = "cloudflare-dns" }
            "3" { $Cert = "none" }
            "4" { $Cert = "advanced" }
            default { Fail "Please choose 1-4." }
        }
        Write-Host ""
    } else { $Cert = "letsencrypt" }
}
if (-not $Cert) { $Cert = if ($Mode -eq "none") { "none" } else { "advanced" } }

$Challenge = "http"
switch ($Cert) {
    "letsencrypt" {
        if (-not $Mode) { $Mode = "letsencrypt" }
        if ($Mode -notin @("letsencrypt", "letsencrypt-staging")) { Fail "-Cert letsencrypt goes with -Mode letsencrypt or letsencrypt-staging." }
    }
    "cloudflare-dns" {
        $Challenge = "cloudflare"
        if (-not $Mode) { $Mode = "letsencrypt" }
        if ($Mode -notin @("letsencrypt", "letsencrypt-staging", "acme", "incommon")) { Fail "Cloudflare DNS works with -Mode letsencrypt, letsencrypt-staging, acme, or incommon." }
    }
    "none" {
        if ($Mode -and $Mode -ne "none") { Fail "-Cert none can't be combined with -Mode $Mode." }
        $Mode = "none"
    }
    "advanced" {
        if (-not $Mode) {
            Write-Host "Advanced certificate options:"
            Write-Host "  1) letsencrypt-staging  Let's Encrypt's TEST service (untrusted certs; good for trying things)"
            Write-Host "  2) acme                 your own ACME CA (e.g. internal step-ca)"
            if ($Proxy -eq "caddy") {
                Write-Host "  3) internal             Caddy's own private CA (LAN only; browsers warn until trusted)"
            } else {
                Write-Host "  3) internal             (Caddy only — not available with Traefik)"
            }
            Write-Host "  4) custom               certificate files you provide"
            Write-Host "  5) incommon             InCommon certificates via CERTInext — BETA, untested." -ForegroundColor Yellow
            Write-Host "                          Mostly for universities in InCommon. You'll need the ACME key ID,"
            Write-Host "                          HMAC key and server address from your campus IT now."
            switch (Ask "Choose 1-5" "1") {
                "1" { $Mode = "letsencrypt-staging" }
                "2" { $Mode = "acme" }
                "3" { $Mode = "internal" }
                "4" { $Mode = "custom" }
                "5" { $Mode = "incommon" }
                default { Fail "Please choose 1-5." }
            }
        }
    }
}
if ($Proxy -eq "traefik" -and $Mode -eq "internal") {
    Fail "internal mode uses Caddy's private CA. Use -Proxy caddy, or -Mode custom with your own certificate."
}

# ── domain ──
if ($Mode -eq "none") {
    if (-not $Domain) { $Domain = Ask "Domain name, if you have one (blank = answer on any name)" "" }
    if ($Domain -and -not (Test-ValidDomain $Domain)) { Fail "Invalid domain: $Domain" }
} else {
    if (-not $Domain) { $Domain = Ask "Domain name people will use (e.g. privacy.yourlibrary.org)" }
    if (-not (Test-ValidDomain $Domain)) { Fail "Invalid domain: $Domain" }
}
if ($Proxy -eq "traefik" -and $Domain.Contains("*")) { Fail "Wildcard domains need -Proxy caddy (or list each name)." }
$Primary = if ($Domain) { $Domain.Split(",")[0].Trim() } else { "" }

# ── email ──
if (-not $Email -and $Mode -notin @("internal", "custom", "none")) {
    $Email = Ask "Contact email for the certificate authority (recommended)" ""
}
if ($Email -and -not (Test-ValidEmail $Email)) { Fail "Invalid email: $Email" }

# ── acme ──
$AcmeCaRootPath = ""
if ($Mode -eq "acme") {
    if (-not $AcmeCa) { $AcmeCa = Ask "ACME directory URL (e.g. https://ca.internal/acme/acme/directory)" }
    if ($AcmeCa -notmatch '^https://[A-Za-z0-9.:/_~%-]+$') { Fail "ACME CA must be an https:// URL" }
    if (-not $AcmeCaRoot) {
        $AcmeCaRoot = Ask "Path to the CA root certificate, if the ACME server uses an internal CA (blank = none)" ""
    }
    if ($AcmeCaRoot) {
        if (-not (Test-Path $AcmeCaRoot -PathType Leaf)) { Fail "File not found: $AcmeCaRoot" }
        if (-not (Select-String -Path $AcmeCaRoot -Pattern "BEGIN CERTIFICATE" -Quiet)) { Fail "Not a PEM certificate: $AcmeCaRoot" }
        New-Item -ItemType Directory -Force -Path "deploy/certs" | Out-Null
        Copy-Item -Path $AcmeCaRoot -Destination "deploy/certs/acme-ca-root.pem" -Force
        $AcmeCaRootPath = "/certs/acme-ca-root.pem"
    }
}

# ── account credentials (EAB) + key type ──
if ($Mode -eq "incommon") {
    # Required now, unlike the Cloudflare token: without them CERTInext refuses the account and nothing works.
    Write-Host ""
    Write-Host "InCommon (BETA, untested against a live account): CERTInext issues these to your campus IT," -ForegroundColor Yellow
    Write-Host "who give each department its own ACME key ID, HMAC key and server address."
    if (-not $AcmeCa) { $AcmeCa = Ask "ACME server address (directory URL) from campus IT" "https://acme-us.certinext.io/v1/directory" }
    if (-not $EabKid) { $EabKid = Ask "ACME key ID (EAB key ID)" }
    if (-not $EabHmac) { $EabHmac = Ask-Secret "ACME HMAC key (EAB HMAC key; typing is hidden)" }
    if (-not $EabKid -or -not $EabHmac) { Fail "InCommon needs the ACME key ID and HMAC key from campus IT during setup (-EabKid / -EabHmac). Nothing was changed." }
    $KeyType = "rsa2048"   # CERTInext requires RSA 2048
    if ($AcmeCa -notmatch '^https://[A-Za-z0-9.:/_~%-]+$') { Fail "The ACME server address must be an https:// URL" }
} elseif ($Mode -eq "acme" -and -not $EabKid -and -not $EabHmac -and (Test-Interactive)) {
    if ((Ask "Did your CA give you account credentials (an EAB key ID and HMAC key)? (y/n)" "n") -eq "y") {
        $EabKid = Ask "EAB key ID"
        $EabHmac = Ask-Secret "EAB HMAC key (typing is hidden)"
    }
}
if ($EabKid -or $EabHmac) {
    if ($Mode -notin @("acme", "incommon")) { Fail "-EabKid/-EabHmac only apply to -Mode acme or incommon." }
    if (-not $EabKid -or -not $EabHmac) { Fail "Give both the EAB key ID and the HMAC key." }
    if ($EabKid -cnotmatch '^[A-Za-z0-9_.-]{1,128}$') { Fail "That EAB key ID has unexpected characters." }
    if ($EabHmac -cnotmatch '^[A-Za-z0-9_-]{16,}={0,2}$') { Fail "That HMAC key doesn't look right (it's a long base64url string; copy it exactly)." }
}

# ── custom ──
if ($Mode -eq "custom") {
    foreach ($f in @("deploy/certs/fullchain.pem", "deploy/certs/privkey.pem")) {
        if (-not (Test-Path $f -PathType Leaf)) {
            Fail "Put your certificate files in deploy/certs/ first: fullchain.pem and privkey.pem ($f missing)."
        }
    }
}

# ── Cloudflare token ──
if ($Challenge -eq "cloudflare" -and -not $CfToken -and -not (Test-HasEnv $EnvFile "CLOUDFLARE_API_TOKEN")) {
    Write-Host "Cloudflare API token: in the Cloudflare dashboard, My Profile > API Tokens >"
    Write-Host "Create Token > 'Edit zone DNS' template, limited to this domain's zone."
    $CfToken = Ask-Secret "Paste the token (blank = add CLOUDFLARE_API_TOKEN to .env later)"
}
if ($CfToken -and -not (Test-ValidCfToken $CfToken)) { Fail "That doesn't look like a Cloudflare API token." }

# ── step 3: Cloudflare's proxy (DDoS protection) ──
# Only offered where it works: the certificate must not depend on Let's Encrypt reaching this server directly (Cloudflare DNS, or your own e.g. Cloudflare Origin certificate).
$cfProxyOk = ($Challenge -eq "cloudflare") -or ($Mode -eq "custom")
$UseCfProxy = [bool]$CloudflareProxy
if ($UseCfProxy -and -not $cfProxyOk) {
    Fail "-CloudflareProxy needs -Cert cloudflare-dns (or -Mode custom with a Cloudflare Origin certificate)."
}
if (-not $UseCfProxy -and $cfProxyOk -and (Test-Interactive)) {
    Write-Host ""
    Write-Host "Also put the site behind Cloudflare's proxy for DDoS protection?"
    Write-Host "  Cloudflare absorbs floods of traffic, hides this server's address, and this"
    Write-Host "  server will then refuse every connection that doesn't come through Cloudflare."
    Write-Host "  WARNING: Cloudflare then decrypts and can see ALL traffic to this site: names," -ForegroundColor Yellow
    Write-Host "  home addresses, phone numbers, emails, and sign-in tokens." -ForegroundColor Yellow
    Write-Host "  Needs ports 80/443 reachable from the internet (from Cloudflare). Most homes"
    Write-Host "  don't need this — it's for sites that are public and big enough to be a target."
    if ((Ask "Use Cloudflare proxy? Type yes, or press Enter for no" "no") -eq "yes") { $UseCfProxy = $true }
}
$CfProxyValue = if ($UseCfProxy) { "on" } else { "off" }

# ── rate limits ──
if ($RateLimit -lt 0 -or $AuthRateLimit -lt 0) { Fail "-RateLimit / -AuthRateLimit must be whole numbers above 0." }
$Rl = if ($NoRateLimit) { "off" } else { "on" }

# ── preflight ──
if ($Challenge -eq "http" -and $Mode -in @("letsencrypt", "letsencrypt-staging")) {
    $ip = $null
    try {
        $ip = (Resolve-DnsName -Name $Primary -Type A -ErrorAction Stop |
               Where-Object { $_.IPAddress } | Select-Object -First 1).IPAddress
    } catch {
        try { $ip = ([System.Net.Dns]::GetHostAddresses($Primary) | Select-Object -First 1).IPAddressToString } catch { $ip = $null }
    }
    if (-not $ip) {
        Warn "$Primary does not resolve in DNS yet. Let's Encrypt needs a DNS record pointing to this server."
    } else {
        Write-Host "DNS: $Primary -> $ip"
    }
    Write-Host "Let's Encrypt must reach this server on ports 80 and 443 from the internet (Windows Firewall + router/NAT)."
    Write-Host "If your internet provider blocks those ports or gives you a shared IP, use -Cert cloudflare-dns."
    if ($Mode -eq "letsencrypt") {
        Write-Host "Tip: test with -Mode letsencrypt-staging first to avoid rate limits, then switch."
    }
}

$certLabel = if ($Mode -eq "incommon") { "incommon (beta)" } else { $Mode }
if ($Challenge -eq "cloudflare") { $certLabel = "$certLabel via Cloudflare DNS" }
$domainLabel = if ($Domain) { $Domain } else { "(any)" }
$emailSuffix = if ($Email) { "  email=$Email" } else { "" }
Write-Host ""
$protectLabel = "rate-limits=$Rl"; if ($UseCfProxy) { $protectLabel += "  cloudflare-proxy=on" }
Write-Host "About to set up:  proxy=$Proxy  certificate=$certLabel  $protectLabel  domain=$domainLabel$emailSuffix"
if (Test-Interactive) {
    if ((Ask "Continue? (y/n)" "y") -ne "y") { Fail "Cancelled." }
}

Backup-EnvFile $EnvFile
foreach ($k in $FrontDoorKeys) { Remove-EnvVar $EnvFile $k }
# Caddy needs its extended build (caddy-extended service) for rate limits or Cloudflare DNS; Traefik has both built in.
$caddyExtended = ($Proxy -eq "caddy") -and (($Challenge -eq "cloudflare") -or ($Rl -eq "on"))
if ($Proxy -eq "traefik") { Set-EnvVar $EnvFile "COMPOSE_PROFILES" "https-traefik" }
elseif ($caddyExtended) { Set-EnvVar $EnvFile "COMPOSE_PROFILES" "https-caddy-extended" }
else { Set-EnvVar $EnvFile "COMPOSE_PROFILES" "https" }
Set-EnvVar $EnvFile "RATE_LIMIT" $Rl
if ($RateLimit -gt 0) { Set-EnvVar $EnvFile "RATE_LIMIT_PER_MINUTE" "$RateLimit" }
if ($AuthRateLimit -gt 0) { Set-EnvVar $EnvFile "AUTH_RATE_LIMIT_PER_MINUTE" "$AuthRateLimit" }
Set-EnvVar $EnvFile "CLOUDFLARE_PROXY" $CfProxyValue
Set-EnvVar $EnvFile "FRONT_DOOR" $Proxy
Set-EnvVar $EnvFile "HTTPS_CHECK_HOST" $Proxy   # the certificate monitor checks this container
Set-EnvVar $EnvFile "HTTPS_MODE" $Mode
Set-EnvVar $EnvFile "ACME_CHALLENGE" $Challenge
if ($Domain) { Set-EnvVar $EnvFile "DOMAIN" $Domain }
if ($Email) { Set-EnvVar $EnvFile "ACME_EMAIL" $Email }
if ($AcmeCa) { Set-EnvVar $EnvFile "ACME_CA" $AcmeCa }
if ($EabKid) { Set-EnvVar $EnvFile "ACME_EAB_KID" $EabKid }
if ($EabHmac) { Set-EnvVar $EnvFile "ACME_EAB_HMAC" $EabHmac }
if ($KeyType) { Set-EnvVar $EnvFile "ACME_KEY_TYPE" $KeyType }
if ($AcmeCaRootPath) { Set-EnvVar $EnvFile "ACME_CA_ROOT" $AcmeCaRootPath }
if ($CfToken) { Set-EnvVar $EnvFile "CLOUDFLARE_API_TOKEN" $CfToken }
# The front door owns ports 80/443; the web container stays reachable only on this machine.
Set-EnvVar $EnvFile "WEB_BIND" "127.0.0.1"
Set-EnvVar $EnvFile "WEB_PORT" "8080"
if ($UseCfProxy) {
    Set-EnvVar $EnvFile "TRUSTED_PROXY_HOPS" "3"   # Cloudflare + front door + nginx in front of the API
} else {
    Set-EnvVar $EnvFile "TRUSTED_PROXY_HOPS" "2"   # front door + nginx in front of the API
}
if ($Mode -eq "none") {
    $host_ = if ($Primary) { $Primary } else { "localhost" }
    Set-EnvVar $EnvFile "FRONTEND_URL" "http://$host_"
} else {
    Set-EnvVar $EnvFile "FRONTEND_URL" "https://$Primary"
}

Write-Host ""
Write-Host "Settings saved to $EnvFile."
if ($Challenge -eq "cloudflare" -and -not (Test-HasEnv $EnvFile "CLOUDFLARE_API_TOKEN")) {
    Write-Host "Not started yet: add your Cloudflare API token first (Zone > DNS > Edit for this domain):"
    Write-Host "    CLOUDFLARE_API_TOKEN=...   in $EnvFile"
    Write-Host "Then run:  docker compose up -d --build"
} else {
    Write-Host "Now run:"
    Write-Host "    docker compose up -d --build"
}
if ($Mode -eq "none") {
    $where = if ($Primary) { $Primary } else { "<this server>" }
    Write-Host "Then open http://$where  (plain HTTP — run this script again to add a certificate)."
} else {
    Write-Host "Then open https://$Primary  (first certificate can take a minute; with Cloudflare DNS, up to a few)."
}
$logSvc = if ($caddyExtended) { "caddy-extended" } else { $Proxy }
Write-Host "Watch progress:  docker compose logs -f $logSvc"
if ($caddyExtended) {
    Write-Host "(The first start builds Caddy with its extra modules; that takes a minute or two.)"
}
if ($UseCfProxy) {
    Write-Host ""
    Write-Host "Cloudflare proxy: finish these in the Cloudflare dashboard (docs/HTTPS.md, `"Behind Cloudflare's proxy`"):"
    Write-Host "  1. DNS: set the record for $Primary to Proxied (orange cloud), pointing at this server's public IP."
    Write-Host "  2. SSL/TLS > Overview: set encryption mode to Full (strict)."
    Write-Host "  3. Forward ports 80 and 443 to this server. Only Cloudflare will be let in."
    Write-Host "Remember: Cloudflare can now see all traffic to this site." -ForegroundColor Yellow
}
if ($Mode -eq "internal") {
    Write-Host "Browsers will warn until Caddy's root CA is trusted — see docs/HTTPS.md."
}
if ($Mode -eq "incommon") {
    Write-Host "InCommon is BETA and untested against a live CERTInext account. If the certificate doesn't arrive, check" -ForegroundColor Yellow
    Write-Host "the logs above and confirm the key ID, HMAC key, server address and domain with campus IT (docs/HTTPS.md)." -ForegroundColor Yellow
}
if ($Mode -eq "letsencrypt-staging") {
    Write-Host "Staging certificates are intentionally untrusted. Rerun with -Mode letsencrypt when it works."
}
if ($Mode -ne "none") {
    Write-Host "If you use Google/Microsoft sign-in or SAML, update their redirect URLs to https://$Primary (docs/SSO.md)."
}
exit 0
