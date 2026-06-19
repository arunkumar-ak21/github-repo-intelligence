# PostgreSQL Deployment Runbook

Use PostgreSQL for client deployments.

SQLite is acceptable only for local development, smoke tests, and short demos.

## Required Environment

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
REQUIRE_LOGIN=true
SESSION_SECRET=<long random secret>
SESSION_COOKIE_SECURE=true
PUBLIC_BASE_URL=https://your-production-domain.example
GITHUB_APP_CLIENT_ID=<from GitHub App>
GITHUB_APP_CLIENT_SECRET=<from GitHub App>
GITHUB_APP_ID=<from GitHub App>
GITHUB_APP_PRIVATE_KEY=<private key or use path>
GITHUB_APP_WEBHOOK_SECRET=<webhook secret>
PROVISIONING_DRY_RUN=false
AUTO_SYNC_REPOS_ON_INSTALL=true
AUTO_PROVISION_ON_INSTALL=true
AUTO_PROVISION_ON_SYNC=true
AUTO_REPROVISION_ACTIVE_REPOS=false
ALLOW_LOCAL_DASHBOARD_URL_FOR_PROVISIONING=false
```

These GitHub App values are platform-owner secrets for Arya Tech. They are not
client setup steps. A client should only sign in, install/authorize the GitHub
App, and select repositories.

## Recommended Providers

Early hosted production:

- Neon
- Supabase
- Render PostgreSQL
- Railway PostgreSQL

Mature large-scale production:

- AWS RDS PostgreSQL
- Azure Database for PostgreSQL
- Google Cloud SQL for PostgreSQL

## Migration Policy

Use Alembic for production schema changes.

Do not rely on `Base.metadata.create_all()` to alter existing production
schemas. It can create missing tables for a fresh local database, but it does
not safely version or review schema changes.

Required deployment sequence:

```powershell
alembic upgrade head
python server.py --host 0.0.0.0 --port 8000
```

## Tenant Isolation

Every client-owned table must be filtered by `tenant_id`.

The first production release should enforce isolation in the service layer.
Later, add PostgreSQL Row Level Security for defense in depth.

## Backup And Recovery

Minimum production policy:

- automated daily database backups
- point-in-time recovery if the provider supports it
- backup restore test before onboarding important clients
- separate production and staging databases

## Secrets

Do not commit production `.env` files.

Store deployment secrets in:

- Render/Railway environment settings
- AWS Secrets Manager
- Doppler
- 1Password Secrets Automation
- another startup-approved secret manager

GitHub Actions repository secrets should be installed by the platform
provisioning flow, not manually by clients.

## GitHub App Owner Setup Versus Client Setup

Arya Tech configures these once for the GitHub App:

- permissions requested by the app
- private key
- webhook URL and webhook secret
- callback/setup URL
- production dashboard URL

Client setup is intentionally smaller:

1. Sign in with GitHub.
2. Install/authorize the GitHub App.
3. Select repositories.

After that, the backend syncs selected repositories and provisions workflow,
repository secrets, and rulesets automatically.
