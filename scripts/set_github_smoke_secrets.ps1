param(
    [Parameter(Mandatory = $true)]
    [string]$Repo,

    [Parameter(Mandatory = $true)]
    [string]$DashboardUrl,

    [string]$ApiKey = "dev-test-key"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "GitHub CLI is not installed or not on PATH."
    Write-Host "Install it from https://cli.github.com/ and run: gh auth login"
    throw "gh command not found"
}

Write-Host "Setting GitHub Actions secrets for $Repo..."
gh secret set DASHBOARD_URL --body $DashboardUrl --repo $Repo
gh secret set DASHBOARD_API_KEY --body $ApiKey --repo $Repo

Write-Host ""
Write-Host "Secrets configured:"
Write-Host "  DASHBOARD_URL=$DashboardUrl"
Write-Host "  DASHBOARD_API_KEY=<hidden>"
Write-Host ""
Write-Host "Ruleset still needs repository admin permission."
Write-Host "After the first workflow run exists, configure required status check:"
Write-Host "  Basic Pipeline Smoke Test / quality-gate"
