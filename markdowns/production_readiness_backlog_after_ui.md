# Production Readiness Backlog After UI Upgrade

This document records what is already working, what is temporary, and what must
be upgraded after the major professional UI redesign.

The current system is good enough to move into UI work. The remaining items are
production hardening and replacing prototype-stage shortcuts.

---

## Current Working State

The autonomous repository onboarding flow is working.

Implemented and verified:

- GitHub login works for new users.
- Public GitHub App installation works.
- Users can install/authorize the GitHub App and select repositories.
- Dashboard syncs selected repositories.
- Each synced repository is registered under the correct tenant.
- Repo-scoped dashboard API keys are generated.
- GitHub Actions workflow file is installed automatically.
- GitHub Actions secrets are installed automatically:
  - `DASHBOARD_URL`
  - `DASHBOARD_API_KEY`
- Repository ruleset/branch protection is installed automatically.
- Pipeline report ingestion API exists:
  - `POST /api/quality/report`
  - `POST /api/pipeline/report`
- Pipeline history tables exist separately from repo intelligence history.
- Tenant/user foundation exists.
- Pipeline Monitor UI exists.
- Local automated tests pass.

Repos verified during testing:

```text
arunkumar-ak21/Sarthi-Dashboard
bardaiak03-dev/Student-portal
```

Both repos had:

```text
.github/workflows/company-quality-pipeline.yml
DASHBOARD_URL secret
DASHBOARD_API_KEY secret
Arya Quality Required Checks ruleset
local setup_status = active
```

---

## Temporary Choices

These are intentional temporary choices made so the system could work now.

### 1. Standalone Workflow Mode

Current mode:

```text
QUALITY_WORKFLOW_MODE=standalone
```

Meaning:

- The platform writes a full workflow file into every monitored repository.
- Each repo gets its own `.github/workflows/company-quality-pipeline.yml`.
- This is good for fast testing and proving automatic provisioning works.

Why it is temporary:

- Updating workflow logic later means updating every monitored repository.
- Different repos can drift if some workflow files are outdated.
- This is less clean for a SaaS product with many clients.

Production target:

```text
QUALITY_WORKFLOW_MODE=reusable
```

Each client repo should contain only a small caller workflow, while the real
pipeline lives in one central platform repository.

Example client repo workflow:

```yaml
name: Company Quality Pipeline

on:
  push:
    branches: [main, develop, "feature/**"]
  pull_request:
    branches: [main, develop]

jobs:
  quality:
    uses: arya-tech/repo-quality-platform/.github/workflows/reusable-quality-gate.yml@main
    secrets: inherit
```

Central production workflow location:

```text
arya-tech/repo-quality-platform/.github/workflows/reusable-quality-gate.yml
```

---

### 2. Local Dashboard URL

Current local testing value:

```text
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

Why it is temporary:

- GitHub Actions runs on GitHub-hosted runners.
- GitHub-hosted runners cannot POST reports to a laptop localhost URL.
- Workflow/secrets/ruleset setup can be installed, but live report delivery to
  the dashboard needs a public HTTPS URL.

Production target:

```text
PUBLIC_BASE_URL=https://your-production-domain.example
```

Local testing alternative:

```text
PUBLIC_BASE_URL=https://your-ngrok-or-cloudflared-url
```

Ngrok/cloudflared should only be used by the platform team for development. A
client should never need to know or run it.

---

### 3. SQLite Local Database

Current local mode:

```text
DATABASE_URL=sqlite:///data/app.db
```

Why it is temporary:

- SQLite is fine for local development.
- It is not ideal for multiple users, concurrent report ingestion, webhook
  bursts, audit history, and production data integrity.

Production target:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
```

Recommended providers:

- Neon
- Supabase
- Render PostgreSQL
- Railway PostgreSQL
- Later: AWS RDS PostgreSQL or equivalent managed PostgreSQL.

---

### 4. Placeholder Compiler Stage

Current state:

- `compiler-check` exists in the workflow.
- It currently contains a placeholder command.

Production target:

- Add the real compiler/error-check module.
- The stage should emit a normalized pipeline report.
- Compiler failures should trigger AI remediation only when the quality gate
  already passed.

Expected stage name:

```text
compiler_check
```

---

### 5. Placeholder AI Remediation Stage

Current state:

- AI remediation stage exists conceptually and in workflow structure.
- Real patch generation is not implemented yet.

Production target:

- Add the real AI remediation module.
- It should consume safe compiler errors and safe file context only.
- It must never receive raw secret values.
- It must not auto-merge.
- It should generate a patch/report first.
- It may optionally create a separate auto-fix branch or PR.
- It must stop after the configured max attempts.

Required config:

```text
MAX_AI_ATTEMPTS=2
```

Expected final fallback:

```text
needs_human
```

---

### 6. Code-Quality Package Source

Current standalone workflow attempts:

```text
pip install cq-pipeline[all]
```

Why this may be temporary:

- The package must exist in an installable location for GitHub Actions.
- Local sibling-folder imports will not work inside client repositories.

Production target:

Choose one stable package strategy:

1. Publish `Code-Quality` as an internal Python package.
2. Move the package into a monorepo under `packages/cqpipeline`.
3. Install from a private GitHub package source with a GitHub App/token strategy.

Do not use `sys.path.insert(...)` hacks in production.

---

### 7. Local Secrets And Credentials

Current local `.env` contains live development credentials.

Before production:

- Rotate the GitHub Personal Access Token used during development.
- Rotate the GitHub App client secret that was shared during testing.
- Store production secrets in deployment environment variables or a secret
  manager.
- Never commit `.env`.

Recommended production secret storage:

- Render/Railway environment settings.
- AWS Secrets Manager.
- Doppler.
- 1Password Secrets Automation.
- Another approved startup secret manager.

---

## Required Production Upgrades

Complete these after the professional UI upgrade.

### 1. Deploy The Dashboard

Goal:

```text
https://quality.aryatech.example
```

Tasks:

- Deploy FastAPI app.
- Serve static frontend.
- Set `PUBLIC_BASE_URL` to the production HTTPS URL.
- Set secure cookie config:

```text
REQUIRE_LOGIN=true
SESSION_COOKIE_SECURE=true
```

---

### 2. Move To PostgreSQL

Tasks:

- Provision PostgreSQL.
- Set `DATABASE_URL`.
- Run Alembic migrations.
- Confirm tenant isolation works.
- Add database backups.

Command:

```powershell
alembic upgrade head
```

---

### 3. Switch To Reusable Workflow Mode

Tasks:

- Create/choose central platform repository.
- Add `.github/workflows/reusable-quality-gate.yml`.
- Confirm it uses:

```yaml
on:
  workflow_call:
```

- Set:

```text
QUALITY_WORKFLOW_MODE=reusable
QUALITY_REUSABLE_WORKFLOW_REF=arya-tech/repo-quality-platform/.github/workflows/reusable-quality-gate.yml@main
```

- Re-provision monitored repos so their workflow files become small callers.

---

### 4. Connect Real Code-Quality Scanner

Tasks:

- Make `cq-pipeline` installable in GitHub Actions.
- Confirm all standalone scanner functions/modules are available.
- Confirm scanner error policy fails closed for:
  - secrets
  - SAST
  - dependencies
- Confirm skipped critical scanners do not produce a PASS.
- Confirm raw secrets are redacted before dashboard storage or AI usage.

---

### 5. Add Real Compiler Stage

Tasks:

- Add compiler stage implementation.
- Normalize compiler output into the common stage contract.
- Send compiler report to dashboard.
- Make `compiler-check` a required status check.

---

### 6. Add Real AI Remediation Stage

Tasks:

- Add AI remediation module.
- Enforce `MAX_AI_ATTEMPTS=2`.
- Generate patch/report first.
- Optionally create auto-fix branch/PR.
- Never auto-merge.
- Mark `needs_human` when unsafe or repeatedly failing.

---

### 7. Add Final Verification

Tasks:

- After AI remediation, rerun:
  - quality gate
  - compiler check
- Only mark pipeline completed when both pass.
- Store final verification result in `pipeline_stages`.

---

### 8. Harden GitHub App Operations

Tasks:

- Add better setup verification endpoint.
- Verify workflow file content hash/version.
- Verify repository secrets exist by name.
- Verify ruleset required checks contain:
  - `quality-gate`
  - `compiler-check`
- Add setup retry controls for failed repos.
- Add audit log view for provisioning actions.

---

### 9. Improve Production Security

Tasks:

- Rate-limit report ingestion.
- Enforce payload size limits.
- Verify GitHub webhook signatures.
- Keep repo allowlist enabled.
- Rotate repo-scoped dashboard API keys.
- Add secret redaction tests for every report path.
- Keep raw logs as artifacts, not large database blobs.

---

## UI Work Can Start Now

The professional UI upgrade can begin now because:

- Auth flow works.
- GitHub App install works.
- Repo sync works.
- Repo provisioning works.
- Pipeline storage exists.
- Pipeline Monitor exists.

UI should focus on:

- Professional SaaS layout.
- Cleaner onboarding wizard.
- Tenant/account selector.
- Repo setup status and retry UX.
- Pipeline Monitor polish.
- Clear separation between:
  - repository intelligence
  - pipeline enforcement
  - setup/onboarding

Do not block UI work on the compiler/AI modules. Those can be added after the
visual and navigation foundation is improved.
