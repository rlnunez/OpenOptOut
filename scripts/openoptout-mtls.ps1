<#
==============================================================================
Manage self-managed mutual TLS (mTLS) client certificates for OpenOptOut.
PowerShell script for Windows / PowerShell Core.

Mint a local Certificate Authority (CA) and issue or revoke per-device
client certificates exported as PKCS#12 (.p12 / .pfx) bundles.

Usage:
  .\scripts\openoptout-mtls.ps1 init-ca [-Days 3650] [-CaDir DIR] [-Force]
  .\scripts\openoptout-mtls.ps1 issue <device-name> [-Days 365] [-CaDir DIR] [-Out FILE] [-Pass PASS]
  .\scripts\openoptout-mtls.ps1 revoke <device-name-or-serial> [-CaDir DIR]
  .\scripts\openoptout-mtls.ps1 list [-CaDir DIR]
  .\scripts\openoptout-mtls.ps1 status [-CaDir DIR]
==============================================================================
#>
[CmdletBinding()]
param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet("init-ca", "issue", "revoke", "list", "status", "help")]
    [string]$Command,

    [Parameter(Position=1)]
    [string]$Target,

    [string]$CaDir = "deploy/ca",
    [int]$Days = 0,
    [string]$Out = "",
    [string]$Pass = "",
    [string]$Reason = "unspecified",
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptDir "..")

# Find openssl
$openssl = Get-Command "openssl" -ErrorAction SilentlyContinue
if (-not $openssl) {
    # Check standard Git for Windows location
    $gitOpenssl = "C:\Program Files\Git\usr\bin\openssl.exe"
    if (Test-Path $gitOpenssl) {
        $opensslCmd = $gitOpenssl
    } else {
        Write-Error "openssl is required but was not found in PATH or at '$gitOpenssl'."
        exit 1
    }
} else {
    $opensslCmd = $openssl.Source
}

$ProxyCertsDir = "deploy/certs"
$CaKey = Join-Path $CaDir "client-ca.key"
$CaCert = Join-Path $CaDir "client-ca.pem"
$ProxyCaCert = Join-Path $ProxyCertsDir "client-ca.pem"
$IndexFile = Join-Path $CaDir "index.json"
$SerialFile = Join-Path $CaDir "serial"

function Ensure-CaDir {
    if (-not (Test-Path $CaDir)) {
        New-Item -ItemType Directory -Path $CaDir -Force | Out-Null
    }
    if (-not (Test-Path $ProxyCertsDir)) {
        New-Item -ItemType Directory -Path $ProxyCertsDir -Force | Out-Null
    }
    if (-not (Test-Path $SerialFile)) {
        "1001" | Out-File -FilePath $SerialFile -Encoding ascii
    }
    if (-not (Test-Path $IndexFile)) {
        "[]" | Out-File -FilePath $IndexFile -Encoding utf8
    }
}

function Invoke-InitCa {
    Ensure-CaDir
    $caDays = if ($Days -gt 0) { $Days } else { 3650 }

    if ((Test-Path $CaCert) -and (Test-Path $CaKey) -and (-not $Force)) {
        Write-Warning "A Client CA already exists at $CaCert."
        Write-Host "Pass -Force to overwrite it (warning: all existing client certificates will be invalidated)."
        exit 1
    }

    Write-Host "==> Initializing OpenOptOut Client Certificate Authority..." -ForegroundColor Cyan

    $tmpCnf = [System.IO.Path]::GetTempFileName()
    @"
[req]
distinguished_name = req_dn
x509_extensions = v3_ca
prompt = no

[req_dn]
CN = OpenOptOut Client CA

[v3_ca]
basicConstraints = critical, CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
"@ | Out-File -FilePath $tmpCnf -Encoding ascii

    try {
        & $opensslCmd req -new -x509 -newkey rsa:4096 -nodes `
            -keyout $CaKey `
            -out $CaCert `
            -days $caDays `
            -sha256 `
            -config $tmpCnf 2>$null
    } finally {
        Remove-Item -Path $tmpCnf -Force -ErrorAction SilentlyContinue
    }

    Copy-Item -Path $CaCert -Destination $ProxyCaCert -Force

    $fp = (& $opensslCmd x509 -in $CaCert -noout -fingerprint -sha256).Split('=')[-1]
    $exp = (& $opensslCmd x509 -in $CaCert -noout -enddate).Split('=')[-1]

    Write-Host "✓ Client CA initialized successfully!" -ForegroundColor Green
    Write-Host "  CA Certificate:   $CaCert"
    Write-Host "  CA Private Key:   $CaKey"
    Write-Host "  Proxy CA Copy:    $ProxyCaCert"
    Write-Host "  Valid Until:      $exp"
    Write-Host "  SHA-256 Fingerprint: $fp"
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Issue certificates for devices that need access:"
    Write-Host "     .\scripts\openoptout-mtls.ps1 issue <device-name>"
    Write-Host "  2. Enable mTLS enforcement on your reverse proxy:"
    Write-Host "     .\scripts\enable-https.ps1 -ClientMtls"
}

function Invoke-Issue {
    Ensure-CaDir
    if (-not $Target) {
        Write-Error "device-name is required. Example: .\scripts\openoptout-mtls.ps1 issue jordan-laptop"
        exit 1
    }

    $devName = $Target
    $safeName = $devName -replace '[^a-zA-Z0-9._-]', '-'

    if ((-not (Test-Path $CaCert)) -or (-not (Test-Path $CaKey))) {
        Write-Error "Client CA not found at $CaCert. Run '.\scripts\openoptout-mtls.ps1 init-ca' first."
        exit 1
    }

    $clientDays = if ($Days -gt 0) { $Days } else { 365 }
    $serial = (Get-Content $SerialFile -Raw).Trim()
    $nextSerial = [int]$serial + 1
    "$nextSerial" | Out-File -FilePath $SerialFile -Encoding ascii

    $devDir = Join-Path $CaDir (Join-Path "issued" $safeName)
    if (-not (Test-Path $devDir)) {
        New-Item -ItemType Directory -Path $devDir -Force | Out-Null
    }

    $clientKey = Join-Path $devDir "$safeName.key"
    $clientCsr = Join-Path $devDir "$safeName.csr"
    $clientCert = Join-Path $devDir "$safeName.crt"
    $p12Path = if ($Out) { $Out } else { Join-Path $devDir "$safeName.p12" }

    $pfxPass = $Pass
    if (-not $pfxPass) {
        $pfxPass = Read-Host -Prompt "Enter password to protect the .p12 certificate bundle (press Enter for none)" -AsSecureString
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($pfxPass)
        $pfxPass = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    }

    Write-Host "==> Generating client certificate for '$devName' (serial $serial)..." -ForegroundColor Cyan

    & $opensslCmd genrsa -out $clientKey 2048 2>$null
    & $opensslCmd req -new -key $clientKey -out $clientCsr -subj "/CN=$devName" 2>$null

    $tmpExt = [System.IO.Path]::GetTempFileName()
    @"
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
"@ | Out-File -FilePath $tmpExt -Encoding ascii

    try {
        & $opensslCmd x509 -req -in $clientCsr `
            -CA $CaCert `
            -CAkey $CaKey `
            -set_serial $serial `
            -out $clientCert `
            -days $clientDays `
            -sha256 `
            -extfile $tmpExt 2>$null
    } finally {
        Remove-Item -Path $tmpExt -Force -ErrorAction SilentlyContinue
        Remove-Item -Path $clientCsr -Force -ErrorAction SilentlyContinue
    }

    $passArg = if ($pfxPass) { "pass:$pfxPass" } else { "pass:" }
    & $opensslCmd pkcs12 -export -out $p12Path `
        -inkey $clientKey `
        -in $clientCert `
        -certfile $CaCert `
        -name $devName `
        -passout $passArg 2>$null

    $expIso = (& $opensslCmd x509 -in $clientCert -noout -enddate).Split('=')[-1]
    $nowIso = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

    $json = Get-Content $IndexFile -Raw | ConvertFrom-Json
    $list = @($json) | Where-Object { $_.name -ne $devName -or $_.status -eq "revoked" }
    $list += [PSCustomObject]@{
        name = $devName
        serial = $serial
        issued_at = $nowIso
        expires_at = $expIso
        status = "valid"
        p12_path = $p12Path
    }
    $list | ConvertTo-Json -Depth 5 | Out-File -FilePath $IndexFile -Encoding utf8

    Write-Host "✓ Client certificate successfully issued!" -ForegroundColor Green
    Write-Host "  Device Name:   $devName"
    Write-Host "  Serial Number: $serial"
    Write-Host "  Valid Until:   $expIso"
    Write-Host "  PKCS#12 File:  $p12Path"
    Write-Host ""
    Write-Host "How to install this certificate on your device:" -ForegroundColor White
    Write-Host "  • Windows:       Double-click the .p12 file, choose 'Current User' -> 'Personal' store."
    Write-Host "  • macOS / iOS:   Double-click the .p12 file to import it into Keychain Access."
    Write-Host "  • Linux/Firefox: Settings -> Privacy & Security -> Certificates -> View Certificates -> Import."
    Write-Host "  • Android:       Settings -> Security -> Encryption & credentials -> Install user certificate."
}

function Invoke-Revoke {
    Ensure-CaDir
    if (-not $Target) {
        Write-Error "device-name or serial is required. Example: .\scripts\openoptout-mtls.ps1 revoke jordan-laptop"
        exit 1
    }

    $json = Get-Content $IndexFile -Raw | ConvertFrom-Json
    $found = $false
    foreach ($entry in @($json)) {
        if ($entry.name -eq $Target -or $entry.serial -eq $Target) {
            $entry.status = "revoked"
            $entry | Add-Member -NotePropertyName "revoked_at" -NotePropertyValue (Get-Date).ToString("u") -Force
            $found = $true
            Write-Host "Revoked certificate for '$($entry.name)' (serial $($entry.serial))."
        }
    }
    if (-not $found) {
        Write-Error "Certificate '$Target' not found."
        exit 1
    }
    $json | ConvertTo-Json -Depth 5 | Out-File -FilePath $IndexFile -Encoding utf8
    Write-Host "✓ Certificate recorded as revoked." -ForegroundColor Green
}

function Invoke-List {
    Ensure-CaDir
    $json = Get-Content $IndexFile -Raw | ConvertFrom-Json
    $items = @($json)
    if ($items.Count -eq 0) {
        Write-Host "No client certificates have been issued yet."
        Write-Host "Run '.\scripts\openoptout-mtls.ps1 issue <device-name>' to issue one."
        return
    }
    $items | Format-Table -Property name, serial, status, expires_at, p12_path
}

function Invoke-Status {
    Ensure-CaDir
    if (-not (Test-Path $CaCert)) {
        Write-Warning "Client CA has not been initialized yet. Run '.\scripts\openoptout-mtls.ps1 init-ca' to create one."
        return
    }
    $fp = (& $opensslCmd x509 -in $CaCert -noout -fingerprint -sha256).Split('=')[-1]
    $subj = (& $opensslCmd x509 -in $CaCert -noout -subject) -replace 'subject=', ''
    $start = (& $opensslCmd x509 -in $CaCert -noout -startdate).Split('=')[-1]
    $end = (& $opensslCmd x509 -in $CaCert -noout -enddate).Split('=')[-1]

    Write-Host "OpenOptOut Client CA Status:" -ForegroundColor White
    Write-Host "  Subject:      $subj"
    Write-Host "  Certificate:  $CaCert"
    Write-Host "  Key:          $CaKey"
    Write-Host "  Valid From:   $start"
    Write-Host "  Valid Until:  $end"
    Write-Host "  Fingerprint:  $fp"

    if (Test-Path $ProxyCaCert) {
        $pfp = (& $opensslCmd x509 -in $ProxyCaCert -noout -fingerprint -sha256).Split('=')[-1]
        if ($fp -eq $pfp) {
            Write-Host "  Proxy Copy:   $ProxyCaCert (synchronized)" -ForegroundColor Green
        } else {
            Write-Host "  Proxy Copy:   $ProxyCaCert (out of sync! Run: Copy-Item $CaCert $ProxyCaCert)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Proxy Copy:   Missing! Run: Copy-Item $CaCert $ProxyCaCert" -ForegroundColor Red
    }
    Write-Host ""
    Invoke-List
}

switch ($Command) {
    "init-ca" { Invoke-InitCa }
    "issue"   { Invoke-Issue }
    "revoke"  { Invoke-Revoke }
    "list"    { Invoke-List }
    "status"  { Invoke-Status }
    default   { Get-Help $MyInvocation.MyCommand.Path }
}

