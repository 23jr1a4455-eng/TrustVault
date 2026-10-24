# Saves today's audit "anchor" OUTSIDE the app, in Git history.
# An anchor is the end of the audit chain at one moment. If anyone later rewrites the
# database, even someone holding the secret key, the saved anchor will not match.
#
# Run from the repo root with the virtual environment active:   .\scripts\anchor.ps1
$ErrorActionPreference = "Stop"
$secure = Read-Host "Paste the EXTERNAL database URL of the live site" -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new("", $secure).Password
try {
    $line = python manage.py anchor
    if (-not $line) { throw "No anchor line was produced." }
    New-Item -ItemType Directory -Force docs | Out-Null
    Add-Content -Path docs\anchors.log -Value $line -Encoding ascii
    Write-Host "Saved: $line"
    git add docs\anchors.log
    git commit -m "docs: audit anchor $(Get-Date -Format yyyy-MM-dd)"
    git push
}
finally {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
}
