
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $repoRoot ".venv\Scripts\python.exe"),
    (Join-Path $repoRoot "venv\Scripts\python.exe")
)
$python = $pythonCandidates |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1

if (-not $python) {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $python = if ($pythonCommand.Source) {
        $pythonCommand.Source
    } else {
        $pythonCommand.Name
    }
}

$hadDatabaseUrl = Test-Path Env:DATABASE_URL
$previousDatabaseUrl = $env:DATABASE_URL
$hadAuditKey = Test-Path Env:AUDIT_HMAC_KEY
$previousAuditKey = $env:AUDIT_HMAC_KEY
$originalLocation = Get-Location
$db = $null
$key = $null

try {
    Set-Location -LiteralPath $repoRoot

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

    # Verify the current live chain against all previously saved anchors.
       # Verify existing anchors only when the file exists.
    if (Test-Path -LiteralPath "docs\anchors.log") {
        $LASTEXITCODE = 0
        & $python manage.py verify_audit --anchors docs\anchors.log
        if ($LASTEXITCODE -ne 0) {
            throw "Live audit verification failed. No new anchor will be created."
        }
    } else {
        Write-Host "No historical anchor log exists; this will be the first anchor."
    }

    # Always verify the live chain even when there are no saved anchors.
    $LASTEXITCODE = 0
    & $python manage.py verify_audit
    if ($LASTEXITCODE -ne 0) {
        throw "Live audit chain verification failed. No new anchor will be created."
    }

    # Generate a new anchor only after successful verification.
    $LASTEXITCODE = 0
    $line = & $python manage.py anchor
    if ($LASTEXITCODE -ne 0) {
        throw "Anchor command failed."
    }
    if (-not $line -or $line.Count -ne 1) {
        throw "Expected exactly one anchor line; nothing was saved."
    }

    # Prevent accidental duplicate commits when the anchor is unchanged.
    New-Item -ItemType Directory -Force docs | Out-Null
    Add-Content -Path docs\anchors.log -Value $line -Encoding ascii

    git add -- docs\anchors.log
    if ($LASTEXITCODE -ne 0) {
        throw "git add failed."
    }

    git commit -m "docs: audit anchor $(Get-Date -Format yyyy-MM-dd)"
    if ($LASTEXITCODE -ne 0) {
        throw "git commit failed. Inspect Git status before retrying."
    }

    git push
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed. The anchor is committed locally but not confirmed in the remote repository."
    }

    Write-Host "Anchor committed and pushed successfully."
}
finally {
    if ($db) { $db.Dispose() }
    if ($key) { $key.Dispose() }

    if ($hadDatabaseUrl) {
        $env:DATABASE_URL = $previousDatabaseUrl
    } else {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }

    if ($hadAuditKey) {
        $env:AUDIT_HMAC_KEY = $previousAuditKey
    } else {
        Remove-Item Env:AUDIT_HMAC_KEY -ErrorAction SilentlyContinue
    }

    Set-Location -LiteralPath $originalLocation
}
