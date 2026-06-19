# Client-Ready Authentication, Database, And Repository Provisioning Plan

This document records the production direction for turning the current dashboard
into a professional client-ready GitHub extension-style product.

The user-facing goal is:

```text
Client signs in with GitHub
        ->
Client installs our GitHub App once
        ->
Client selects repositories
        ->
System auto-configures workflows, secrets, rulesets, and dashboard registration
        ->
Client sees only their own organization/user data
```

Confirmed product decisions:

```text
GitHub App owner model:
- Clients may be a GitHub organization or an individual GitHub user account.
- Treat each installed GitHub account as a tenant.

Client-facing app name:
- Arya tech Repo Quality Platform

Database direction:
- Use PostgreSQL for production from the beginning of serious deployment.
- Choose a provider that can scale with startup growth and later high usage.
```

The client should not manually:

- Choose GitHub App permissions.
- Generate GitHub App private keys.
- Configure webhook URLs or webhook secrets.
- Paste workflow YAML.
- Paste dashboard URLs into GitHub secrets.
- Create API keys by hand.
- Configure every repo manually.
- Understand ngrok.
- Share a database with other clients without strict isolation.

---

## 1. Current State

The current system already has:

- Repository intelligence modules:
  - `modules/metadata`
  - `modules/cicd`
  - `modules/deps`
- Autonomous pipeline modules:
  - `modules/quality`
  - `modules/security`
- Pipeline storage:
  - `pipeline_runs`
  - `pipeline_stages`
  - `quality_findings`
  - `monitored_repositories`
- Pipeline report API:
  - `POST /api/quality/report`
  - `POST /api/pipeline/report`
- Pipeline Monitor UI.
- Basic smoke-test automation scripts.

Import health check:

- Added `tests/test_imports.py`.
- This verifies all important `core` and `modules` Python packages import
  correctly.

Current test command:

```powershell
cd "C:\Users\kumar\OneDrive\Pictures\Laptop data\Arun Mokashi's Folder\codex\github-repo-intelligence"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected:

```text
5 tests OK
```

---

## 2. Product-Level Problem To Solve

For a real client product, the system must support multiple users and clients.

Example:

```text
User A -> Client Alpha -> only sees Alpha repos/runs/reports
User B -> Client Beta  -> only sees Beta repos/runs/reports
User C -> Client Alpha -> sees Alpha data only if invited/authorized
```

The system must guarantee:

- user-specific authentication
- tenant/client-specific data access
- repository ownership integrity
- no data leakage between clients
- auditable setup actions
- secure GitHub automation
- production-grade database migrations

---

## 3. Final Decision

Use:

```text
PostgreSQL + SQLAlchemy + Alembic + tenant_id isolation + optional PostgreSQL RLS
```

Do not create one physical database per user by default.

Use one production PostgreSQL database with tenant-aware tables.

Why:

- Easier migrations.
- Easier backups.
- Easier reporting.
- Easier connection pooling.
- Easier onboarding for many clients.
- Strong isolation can still be enforced using `tenant_id`, foreign keys,
  service-layer authorization, and PostgreSQL Row Level Security.

PostgreSQL Row Level Security is specifically designed to restrict which rows
are visible or modifiable based on policies. Reference:
<https://www.postgresql.org/docs/current/ddl-rowsecurity.html>

Optional enterprise mode:

- For very large or high-compliance clients, add tenant-dedicated database or
  tenant-dedicated schema later.
- That should be a premium/enterprise isolation mode, not the default.

---

## 4. Why PostgreSQL

Use PostgreSQL for production.

Reasons:

- Strong relational integrity.
- JSONB support for raw GitHub/workflow payloads.
- Good indexing for pipeline dashboards.
- Row Level Security support.
- Mature migration support through Alembic.
- Production-friendly deployment on AWS RDS, Supabase, Neon, Render,
  Railway, Azure Database for PostgreSQL, or self-managed Docker.

SQLite remains acceptable only for:

- local development
- smoke testing
- demos

Production should not use SQLite because:

- weak concurrency for multi-user SaaS
- harder operational backup/restore story
- no serious multi-tenant row security
- not ideal for concurrent GitHub webhook/report ingestion

---

## 5. Auth Model

Use GitHub as the primary identity provider.

Recommended approach:

```text
GitHub App for repo installation/provisioning
GitHub user authorization for login/session identity
```

Why GitHub App instead of only OAuth App:

- GitHub Apps are better for repository installation.
- GitHub Apps support installation on selected repositories.
- GitHub Apps support installation access tokens for repo automation.
- GitHub recommends considering GitHub Apps instead of OAuth Apps for many
  integrations.

GitHub App docs:

- Registering a GitHub App:
  <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app>
- Choosing GitHub App permissions:
  <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app>

OAuth/user authorization docs:

- <https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps>

Important:

The user must approve GitHub authorization. That approval cannot and should not
be bypassed.

---

## 6. Tenant Model

Use `tenant` to mean:

```text
one installed GitHub account
```

A user can belong to multiple tenants.

Example:

```text
Client Alpha GitHub organization -> one tenant
Client Beta personal GitHub account -> one tenant
User A can belong to one or many tenants through tenant_memberships
```

User table:

```text
users:
- id
- github_user_id
- github_login
- name
- email
- avatar_url
- created_at
- last_login_at
```

Tenant table:

```text
tenants:
- id
- name
- slug
- github_account_id
- github_account_login
- github_account_type
- plan
- created_at
```

Membership table:

```text
tenant_memberships:
- id
- tenant_id
- user_id
- role
- created_at
```

Roles:

```text
owner
admin
developer
viewer
```

Role meaning:

- `owner`: can manage billing/app installation.
- `admin`: can provision repositories and rulesets.
- `developer`: can view pipeline runs and reports.
- `viewer`: read-only access.

### Shared repository with many contributors

If one repository has many contributors, do not store one separate copy of the
same workflow/run data for every contributor.

Correct model:

```text
GitHub organization/account tenant
        ->
monitored repository
        ->
pipeline runs / stages / findings
        ->
all authorized tenant members can view the same authoritative records
```

Example:

```text
Repo: client-org/backend-api
Contributors: alice, bob, charan
Tenant: client-org
Stored once:
- monitored_repositories row for client-org/backend-api
- pipeline_runs rows for commits/workflows in that repo
- pipeline_stages rows for quality/compiler/AI/final stages
- quality_findings rows for the relevant quality stage
```

Alice, Bob, and Charan do not each get separate copies of the repo data just
because they contributed commits. They get access through `tenant_memberships`.

What is user-specific:

- login/session
- selected tenant
- role
- audit events for actions the user performed
- optional UI preferences later

What is repo/tenant-specific:

- workflow installation status
- GitHub Actions secrets setup status
- branch protection/ruleset setup status
- pipeline run history
- reports and findings
- repo-scoped API keys

Why this is correct:

- Everyone looking at the same client repo sees the same pipeline truth.
- A workflow run is generated by GitHub for a repository/commit, not for one
  dashboard user.
- It prevents duplicate rows and conflicting statuses.
- It keeps client data isolated by tenant, not fragmented by contributor.

If the same GitHub repository is intentionally installed under two different
tenants, the `tenant_id + repo` uniqueness rules keep those records isolated.
That is an edge case, not the normal collaborator flow.

---

## 7. GitHub Installation Model

Add:

```text
github_installations:
- id
- tenant_id
- installation_id
- account_id
- account_login
- account_type
- permissions_json
- repository_selection
- installed_at
- suspended_at
- raw_json
```

Why:

- A GitHub App installation is the bridge between our product and a client's
  selected repositories.
- Installation tokens are used server-side to automate workflow/secrets/ruleset
  setup.
- Users should never paste GitHub tokens into clone URLs.

GitHub App installation flow:

```text
Client clicks Install GitHub App
        ->
Client approves the permissions already configured by Arya Tech
        ->
GitHub redirects to our setup/callback URL and sends webhook events
        ->
Dashboard records installation_id
        ->
Dashboard auto-syncs selected repositories
        ->
Dashboard auto-registers selected repositories
        ->
Dashboard auto-installs workflow, secrets, and ruleset when production config is valid
        ->
Pipeline Monitor starts showing workflow reports
```

GitHub App registration supports callback/setup URLs and webhooks.

Important client/product rule:

- GitHub App permissions, private key generation, webhook URL, and webhook secret
  are one-time Arya Tech platform-owner setup tasks.
- Clients only install/authorize the GitHub App and select repositories.
- In production, `PUBLIC_BASE_URL` must be a public HTTPS dashboard URL. Local
  `127.0.0.1` works for browser testing only; GitHub Actions cannot post reports
  to a laptop localhost URL.
- For local development, ngrok/cloudflared is a temporary tunnel only. Clients
  should never need to know or run ngrok.

---

## 8. Repository Provisioning Model

Add or extend:

```text
monitored_repositories:
- id
- tenant_id
- installation_id
- full_name
- owner
- repo
- default_branch
- is_active
- setup_status
- workflow_installed_at
- secrets_configured_at
- ruleset_configured_at
- last_verified_at
- created_at
```

Setup statuses:

```text
pending
workflow_installed
secrets_configured
ruleset_configured
active
failed
needs_attention
```

Provisioning should do:

1. Generate repo-scoped dashboard API key.
2. Store only a hash of the key.
3. Set GitHub Actions secret `DASHBOARD_URL`.
4. Set GitHub Actions secret `DASHBOARD_API_KEY`.
5. Create/update `.github/workflows/company-quality-pipeline.yml`.
6. Configure ruleset/branch protection.
7. Register repo in `monitored_repositories`.
8. Run setup verification.

Automation controls:

```text
AUTO_SYNC_REPOS_ON_INSTALL=true
AUTO_PROVISION_ON_INSTALL=true in production after GitHub App credentials and public URL are ready
AUTO_PROVISION_ON_SYNC=true if the Sync Installed Repos button should also apply setup
PROVISIONING_DRY_RUN=false only when real GitHub mutations are intended
```

Safety rules:

- Real provisioning must not run with `PUBLIC_BASE_URL=http://127.0.0.1:...`
  unless explicitly overridden for a controlled local experiment.
- Provisioning responses shown to the browser must redact raw repo API keys.
- Ruleset creation must be idempotent: update the Arya ruleset if it already
  exists instead of creating duplicates.

GitHub Actions secrets API reference:

<https://docs.github.com/en/rest/actions/secrets?apiVersion=2022-11-28#create-or-update-a-repository-secret>

Repository contents API reference:

<https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28#create-or-update-file-contents>

Repository rulesets API reference:

<https://docs.github.com/en/rest/repos/rules?apiVersion=2022-11-28>

---

## 9. Pipeline Data Model Changes

Every client-owned table must include `tenant_id`.

Update or add:

```text
analysis_history.tenant_id
pipeline_runs.tenant_id
pipeline_stages.tenant_id
quality_findings.tenant_id
monitored_repositories.tenant_id
```

Recommended final pipeline tables:

```text
pipeline_runs:
- id
- tenant_id
- repository_id
- repo
- branch
- commit_sha
- pr_number
- workflow_run_id
- workflow_url
- overall_status
- started_at
- completed_at
- created_at
- raw_json
```

Unique key:

```text
tenant_id + repo + commit_sha + workflow_run_id
```

```text
pipeline_stages:
- id
- tenant_id
- pipeline_run_id
- stage_name
- status
- blocking
- started_at
- completed_at
- duration_ms
- summary_json
- artifacts_json
- raw_json
```

Unique key:

```text
pipeline_run_id + stage_name
```

```text
quality_findings:
- id
- tenant_id
- pipeline_stage_id
- scanner
- severity
- rule_id
- title
- message
- file_path
- line_number
- recommendation
- created_at
```

---

## 10. API Key Model

Add:

```text
repository_api_keys:
- id
- tenant_id
- repository_id
- key_prefix
- key_hash
- status
- created_at
- rotated_at
- revoked_at
```

Rules:

- Never store raw `DASHBOARD_API_KEY`.
- Store only a secure hash.
- Show only prefix in UI.
- Allow key rotation.
- Allow key revocation.
- Report ingestion validates key and repo ownership.

Why:

- One leaked repo API key should not compromise every client.
- A client can rotate one repo key without breaking all repos.
- Dashboard report ingestion becomes tenant-aware.

---

## 11. Authenticated API Rules

All dashboard UI APIs must require a user session.

Examples:

```text
GET /api/pipeline/runs
GET /api/pipeline/runs/{id}
GET /api/pipeline/latest/{owner}/{repo}
GET /api/history
POST /api/analyze/full
```

Rules:

- User must be logged in.
- User must select or belong to tenant.
- Query must be filtered by `tenant_id`.
- User role must allow the action.

Report ingestion APIs are different:

```text
POST /api/quality/report
POST /api/pipeline/report
```

These authenticate using repo-scoped bearer keys, not user sessions.

Rules:

- Validate bearer key hash.
- Resolve tenant/repository from key.
- Reject repo mismatch.
- Store rows with correct `tenant_id`.
- Redact secrets before storage.

---

## 12. Data Integrity Rules

Use:

- foreign keys
- unique constraints
- indexes
- transactional provisioning
- idempotency keys
- audit logs

Add:

```text
audit_events:
- id
- tenant_id
- user_id
- event_type
- target_type
- target_id
- ip_address
- user_agent
- created_at
- metadata_json
```

Audit events should record:

- login
- logout
- GitHub App installed
- repository configured
- workflow created/updated
- secrets configured
- ruleset configured
- repo API key rotated
- repo API key revoked
- report ingestion rejected

Why:

- Clients will ask what happened.
- Admins need traceability.
- Security events need records.

---

## 13. UI Direction For Later

The current UI feels too AI-generated and generic.

Do not fix this before auth/workflow/data are stable.

Later UI redesign should focus on:

- quiet enterprise SaaS style
- less decorative hero content
- setup/onboarding clarity
- dense operational dashboard
- professional tables and filters
- fewer generic gradients/cards
- clearer empty/loading/error states

This is intentionally deferred until:

- GitHub auth works
- tenants work
- PostgreSQL works
- repository provisioning works
- pipeline ingestion is tenant-safe

---

## 14. Implementation Phases

### Phase 1: Import Health And Architecture Decision

Status:

```text
Completed
```

Done:

- Added import smoke test.
- Verified current app modules import.
- Wrote auth/database plan.

### Phase 2: Multi-Tenant Database Foundation

Build:

- `tenants`
- `users`
- `tenant_memberships`
- `github_installations`
- `repository_api_keys`
- `audit_events`
- tenant-aware changes to existing tables
- Alembic migration

Decision:

- Local dev can still use SQLite.
- Production target is PostgreSQL.

### Phase 3: GitHub Login

Build:

- GitHub login route.
- OAuth state protection.
- Callback route.
- signed session cookie.
- current user API.
- logout.

Current implementation status:

- Added signed-cookie session middleware.
- Added GitHub OAuth login/callback/logout/status routes.
- Added tenant selection route.
- Added local-dev fallback tenant when `REQUIRE_LOGIN=false`.

### Phase 4: GitHub App Installation

Build:

- install/start route.
- setup/callback route.
- webhook endpoint.
- HMAC verification for GitHub webhooks.
- installation storage.

Current implementation status:

- Added install redirect route.
- Added setup callback route.
- Added webhook endpoint with `X-Hub-Signature-256` verification.
- Added installation and repository sync helpers.
- Added install-time automation so setup callbacks and webhooks can sync
  selected repositories without the user pressing a separate dashboard button.

### Phase 5: Repository Provisioning

Build:

- workflow installer.
- repo API key generator.
- GitHub Actions secret installer.
- ruleset/branch protection manager.
- setup status checker.

Current implementation status:

- Added caller workflow renderer.
- Added repo-scoped API key generation/rotation.
- Added provisioning service for workflow file, GitHub Actions secrets, and
  repository ruleset setup.
- Added dry-run mode so local development does not mutate real client repos.
- Added setup status API and basic dashboard tab.
- Added optional auto-provisioning after GitHub App install/sync through:
  - `AUTO_SYNC_REPOS_ON_INSTALL`
  - `AUTO_PROVISION_ON_INSTALL`
  - `AUTO_PROVISION_ON_SYNC`
- Added safety guard so real provisioning is blocked when `PUBLIC_BASE_URL` is
  localhost, because GitHub Actions cannot report to a laptop-only URL.
- Added browser-safe provisioning responses that redact raw repo API keys.
- Added idempotent ruleset setup so repeated provisioning updates the Arya
  ruleset instead of creating duplicates.

### Phase 6: Tenant-Safe Pipeline Ingestion

Build:

- report ingestion by repo API key.
- repo/key ownership validation.
- tenant_id propagation.
- tenant-aware Pipeline Monitor.

Current implementation status:

- Report ingestion can validate repo-scoped bearer keys.
- Global `DASHBOARD_API_KEY` remains only for local smoke testing and backward
  compatibility.
- Pipeline Monitor queries use the selected session tenant.

### Phase 7: Production Database Hardening

Build:

- PostgreSQL deployment config.
- optional Row Level Security.
- backup/restore docs.
- migration runbook.

### Phase 8: UI Redesign

Build later:

- professional SaaS redesign.
- onboarding wizard UI.
- client repository setup page.
- less generic dashboard visuals.

---

## 15. What You Need To Provide

You do not need to know database/auth internals, but you will need to provide
product ownership decisions.

### GitHub App information

Arya Tech must create/register the GitHub App once as the platform owner and
provide these backend environment values:

```text
GITHUB_APP_ID
GITHUB_APP_CLIENT_ID
GITHUB_APP_CLIENT_SECRET
GITHUB_APP_PRIVATE_KEY
GITHUB_APP_WEBHOOK_SECRET
GITHUB_APP_NAME
```

Arya Tech also decides:

```text
App owner: personal account or organization?
Can clients install it on any account, or only your org?
Final app name shown to clients?
```

Current decision:

```text
Final app name: Arya tech Repo Quality Platform
Client install target: GitHub organization or individual user account
Tenant definition: the installed GitHub account
```

### Deployment URL

You need a real production URL before enabling real automatic provisioning:

```text
https://quality.yourcompany.com
```

This replaces ngrok.

Clients do not need ngrok. Ngrok/cloudflared are only local-development tunnels
for the platform team while the dashboard is still running on a laptop.

### Database

For production, prepare PostgreSQL.

Options:

- Supabase
- Neon
- Render PostgreSQL
- Railway PostgreSQL
- AWS RDS PostgreSQL
- Docker-managed PostgreSQL

Recommendation for this startup path:

```text
Early hosted production: Neon or Supabase
Simple deployment pairing: Render PostgreSQL or Railway PostgreSQL
Large-scale mature production: AWS RDS PostgreSQL or equivalent managed cloud Postgres
```

Reason:

- Start with a managed provider to avoid database operations overhead.
- Keep standard PostgreSQL so migration to AWS RDS or another enterprise
  provider is possible later.
- Avoid provider-specific database features unless necessary.

Required production variable:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
```

### Client model

You need to decide:

```text
Is one GitHub organization equal to one tenant?
Can one user belong to multiple tenants?
Who is allowed to invite users?
Do you need billing/plans now, or later?
```

Recommended initial answers:

```text
GitHub organization/account = tenant
Users can belong to multiple tenants
owner/admin can invite users
billing/plans later
```

---

## 16. Final Conclusion

Use this production direction:

```text
GitHub App + GitHub login + PostgreSQL + tenant_id isolation + repo-scoped API keys
```

Do not build a per-user SQLite-style system.

Do not let all users share unfiltered tables.

Do not make clients manually configure secrets/workflows/rulesets.

Build the product as a GitHub extension-style SaaS:

```text
Sign in with GitHub
        ->
Install/authorize GitHub App
        ->
Select repositories
        ->
Backend syncs repositories
        ->
Backend provisions workflow, secrets, and ruleset
        ->
Pipeline runs automatically
```
