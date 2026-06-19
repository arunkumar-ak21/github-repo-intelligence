# Automation-First GitHub Actions To Dashboard Smoke Test Guide

This guide is for the basic system smoke test only.

Goal:

```text
GitHub Actions -> report artifact -> Dashboard API -> Pipeline Monitor
```

This does not test the real Code-Quality scanner yet. It uses a mock GitHub
Actions workflow that passes folders with `good` in the name and fails folders
with `wrong` in the name.

After this smoke test works, the next phase is to connect the real
Code-Quality scanner.

---

## 1. What Changed After Testing

The first version worked, but it had too much manual setup:

- You had to manually create files and folders.
- You had to manually type `$env:DASHBOARD_API_KEY` and
  `$env:ALLOW_UNREGISTERED_REPOS`.
- You had to manually start ngrok.
- You had to manually copy GitHub secrets.
- You had to manually configure rulesets.
- You had to manually create a workflow file.

The improved setup reduces this:

- A script creates the smoke-test lab.
- A script starts the dashboard in smoke-test mode.
- A script starts ngrok if it is installed.
- A script can set GitHub Actions secrets if GitHub CLI is installed and logged in.
- The workflow file is generated automatically.
- The test push helper copies and pushes one test folder at a time.

Some manual work remains because GitHub intentionally requires repository admin
authorization for secrets and branch/ruleset protection.

---

## 2. What Can And Cannot Be Fully Automated

### Can be automated locally

- Creating the test repo folder.
- Creating `.github/workflows/basic-pipeline-smoke-test.yml`.
- Creating `README.md`.
- Creating `.gitignore`.
- Creating all good/wrong test folders.
- Starting the dashboard with smoke-test environment values.
- Starting ngrok if it is installed.
- Pushing one test branch at a time.

### Can be automated if GitHub CLI is authenticated

- Setting `DASHBOARD_URL`.
- Setting `DASHBOARD_API_KEY`.

### Still requires GitHub permission

- Creating or selecting the GitHub repo.
- Configuring branch rulesets or branch protection.
- Selecting required status checks.

Why this cannot be silently bypassed:

- GitHub secrets are sensitive configuration.
- Branch protection changes repository merge policy.
- GitHub requires an authenticated user or app with the right permissions.
- Required status checks usually appear only after the workflow has run at least
  once.

Long-term production fix:

- Deploy the dashboard to a real HTTPS URL.
- Replace ngrok with the deployed dashboard URL.
- Use a GitHub App or organization-level automation to register repos,
  configure secrets, and configure rulesets.

---

## 3. Generated Smoke-Test Lab

The helper creates this lab:

```text
C:\Users\kumar\Videos\test-system
|-- repo
|   |-- .github
|   |   `-- workflows
|   |       `-- basic-pipeline-smoke-test.yml
|   |-- README.md
|   `-- .gitignore
|-- test-file-bank
|   |-- test-1-good
|   |-- test-2-wrong
|   |-- test-3-good
|   |-- test-4-wrong
|   |-- test-5-good
|   |-- test-6-wrong
|   |-- test-7-good
|   `-- test-8-wrong
`-- push-smoke-test.ps1
```

Why the `test-file-bank` is outside the Git repo:

- It prevents accidentally pushing all future test folders to `main`.
- It avoids using `git add -A`.
- Each test branch contains only one copied test folder.

---

## 4. Create The Lab Automatically

Run this from PowerShell:

```powershell
cd "C:\Users\kumar\OneDrive\Pictures\Laptop data\Arun Mokashi's Folder\codex\github-repo-intelligence"

.\.venv\Scripts\python.exe scripts\create_basic_smoke_test_lab.py
```

This creates:

```text
C:\Users\kumar\Videos\test-system
```

To recreate files if they already exist:

```powershell
.\.venv\Scripts\python.exe scripts\create_basic_smoke_test_lab.py --force
```

Why this step matters:

- You do not manually create the workflow file.
- You do not manually create test folders.
- You get a repeatable smoke-test environment.

---

## 5. Connect The Generated Repo To GitHub

Create an empty GitHub repo, for example:

```text
test-system
```

Do not add README, `.gitignore`, or license in GitHub UI because the script
already generated local base files.

Then run:

```powershell
cd "C:\Users\kumar\Videos\test-system\repo"

git remote add origin https://github.com/YOUR_USERNAME/test-system.git
git add .github README.md .gitignore
git commit -m "add basic pipeline smoke test"
git push -u origin main
```

Why this step matters:

- The workflow must exist on `main` before feature branches can use it.
- Only base files are pushed to `main`.
- Test folders are copied from the bank later, one branch at a time.

---

## 6. Start The Dashboard Without Typing Raw `$env:` Commands

Instead of manually typing:

```powershell
$env:DASHBOARD_API_KEY="dev-test-key"
$env:ALLOW_UNREGISTERED_REPOS="true"
```

run:

```powershell
cd "C:\Users\kumar\OneDrive\Pictures\Laptop data\Arun Mokashi's Folder\codex\github-repo-intelligence"

.\scripts\start_dashboard_smoke.ps1
```

This starts:

```text
http://127.0.0.1:8012/#dashboard
```

The script sets:

```text
DASHBOARD_API_KEY=dev-test-key
ALLOW_UNREGISTERED_REPOS=true
```

Why these values exist:

- `DASHBOARD_API_KEY` protects `/api/quality/report`.
- GitHub Actions must send the same key as a bearer token.
- `ALLOW_UNREGISTERED_REPOS=true` lets the dashboard accept your temporary
  smoke-test repo without pre-registering it in the database.

Production difference:

- Use a long random API key.
- Set `ALLOW_UNREGISTERED_REPOS=false`.
- Register allowed repos in `monitored_repositories`.

---

## 7. Start ngrok With A Helper

GitHub Actions cannot call your laptop at:

```text
http://127.0.0.1:8012
```

For local testing, ngrok creates a temporary public HTTPS URL that forwards to
your local dashboard.

Run:

```powershell
cd "C:\Users\kumar\OneDrive\Pictures\Laptop data\Arun Mokashi's Folder\codex\github-repo-intelligence"

.\scripts\start_ngrok_8012.ps1
```

Copy only the HTTPS forwarding base URL, for example:

```text
https://abc123.ngrok-free.app
```

Do not copy:

```text
/#dashboard
```

Why ngrok exists:

- It is only needed because the dashboard is running locally.
- GitHub-hosted runners need a public URL.
- In production, ngrok disappears because the dashboard will be deployed to a
  real server.

---

## 8. Set GitHub Actions Secrets

### Option A: Use GitHub CLI

If `gh` is installed and authenticated:

```powershell
cd "C:\Users\kumar\OneDrive\Pictures\Laptop data\Arun Mokashi's Folder\codex\github-repo-intelligence"

.\scripts\set_github_smoke_secrets.ps1 `
  -Repo "YOUR_USERNAME/test-system" `
  -DashboardUrl "https://abc123.ngrok-free.app" `
  -ApiKey "dev-test-key"
```

Why this helps:

- You do not manually paste secrets in GitHub UI.
- The script sets both required secrets:

```text
DASHBOARD_URL
DASHBOARD_API_KEY
```

### Option B: Manual GitHub UI

If `gh` is not available:

```text
GitHub repo
-> Settings
-> Secrets and variables
-> Actions
-> New repository secret
```

Add:

```text
DASHBOARD_URL=https://abc123.ngrok-free.app
DASHBOARD_API_KEY=dev-test-key
```

Why this step matters:

- The workflow posts to `${DASHBOARD_URL}/api/quality/report`.
- The dashboard rejects reports unless the bearer token matches
  `DASHBOARD_API_KEY`.

---

## 9. Push Each Test Branch With One Command

Use the generated helper:

```powershell
cd "C:\Users\kumar\Videos\test-system"

.\push-smoke-test.ps1 test-1-good
```

Expected:

```text
feature/test-1-good -> quality-gate passes
```

Then:

```powershell
.\push-smoke-test.ps1 test-2-wrong
```

Expected:

```text
feature/test-2-wrong -> quality-gate fails
```

Run the full matrix:

```powershell
.\push-smoke-test.ps1 test-1-good
.\push-smoke-test.ps1 test-2-wrong
.\push-smoke-test.ps1 test-3-good
.\push-smoke-test.ps1 test-4-wrong
.\push-smoke-test.ps1 test-5-good
.\push-smoke-test.ps1 test-6-wrong
.\push-smoke-test.ps1 test-7-good
.\push-smoke-test.ps1 test-8-wrong
```

Expected:

```text
test-1-good  -> pass
test-2-wrong -> fail
test-3-good  -> pass
test-4-wrong -> fail
test-5-good  -> pass
test-6-wrong -> fail
test-7-good  -> pass
test-8-wrong -> fail
```

Why this helper exists:

- It checks out `main`.
- It pulls latest `main`.
- It copies only one folder from `test-file-bank`.
- It creates a feature branch.
- It runs `git add TEST_FOLDER`, not `git add -A`.
- It commits and pushes the branch.

---

## 10. Configure Merge Blocking

This step is still GitHub-side because it changes repository merge policy.

In GitHub:

```text
Repository
-> Settings
-> Rules
-> Rulesets
-> New branch ruleset
```

Use:

```text
Ruleset name: Protect main
Enforcement status: Active
Target branches: Include default branch
Require a pull request before merging: enabled
Require status checks to pass: enabled
Required check: Basic Pipeline Smoke Test / quality-gate
Block force pushes: enabled
Bypass list: empty
```

Important:

If GitHub says there are no checks to select, run the workflow once first.
GitHub often shows a status check only after it has appeared in at least one
workflow run.

Why this step matters:

- GitHub Actions cannot block the first push to a feature branch.
- Branch rulesets block merge into `main`.
- Failed `wrong` branches should not merge.
- Passed `good` branches should be allowed to merge.

Future automation:

- A GitHub App or organization admin automation can configure rulesets.
- For now, this is intentionally explicit because it requires repository admin
  permission.

---

## 11. Verify GitHub Actions

In GitHub:

```text
Repository -> Actions -> Basic Pipeline Smoke Test
```

For every branch, check:

- `quality-gate` started.
- `Create mock quality report` completed.
- `Upload Quality Reports` completed.
- `Send Quality Report to Dashboard` completed.
- `test-*good` branches passed.
- `test-*wrong` branches failed.

Artifact should contain:

```text
quality-report.json
quality-report.html
dashboard-quality-payload.json
workflow-summary.json
```

Why this matters:

- Artifacts prove the workflow generated report files.
- Dashboard submission proves GitHub Actions can reach your dashboard API.
- The pass/fail result proves the mock gate controls the workflow status.

---

## 12. Verify Pipeline Monitor

Open:

```text
http://127.0.0.1:8012/#dashboard
```

Go to:

```text
Pipeline Monitor
```

Expected rows:

```text
feature/test-1-good   quality passed
feature/test-2-wrong  quality failed
feature/test-3-good   quality passed
feature/test-4-wrong  quality failed
feature/test-5-good   quality passed
feature/test-6-wrong  quality failed
feature/test-7-good   quality passed
feature/test-8-wrong  quality failed
```

This confirms:

- GitHub Actions posted reports.
- `/api/quality/report` accepted them.
- Pipeline tables stored them.
- Pipeline Monitor displays them.

---

## 13. Troubleshooting

### No dashboard rows

Check:

1. Dashboard still running?
2. ngrok still running?
3. `DASHBOARD_URL` updated after ngrok restart?
4. `DASHBOARD_API_KEY` is `dev-test-key` in both places?
5. Workflow reached `Send Quality Report to Dashboard`?
6. `ALLOW_UNREGISTERED_REPOS=true` in smoke mode?

### Dashboard submission returns 401

Cause:

```text
DASHBOARD_API_KEY mismatch
```

Fix:

- Restart dashboard with `scripts/start_dashboard_smoke.ps1`.
- Reset GitHub secret with `scripts/set_github_smoke_secrets.ps1`.

### curl exit code 3

Cause:

```text
Malformed DASHBOARD_URL
```

Fix:

- Use only the ngrok base HTTPS URL.
- Example: `https://abc123.ngrok-free.app`
- Do not include `/#dashboard`.

### Wrong PR can still merge

Cause:

```text
Ruleset is missing required status check.
```

Fix:

- Go to ruleset settings.
- Enable required status checks.
- Add `Basic Pipeline Smoke Test / quality-gate`.

### Good branch failed

Check:

- Did the branch accidentally include a `wrong` folder?
- Did you use `git add -A` manually?
- Check the Actions log for detected folders.

---

## 14. Success Criteria

The smoke test is complete when:

- The lab is generated by script.
- The dashboard starts through `start_dashboard_smoke.ps1`.
- ngrok exposes port `8012`.
- GitHub secrets are set.
- All eight branches trigger GitHub Actions.
- Good branches pass.
- Wrong branches fail.
- Artifacts upload every time.
- Reports POST to `/api/quality/report`.
- Pipeline Monitor shows all eight runs.
- Ruleset blocks failed PRs from merging into `main`.

After this passes:

```text
Replace the mock workflow with the real Code-Quality scanner workflow.
```
