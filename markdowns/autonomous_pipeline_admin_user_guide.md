# Autonomous Pipeline Admin And User Guide

This guide is the handoff runbook for the autonomous Repo Quality Platform flow.
It covers the production setup required by the Arya Tech application admin and
the short onboarding flow required from a client user.

The target production behavior is:

```text
Client signs in with GitHub
        |
Client installs the GitHub App and selects repositories
        |
Dashboard records the installation
        |
Backend syncs selected repositories
        |
Backend installs workflow, repository secrets, and branch ruleset
        |
GitHub Actions runs on push and pull request
        |
Quality reports are posted to the dashboard
        |
Pipeline Monitor shows the run
        |
GitHub required checks block bad code from main/develop
```

## Current Implementation Status

Implemented backend pieces:

- GitHub OAuth login routes.
- Tenant-aware user/session model.
- GitHub App install callback and webhook receiver.
- Webhook HMAC verification through `X-Hub-Signature-256`.
- Installed repository sync.
- Monitored repository records per tenant.
- Repo-scoped API keys.
- Automatic workflow installer.
- Automatic GitHub Actions secret installer.
- Automatic GitHub repository ruleset installer.
- Live setup verification endpoint.
- Quality report ingestion through `POST /api/quality/report`.
- Generic pipeline stage ingestion through `POST /api/pipeline/report`.
- Pipeline run history through `GET /api/pipeline/runs`.
- Pipeline detail through `GET /api/pipeline/runs/{id}`.
- Latest run lookup through `GET /api/pipeline/latest/{owner}/{repo}`.
- Duplicate run handling through repo + commit SHA + workflow run ID.
- Duplicate stage handling through pipeline run + stage name.
- Secret redaction before database storage.
- Pipeline Monitor data model for quality, compiler, AI remediation, and final verification stages.

Current handoff boundary:

- `quality-gate` is implemented as the first enforced stage.
- `compiler-check` exists as the required GitHub check name and workflow placeholder.
- Satyam should replace the compiler placeholder with the real compiler module.
- AI remediation and final verification remain planned after the compiler module is connected.

## Admin Responsibilities

The application admin is Arya Tech or whoever operates the deployed platform.
Clients should not create GitHub Apps, generate private keys, configure webhook
URLs, add workflow files, add GitHub Actions secrets, or configure branch rules
manually.

The admin configures these once for the deployed platform.

## Required Infrastructure

Use production infrastructure before client onboarding:

- Public HTTPS dashboard URL.
- PostgreSQL database.
- GitHub OAuth App or GitHub App OAuth credentials.
- GitHub App with repository permissions.
- Secure secret storage for environment variables and GitHub private key.

Recommended database for production:

- Neon PostgreSQL, Supabase PostgreSQL, Render PostgreSQL, Railway PostgreSQL, AWS RDS, or another managed PostgreSQL provider.

Do not use SQLite for real multi-client production.

## Required GitHub App Settings

Create one platform-owned GitHub App. Clients install this app into their
personal account or organization.

Recommended app name:

```text
Arya tech Repo Quality Platform
```

Homepage URL:

```text
https://YOUR-PRODUCTION-DOMAIN
```

User authorization callback URL:

```text
https://YOUR-PRODUCTION-DOMAIN/api/auth/callback
```

Setup URL:

```text
https://YOUR-PRODUCTION-DOMAIN/api/github-app/setup-callback
```

Webhook URL:

```text
https://YOUR-PRODUCTION-DOMAIN/api/github-app/webhook
```

Webhook secret:

```text
Use a long random value and store the same value in GITHUB_APP_WEBHOOK_SECRET.
```

Repository permissions:

```text
Metadata: Read-only
Contents: Read and write
Workflows: Read and write
Secrets: Read and write
Administration: Read and write
Actions: Read and write
Checks: Read and write
Pull requests: Read and write
```

Webhook events:

```text
installation
installation_repositories
```

Repository access:

```text
Client chooses all repositories or selected repositories during install.
```

Private key:

```text
Generate one GitHub App private key.
Store it on the deployed backend as GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH.
Do not ask clients to generate private keys.
```

## Required Environment Variables

Set these on the deployed backend.

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME

PUBLIC_BASE_URL=https://YOUR-PRODUCTION-DOMAIN
ALLOWED_ORIGINS=https://YOUR-PRODUCTION-DOMAIN

REQUIRE_LOGIN=true
SESSION_SECRET=replace-with-long-random-secret
SESSION_COOKIE_SECURE=true

GITHUB_CLIENT_ID=your-oauth-client-id
GITHUB_CLIENT_SECRET=your-oauth-client-secret

GITHUB_APP_ID=your-github-app-id
GITHUB_APP_SLUG=arya-tech-repo-quality-platform
GITHUB_APP_INSTALL_URL=https://github.com/apps/arya-tech-repo-quality-platform/installations/new
GITHUB_APP_PRIVATE_KEY_PATH=/secure/path/to/github-app-private-key.pem
GITHUB_APP_WEBHOOK_SECRET=replace-with-long-random-webhook-secret

PROVISIONING_DRY_RUN=false
ALLOW_LOCAL_DASHBOARD_URL_FOR_PROVISIONING=false

AUTO_SYNC_REPOS_ON_INSTALL=true
AUTO_PROVISION_ON_INSTALL=true
AUTO_PROVISION_ON_SYNC=true
AUTO_REPROVISION_ACTIVE_REPOS=false

ALLOW_UNREGISTERED_REPOS=false
MAX_REPORT_PAYLOAD_BYTES=5242880
MAX_FINDINGS_PER_REPORT=500
REPORT_RATE_LIMIT_PER_MINUTE=120

QUALITY_WORKFLOW_MODE=standalone
QUALITY_CALLER_WORKFLOW_PATH=.github/workflows/company-quality-pipeline.yml
```

For long-term production with a central workflow, switch to:

```env
QUALITY_WORKFLOW_MODE=reusable
QUALITY_REUSABLE_WORKFLOW_REF=arya-tech/repo-quality-platform/.github/workflows/reusable-quality-gate.yml@main
```

Use `standalone` only until the central reusable workflow repository is ready.

## What Happens During Client Onboarding

Client-visible steps should be minimal:

1. Client opens the dashboard.
2. Client clicks sign in with GitHub.
3. Client clicks install GitHub App.
4. GitHub asks them to select account and repositories.
5. Client approves.
6. Dashboard syncs and provisions selected repositories.
7. Repo Setup shows workflow, secrets, and ruleset status.
8. Pipeline Monitor starts showing results after the first push or pull request.

The client should not manually add:

- GitHub Actions workflow files.
- GitHub Actions secrets.
- Branch protection or repository rulesets.
- Dashboard API keys.
- Webhook URLs.
- GitHub App permissions.

## What The Backend Provisions

For every selected repository, the backend provisions:

1. Workflow file:

```text
.github/workflows/company-quality-pipeline.yml
```

2. GitHub Actions secrets:

```text
DASHBOARD_URL
DASHBOARD_API_KEY
```

`DASHBOARD_API_KEY` is repo-scoped. It is generated by the backend, stored hashed
in the dashboard database, and installed into GitHub as an encrypted Actions
secret. The raw value is not shown back to the browser.

3. Repository ruleset:

```text
Arya Quality Required Checks
```

Ruleset behavior:

- Requires pull request before merge.
- Requires status checks to pass.
- Requires these check contexts:
  - `quality-gate`
  - `compiler-check`
- Applies to the default branch and `develop`.

Important enforcement rule:

- GitHub Actions cannot block the first push to a feature branch.
- It blocks merge into protected branches through required status checks.

## Setup Verification

The backend exposes live setup verification:

```text
POST /api/setup/repositories/{repo_id}/verify
```

This endpoint checks GitHub directly and updates the repository setup status.

It verifies:

- Workflow file exists at `QUALITY_CALLER_WORKFLOW_PATH`.
- Required GitHub Actions secret names exist:
  - `DASHBOARD_URL`
  - `DASHBOARD_API_KEY`
- Required ruleset exists:
  - `Arya Quality Required Checks`
- Required status checks exist in the ruleset:
  - `quality-gate`
  - `compiler-check`
- Repository has an active dashboard API key.

It does not read secret values. GitHub does not expose secret values, and the
platform should never try to display them.

Expected success response shape:

```json
{
  "status": "verified",
  "repo": {
    "full_name": "owner/repo",
    "setup_status": "active",
    "workflow_installed_at": "2026-06-19T10:00:00Z",
    "secrets_configured_at": "2026-06-19T10:00:00Z",
    "ruleset_configured_at": "2026-06-19T10:00:00Z",
    "last_verified_at": "2026-06-19T10:00:00Z"
  },
  "verification": {
    "ready": true,
    "missing": []
  }
}
```

If verification is not ready, `missing` explains what still needs attention.

## Workflow Pull Request Fallback

Some repositories already have rules that block direct writes to workflow files.
When GitHub rejects direct workflow installation with repository rule violations,
the backend opens a setup pull request instead of failing silently.

In that case:

- Workflow status remains pending until the setup PR is merged.
- Secrets and ruleset can still be configured automatically if permissions allow.
- Client or repo maintainer must merge the setup PR once.
- After merge, run setup verification again.

This is the only acceptable client-side manual step caused by pre-existing repo
rules. It happens because GitHub itself blocks direct workflow writes.

## Pipeline Monitor Behavior

Pipeline Monitor reads from:

```text
GET /api/pipeline/runs
GET /api/pipeline/runs/{id}
GET /api/pipeline/latest/{owner}/{repo}
```

Each run stores:

- Repo.
- Branch.
- Commit SHA.
- PR number.
- Workflow run ID.
- Workflow URL.
- Overall status.
- Stage summaries.
- Stage artifacts.
- Stage findings.

Stages currently supported:

```text
quality_gate
compiler_check
ai_remediation
final_verification
repo_intelligence
```

Statuses currently supported:

```text
pending
running
passed
failed
blocked
error
skipped
needs_human
```

Overall run status rules:

- Failed, blocked, error, or needs_human stage makes the run terminal.
- `compiler_check.passed` marks the run completed.
- `final_verification.passed` marks the run completed.
- `quality_gate.passed` alone keeps the run running until compiler result arrives.

## Security Rules

Production report ingestion is not public or anonymous.

Required controls:

- `Authorization: Bearer <repo-scoped-dashboard-api-key>`.
- Repo allowlist through `monitored_repositories`.
- Payload size limit.
- Rate limiting.
- Duplicate handling.
- Secret redaction before database storage.
- Webhook HMAC verification.

Do not set this in production:

```env
ALLOW_UNREGISTERED_REPOS=true
```

That is demo-only.

## Admin Verification Checklist

Before onboarding a real client, confirm:

- Dashboard is deployed on public HTTPS.
- `PUBLIC_BASE_URL` is not localhost.
- PostgreSQL is configured.
- GitHub OAuth login works.
- GitHub App install URL opens correctly.
- GitHub App setup callback is configured.
- GitHub App webhook URL is configured.
- Webhook secret matches backend env.
- GitHub App private key is configured on backend.
- `PROVISIONING_DRY_RUN=false`.
- `AUTO_SYNC_REPOS_ON_INSTALL=true`.
- `AUTO_PROVISION_ON_INSTALL=true`.
- `AUTO_PROVISION_ON_SYNC=true`.
- `ALLOW_UNREGISTERED_REPOS=false`.
- A test repo can be selected during install.
- Repo Setup syncs the repo.
- Provisioning installs workflow or opens setup PR.
- Provisioning creates `DASHBOARD_URL`.
- Provisioning creates `DASHBOARD_API_KEY`.
- Provisioning creates required ruleset.
- `POST /api/setup/repositories/{repo_id}/verify` returns ready.
- Pull request merge is blocked when `quality-gate` or `compiler-check` fails.

## User Guide

For a client user:

1. Open the Arya Tech Repo Quality Platform dashboard.
2. Click sign in with GitHub.
3. Click install GitHub App.
4. Choose your personal account or organization.
5. Select the repositories you want monitored.
6. Approve the installation.
7. Return to the dashboard.
8. Open Repo Setup.
9. Click sync installed repos if the page has not synced automatically.
10. Wait for status to become active.
11. If the dashboard shows a setup pull request, open and merge that PR.
12. Create or update a pull request in the monitored repository.
13. Watch the GitHub Actions run.
14. Open Pipeline Monitor to view the stored report.

Expected client result:

- Good code can merge after required checks pass.
- Bad code cannot merge into protected branches.
- Reports are visible in Pipeline Monitor.
- Developers do not need local hooks for enforcement.

## Known Handoff Notes

- Current production-ready onboarding flow depends on a deployed public HTTPS URL.
- Local `127.0.0.1` works for development but not for GitHub Actions callbacks.
- `compiler-check` is currently a placeholder check name and job.
- Satyam should replace the compiler placeholder with real compiler execution and report submission.
- Long-term production should move workflow logic to the central reusable workflow and keep only small caller workflows in client repositories.
