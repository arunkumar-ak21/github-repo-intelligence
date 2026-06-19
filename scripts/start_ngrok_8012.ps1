param(
    [int]$Port = 8012
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "ngrok is not installed or not on PATH."
    Write-Host "Install it with:"
    Write-Host "  winget install Ngrok.Ngrok"
    Write-Host ""
    throw "ngrok command not found"
}

Write-Host "Starting ngrok tunnel for local dashboard port $Port..."
Write-Host "Copy the HTTPS Forwarding URL and use it as DASHBOARD_URL in GitHub Secrets."
Write-Host "Example: https://abc123.ngrok-free.app"
Write-Host ""

ngrok http $Port
