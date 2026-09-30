<#
==============================================================================
Native (no Docker) install/update helper for OpenOptOut on Windows.

  .\deploy\native\install-native.ps1                # first install
  .\deploy\native\install-native.ps1 -Update         # pull code changes back in
  .\deploy\native\install-native.ps1 -SkipPlaywright # skip the Firefox download
                                                       # (retry it later yourself —
                                                       # see docs/NATIVE_INSTALL.md)

Run this from the root of an OpenOptOut git checkout (same folder this
script's path implies — it uses $PSScriptRoot to find the repo root, the same
way scripts/enable-https.ps1 does).

What this automates (the safe, mechanical parts):
  1. Creates a venv under backend\venv and installs Python dependencies
  2. Installs Playwright's Firefox (best-effort — see -SkipPlaywright above;
     a failed download here does NOT stop the rest of the install)
  3. Copies the backend into .\app, laid out as an importable "app" package
     (main.py's relative imports need this — mirrors the Docker image and
     deploy/native/install.sh on Linux exactly)
  4. Compiles the plugin gRPC protocol stubs (best-effort — the plugin system
     just stays inactive if this fails)
  5. Builds the frontend (npm run build) into .\frontend\dist
  6. On first install only: creates .env from .env.example with a generated
     SECRET_KEY, and creates .\data\

What this does NOT automate — printed as exact next commands instead, because
reliably scripting IIS/NSSM registration across Windows Server versions isn't
a good fit for one script the way a Linux systemd unit + certbot CLI is:
  7. Registering the API as a Windows Service (via NSSM)
  8. Setting up IIS (ARR + URL Rewrite) to serve the frontend and proxy /api/
  9. HTTPS via win-acme

Full walkthrough for all of this: docs/NATIVE_INSTALL.md
==============================================================================
#>
[CmdletBinding()]
param(
    [switch]$Update,
    [switch]$SkipPlaywright
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

function Fail($msg) { Write-Host "Error: $msg" -ForegroundColor Red; exit 1 }
function Warn($msg) { Write-Host "Warning: $msg" -ForegroundColor Yellow }
function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

if (-not (Test-Path (Join-Path $RepoRoot "backend\main.py"))) {
    Fail "Couldn't find backend\main.py under $RepoRoot — run this from inside an OpenOptOut repo checkout."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Fail "python not found on PATH. Install Python 3.12 first." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "npm not found on PATH. Install Node.js LTS first." }

# ── 1. venv + Python deps ──
$VenvDir = Join-Path $RepoRoot "backend\venv"
if (-not (Test-Path $VenvDir)) {
    Step "Creating venv at $VenvDir"
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Fail "Creating the venv failed (see output above)." }
}
$Pip = Join-Path $VenvDir "Scripts\pip.exe"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$Playwright = Join-Path $VenvDir "Scripts\playwright.exe"

Step "Installing Python dependencies"
& $Pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed (see output above)." }
& $Pip install -r (Join-Path $RepoRoot "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "Installing Python dependencies failed (see pip output above)." }
$EncReq = Join-Path $RepoRoot "backend\requirements-encryption.txt"
if (Test-Path $EncReq) {
    & $Pip install -r $EncReq
    if ($LASTEXITCODE -ne 0) {
        Warn "sqlcipher3 install failed for this platform — continuing without file-level encryption."
    }
}

# ── 2. Playwright's Firefox ──
if ($SkipPlaywright) {
    Warn "Skipping Playwright's Firefox download (-SkipPlaywright). Automated opt-out" 
    Warn "form-filling won't work until you run this yourself later:"
    Warn "    $Playwright install firefox"
} else {
    & $Playwright install firefox
    if ($LASTEXITCODE -ne 0) {
        Warn "Playwright's Firefox download failed — common behind a corporate proxy"
        Warn "that blocks Microsoft's CDN (playwright*.azureedge.net). The rest of"
        Warn "OpenOptOut will still work; automated opt-out form-filling won't,"
        Warn "until you retry this manually once network access allows it:"
        Warn "    $Playwright install firefox"
    }
}

# ── 3. copy the backend, laid out as the "app" package ──
$AppDir = Join-Path $RepoRoot "app"
$BackendDir = Join-Path $RepoRoot "backend"
Step "Laying out the backend as the 'app' package at $AppDir"
# Robocopy (not Copy-Item -Recurse) so venv/__pycache__/settings files are
# EXCLUDED from the copy itself, rather than copied and then deleted — venv
# already exists under backend\ by this point (step 1) and can be large.
# Robocopy's "success" exit codes are 0-7, not just 0 (see its docs); only
# 8+ means a real failure.
robocopy $BackendDir $AppDir /E /XD venv __pycache__ /XF openoptout_settings.json privacyshield_settings.json cert_monitor.json /NFL /NDL /NJH | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "Copying backend -> app failed (robocopy exit code $LASTEXITCODE)." }

New-Item -ItemType File -Force -Path (Join-Path $AppDir "__init__.py") | Out-Null
foreach ($d in @("models", "routers", "core")) {
    $sub = Join-Path $AppDir $d
    if (Test-Path $sub) { New-Item -ItemType File -Force -Path (Join-Path $sub "__init__.py") | Out-Null }
}

# ── 4. compile the plugin gRPC stubs (best-effort) ──
$ProtoDir = Join-Path $AppDir "plugins\proto"
$ProtoFile = Join-Path $ProtoDir "plugin.proto"
if (Test-Path $ProtoFile) {
    Step "Compiling plugin protocol stubs"
    & $Python -m grpc_tools.protoc "-I$ProtoDir" "--python_out=$ProtoDir" "--grpc_python_out=$ProtoDir" $ProtoFile
    if ($LASTEXITCODE -eq 0) {
        $GrpcFile = Join-Path $ProtoDir "plugin_pb2_grpc.py"
        (Get-Content $GrpcFile) -replace '^import plugin_pb2 as', 'from . import plugin_pb2 as' |
            Set-Content $GrpcFile
        New-Item -ItemType File -Force -Path (Join-Path $ProtoDir "__init__.py") | Out-Null
    } else {
        Warn "Proto compile failed — plugin system will be inactive."
    }
}

# ── 5. build the frontend ──
Step "Building frontend"
Push-Location (Join-Path $RepoRoot "frontend")
try {
    npm install
    if ($LASTEXITCODE -ne 0) { Fail "npm install failed (see output above)." }
    npm run build
    if ($LASTEXITCODE -ne 0) { Fail "Frontend build failed (see npm output above)." }
} finally {
    Pop-Location
}

# ── 6. first-install-only setup ──
if (-not $Update) {
    $EnvFile = Join-Path $RepoRoot ".env"
    $DataDir = Join-Path $RepoRoot "data"
    New-Item -ItemType Directory -Force -Path $DataDir, (Join-Path $DataDir "logo"),
        (Join-Path $DataDir "plugins"), (Join-Path $DataDir "plugin_storage"),
        (Join-Path $DataDir "screenshots") | Out-Null
    if (-not (Test-Path $EnvFile)) {
        Copy-Item (Join-Path $RepoRoot ".env.example") $EnvFile
        $Secret = -join ((1..64) | ForEach-Object { "{0:x}" -f (Get-Random -Maximum 16) })
        (Get-Content $EnvFile) -replace '^SECRET_KEY=.*', "SECRET_KEY=$Secret" | Set-Content $EnvFile
        Add-Content $EnvFile "SETTINGS_FILE=$RepoRoot\data\openoptout_settings.json"
        Add-Content $EnvFile "LOGO_PATH=$RepoRoot\data\logo"
        Write-Host "Created $EnvFile with a generated SECRET_KEY."
    }

    Write-Host ""
    Write-Host "============================================================"
    Write-Host " First install steps still needed (docs/NATIVE_INSTALL.md has the full version):"
    Write-Host "   1. Review $EnvFile (database, email, etc — see .env.example)"
    Write-Host "   2. Register the Windows Service with NSSM (https://nssm.cc/):"
    Write-Host "      nssm install OpenOptOutAPI `"$VenvDir\Scripts\uvicorn.exe`" `"app.main:app --host 127.0.0.1 --port 8000 --workers 2`""
    Write-Host "      nssm set OpenOptOutAPI AppDirectory `"$RepoRoot`""
    Write-Host "      nssm start OpenOptOutAPI"
    Write-Host "      Invoke-WebRequest http://127.0.0.1:8000/api/health   # should say {`"status`":`"ok`"}"
    Write-Host "   3. Set up IIS (ARR + URL Rewrite) to serve frontend\dist and proxy /api/"
    Write-Host "      to 127.0.0.1:8000 — see docs/NATIVE_INSTALL.md for the exact rule."
    Write-Host "   4. Turn on HTTPS with win-acme (https://www.win-acme.com/), then set"
    Write-Host "      FRONTEND_URL=https://your-domain in .env and restart the service:"
    Write-Host "      nssm restart OpenOptOutAPI"
    Write-Host "============================================================"
} else {
    Write-Host "==> Update complete. Restart the service to pick up code changes:"
    Write-Host "    nssm restart OpenOptOutAPI"
}
exit 0
