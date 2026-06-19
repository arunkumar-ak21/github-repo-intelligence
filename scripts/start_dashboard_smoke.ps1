param(
    [string]$ApiKey = "dev-test-key",
    [int]$Port = 8012
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:DASHBOARD_API_KEY = $ApiKey
$env:ALLOW_UNREGISTERED_REPOS = "true"

Write-Host "Starting github-repo-intelligence dashboard in smoke-test mode..."
Write-Host "URL: http://127.0.0.1:$Port/#dashboard"
Write-Host "DASHBOARD_API_KEY: $ApiKey"
Write-Host "ALLOW_UNREGISTERED_REPOS: true"
Write-Host ""

& ".\.venv\Scripts\python.exe" server.py --host 127.0.0.1 --port $Port
