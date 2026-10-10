<#
==============================================================================
Turn on HTTPS for OpenOptOut (Caddy or Traefik front door + automatic certificates).
Windows PowerShell / PowerShell 7 port of enable-https.sh — same behavior,
same .env keys, same docker compose commands afterward. Works whether Docker
Desktop or Docker Engine is running on this Windows Server (the containers
themselves are still Linux containers either way — this script never needs to
run inside them, only docker compose does).

  .\scripts\enable-https.ps1                       # interactive
  .\scripts\enable-https.ps1 -Mode letsencrypt -Domain privacy.lib.org -Email it@lib.org
  .\scripts\enable-https.ps1 -Proxy traefik        # use Traefik instead of Caddy
  .\scripts\enable-https.ps1 -Disable              # back to plain HTTP

Options: -Mode letsencrypt|letsencrypt-staging|acme|internal|custom
         -Domain D  -Email E  -AcmeCa URL  -AcmeCaRoot FILE
         -Proxy caddy|traefik (default caddy; Traefik has no 'internal' mode)
         -EnvFile PATH (default .env)  -Yes (no confirmation prompt)

Writes settings to .env (a timestamped backup is made first), then tells you
the one command to run.

If double-clicking is blocked by execution policy, either run
scripts\enable-https.cmd instead (it bypasses policy for this script only), or
run from a PowerShell prompt:
    powershell -ExecutionPolicy Bypass -File .\scripts\enable-https.ps1
==============================================================================
#>
[CmdletBinding()]
param(
    [ValidateSet("letsencrypt", "letsencrypt-staging", "acme", "internal", "custom")]
    [string]$Mode,
    [string]$Domain,
    [string]$Email,
    [string]$AcmeCa,
    [string]$AcmeCaRoot,
    [ValidateSet("caddy", "traefik")]
    [string]$Proxy = "caddy",
    [string]$EnvFile = ".env",
    [switch]$Yes,
    [switch]$Disable
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Fail($msg) { Write-Host "Error: $msg" -ForegroundColor Red; exit 1 }
function Warn($msg) { Write-Host "Warning: $msg" -ForegroundColor Yellow }

# Prompt only when a person is actually at the console. With -Yes, when stdin
# is redirected (piped input / non-interactive launch), or when there's no
# interactive session at all (Scheduled Tasks, CI, a Windows service), never
# block: use the default — required values still missing are then caught by
# validation. This mirrors the bash version's "$YES = 1 || ! -t 0" check.
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
# Same behavior as the bash version's set_env/unset_env: replace an existing
# UNCOMMENTED "KEY=..." line in place (preserving every other line, comments
# included, and their order); otherwise append a new line.
#
# Read/write raw UTF-8 without a BOM via .NET directly, rather than
# Get-Content/Set-Content: their DEFAULT encoding differs between Windows
# PowerShell 5.1 (system codepage on read; UTF-8 WITH a BOM on write with
# -Encoding utf8) and PowerShell 7 (UTF-8 no BOM) — either mismatch can
# silently corrupt non-ASCII characters in .env, or hand docker compose a
# leading BOM byte some versions don't strip. A fixed, explicit encoding
# avoids depending on which PowerShell happens to be running this.
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

# ── --disable ──────────────────────────────────────────────────────────────
if ($Disable) {
    Backup-EnvFile $EnvFile
    foreach ($k in @("COMPOSE_PROFILES", "FRONT_DOOR", "HTTPS_CHECK_HOST", "HTTPS_MODE", "DOMAIN", "ACME_EMAIL", "ACME_CA",
                      "ACME_CA_ROOT", "WEB_BIND", "WEB_PORT", "TRUSTED_PROXY_HOPS")) {
        Remove-EnvVar $EnvFile $k
    }
    Set-EnvVar $EnvFile "FRONTEND_URL" "http://localhost"
    Write-Host "HTTPS disabled. Run:  docker compose down; docker compose up -d"
    exit 0
}

if (-not (Test-Path $EnvFile)) {
    Fail "$EnvFile not found. Create it first (Copy-Item .env.example .env)."
}

# ── mode ──
if (-not $Mode) {
    Write-Host "How should OpenOptOut get its certificate?"
    Write-Host "  1) letsencrypt          public server (ports 80+443 reachable from the internet)"
    Write-Host "  2) letsencrypt-staging  same, but Let's Encrypt's TEST service (untrusted certs; use first)"
    Write-Host "  3) acme                 your own ACME CA (e.g. internal step-ca)"
    if ($Proxy -eq "caddy") {
        Write-Host "  4) internal             Caddy's own private CA (LAN only; browsers warn until trusted)"
    } else {
        Write-Host "  4) internal             (Caddy only — not available with Traefik)"
    }
    Write-Host "  5) custom               certificate files you provide"
    switch (Ask "Choose 1-5" "2") {
        "1" { $Mode = "letsencrypt" }
        "2" { $Mode = "letsencrypt-staging" }
        "3" { $Mode = "acme" }
        "4" { $Mode = "internal" }
        "5" { $Mode = "custom" }
        default { Fail "Please choose 1-5." }
    }
}
if ($Proxy -eq "traefik" -and $Mode -eq "internal") {
    Fail "internal mode uses Caddy's private CA. Use -Proxy caddy, or -Mode custom with your own certificate."
}

# ── domain ──
if (-not $Domain) { $Domain = Ask "Domain name people will use (e.g. privacy.yourlibrary.org)" }
if (-not (Test-ValidDomain $Domain)) { Fail "Invalid domain: $Domain" }
if ($Proxy -eq "traefik" -and $Domain.Contains("*")) { Fail "Wildcard domains need -Proxy caddy (or list each name)." }
$Primary = $Domain.Split(",")[0].Trim()

# ── email ──
if (-not $Email -and $Mode -ne "internal" -and $Mode -ne "custom") {
    $Email = Ask "Contact email for the certificate authority (recommended)" ""
}
if ($Email -and -not (Test-ValidEmail $Email)) { Fail "Invalid email: $Email" }

# ── acme ──
$FinalAcmeCaRoot = ""
if ($Mode -eq "acme") {
    if (-not $AcmeCa) { $AcmeCa = Ask "ACME directory URL (e.g. https://ca.internal/acme/acme/directory)" }
    if ($AcmeCa -notmatch '^https://[A-Za-z0-9.:/_~%-]+$') { Fail "ACME CA must be an https:// URL" }
    if (-not $AcmeCaRoot -and -not $Yes) {
        $AcmeCaRoot = Ask "Path to the CA root certificate, if the ACME server uses an internal CA (blank = none)" ""
    }
    if ($AcmeCaRoot) {
        if (-not (Test-Path $AcmeCaRoot -PathType Leaf)) { Fail "File not found: $AcmeCaRoot" }
        if (-not (Select-String -Path $AcmeCaRoot -Pattern "BEGIN CERTIFICATE" -Quiet)) {
            Fail "Not a PEM certificate: $AcmeCaRoot"
        }
        New-Item -ItemType Directory -Force -Path "deploy\certs" | Out-Null
        Copy-Item -Path $AcmeCaRoot -Destination "deploy\certs\acme-ca-root.pem" -Force
        $FinalAcmeCaRoot = "/certs/acme-ca-root.pem"   # path INSIDE the Linux container, not a Windows path
    }
}

# ── custom ──
if ($Mode -eq "custom") {
    foreach ($f in @("deploy\certs\fullchain.pem", "deploy\certs\privkey.pem")) {
        if (-not (Test-Path $f -PathType Leaf)) {
            Fail "Put your certificate files in deploy/certs/ first: fullchain.pem and privkey.pem ($f missing)."
        }
    }
}

# ── preflight ──
if ($Mode -eq "letsencrypt" -or $Mode -eq "letsencrypt-staging") {
    $ip = $null
    try {
        $ip = (Resolve-DnsName -Name $Primary -Type A -ErrorAction Stop |
               Where-Object { $_.Type -eq "A" } | Select-Object -First 1).IPAddress
    } catch { $ip = $null }
    if (-not $ip) {
        Warn "$Primary does not resolve in DNS yet. Let's Encrypt needs a DNS record pointing to this server."
    } else {
        Write-Host "DNS: $Primary -> $ip"
    }
    Write-Host "Let's Encrypt must reach this server on ports 80 and 443 from the internet (Windows Firewall + router/NAT)."
    if ($Mode -eq "letsencrypt") {
        Write-Host "Tip: test with -Mode letsencrypt-staging first to avoid rate limits, then switch."
    }
}

Write-Host ""
$emailSuffix = if ($Email) { "  email=$Email" } else { "" }
Write-Host "About to enable HTTPS:  proxy=$Proxy  mode=$Mode  domain=$Domain$emailSuffix"
if (-not $Yes) {
    if ((Ask "Continue? (y/n)" "y") -ne "y") { Fail "Cancelled." }
}

Backup-EnvFile $EnvFile
if ($Proxy -eq "traefik") { Set-EnvVar $EnvFile "COMPOSE_PROFILES" "https-traefik" }
else { Set-EnvVar $EnvFile "COMPOSE_PROFILES" "https" }
Set-EnvVar $EnvFile "FRONT_DOOR" $Proxy
Set-EnvVar $EnvFile "HTTPS_CHECK_HOST" $Proxy   # the certificate monitor checks this container
Set-EnvVar $EnvFile "HTTPS_MODE" $Mode
Set-EnvVar $EnvFile "DOMAIN" $Domain
if ($Email) { Set-EnvVar $EnvFile "ACME_EMAIL" $Email } else { Remove-EnvVar $EnvFile "ACME_EMAIL" }
if ($AcmeCa) { Set-EnvVar $EnvFile "ACME_CA" $AcmeCa } else { Remove-EnvVar $EnvFile "ACME_CA" }
if ($FinalAcmeCaRoot) { Set-EnvVar $EnvFile "ACME_CA_ROOT" $FinalAcmeCaRoot } else { Remove-EnvVar $EnvFile "ACME_CA_ROOT" }
# The front door owns ports 80/443; the web container stays reachable only on this machine.
Set-EnvVar $EnvFile "WEB_BIND" "127.0.0.1"
Set-EnvVar $EnvFile "WEB_PORT" "8080"
Set-EnvVar $EnvFile "TRUSTED_PROXY_HOPS" "2"   # front door + nginx in front of the API
Set-EnvVar $EnvFile "FRONTEND_URL" "https://$Primary"

Write-Host ""
Write-Host "HTTPS settings saved to $EnvFile. Now run:"
Write-Host "    docker compose up -d --build"
Write-Host "Then open https://$Primary  (first certificate can take a minute)."
Write-Host "Watch progress:  docker compose logs -f $Proxy"
if ($Mode -eq "internal") {
    Write-Host "Browsers will warn until Caddy's root CA is trusted — see docs/HTTPS.md."
}
if ($Mode -eq "letsencrypt-staging") {
    Write-Host "Staging certificates are intentionally untrusted. Rerun with -Mode letsencrypt when it works."
}
Write-Host "If you use Google/Microsoft sign-in or SAML, update their redirect URLs to https://$Primary (docs/SSO.md)."
exit 0
