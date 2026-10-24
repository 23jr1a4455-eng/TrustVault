# Checks the LIVE audit chain and every saved anchor.
# Needs the external database URL and the AUDIT_HMAC_KEY from the host's settings.
#
# Run from any directory:   .\scripts\verify_live.ps1
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $repoRoot ".venv\Scripts\python.exe"),
    (Join-Path $repoRoot "venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $python = if ($pythonCommand.Source) { $pythonCommand.Source } else { $pythonCommand.Name }
}

$hadDatabaseUrl = Test-Path Env:DATABASE_URL
$previousDatabaseUrl = $env:DATABASE_URL
$hadAuditKey = Test-Path Env:AUDIT_HMAC_KEY
$previousAuditKey = $env:AUDIT_HMAC_KEY
$originalLocation = Get-Location
$db = $null
$key = $null
try {
    $db = Read-Host "Paste the EXTERNAL database URL of the live site" -AsSecureString
    $key = Read-Host "Paste the AUDIT_HMAC_KEY from the host" -AsSecureString
    $env:DATABASE_URL = [System.Net.NetworkCredential]::new("", $db).Password
    $env:AUDIT_HMAC_KEY = [System.Net.NetworkCredential]::new("", $key).Password
    if ([string]::IsNullOrWhiteSpace($env:DATABASE_URL)) {
        throw "The external database URL cannot be empty."
    }
    if ($env:AUDIT_HMAC_KEY.Length -lt 32) {
        throw "AUDIT_HMAC_KEY must be at least 32 characters."
    }

    Set-Location -LiteralPath $repoRoot
    $LASTEXITCODE = 0
    & $python manage.py verify_audit --anchors docs\anchors.log
    if ($LASTEXITCODE -ne 0) {
        throw "Audit verification failed with exit code $LASTEXITCODE."
    }
}
finally {
    if ($db) { $db.Dispose() }
    if ($key) { $key.Dispose() }
    if ($hadDatabaseUrl) {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
    else {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
    if ($hadAuditKey) {
        $env:AUDIT_HMAC_KEY = $previousAuditKey
    }
    else {
        Remove-Item Env:AUDIT_HMAC_KEY -ErrorAction SilentlyContinue
    }
    Set-Location -LiteralPath $originalLocation
}
