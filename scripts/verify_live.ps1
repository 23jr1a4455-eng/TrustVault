# Checks the LIVE audit chain and every saved anchor.
# Needs the external database URL and the AUDIT_HMAC_KEY from the host's settings.
#
# Run from the repo root with the virtual environment active:   .\scripts\verify_live.ps1
$ErrorActionPreference = "Stop"
$db = Read-Host "Paste the EXTERNAL database URL of the live site" -AsSecureString
$key = Read-Host "Paste the AUDIT_HMAC_KEY from the host" -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new("", $db).Password
$env:AUDIT_HMAC_KEY = [System.Net.NetworkCredential]::new("", $key).Password
try {
    python manage.py verify_audit --anchors docs\anchors.log
}
finally {
    Remove-Item Env:DATABASE_URL, Env:AUDIT_HMAC_KEY -ErrorAction SilentlyContinue
}
