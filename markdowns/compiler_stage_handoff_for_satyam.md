# Compiler Stage Handoff For Satyam

This document explains how to plug the compiler/error-check module into the
autonomous quality pipeline.

The quality and repository setup system is already prepared for a stage named:

```text
compiler_check
```

The GitHub Actions status check name must be:

```text
compiler-check
```

Do not change these names unless the ruleset installer is updated too. Branch
rules require `quality-gate` and `compiler-check`.

## Where The Compiler Stage Fits

Pipeline order:

```text
quality-gate
        |
        | passes
        v
compiler-check
        |
        | passes
        v
completed

compiler-check
        |
        | fails
        v
ai-remediation
        |
        | patch generated
        v
final-verification
        |
        | reruns quality-gate + compiler-check
        v
completed or needs_human
```

Current handoff point:

- `quality-gate` is implemented.
- `compiler-check` exists as a workflow placeholder.
- Your task is to replace the placeholder with real compiler/build checks.
- AI remediation comes after your stage and should consume your normalized compiler findings.

## Existing Dashboard Endpoints

Use this endpoint for compiler stage reports:

```text
POST /api/pipeline/report
```

Related pipeline endpoints:

```text
GET /api/pipeline/runs
GET /api/pipeline/runs/{id}
GET /api/pipeline/latest/{owner}/{repo}
```

Quality-specific endpoint:

```text
POST /api/quality/report
```

Repo setup endpoints:

```text
GET  /api/setup/repositories
POST /api/setup/sync-installed-repositories
POST /api/setup/repositories/{repo_id}/provision
POST /api/setup/repositories/{repo_id}/verify
```

## Authentication

GitHub Actions posts compiler reports with:

```text
Authorization: Bearer ${{ secrets.DASHBOARD_API_KEY }}
Content-Type: application/json
```

`DASHBOARD_API_KEY` is repo-scoped. The Repo Setup provisioning flow creates it
automatically and stores it as a GitHub Actions secret.

Do not hardcode dashboard keys into workflow files.

## Compiler Report Payload

Send this payload to:

```text
POST ${{ secrets.DASHBOARD_URL }}/api/pipeline/report
```

Payload shape:

```json
{
  "stage": "compiler_check",
  "status": "failed",
  "blocking": true,
  "repo": "owner/repo",
  "branch": "feature/test",
  "commit_sha": "abc123",
  "pr_number": 12,
  "workflow_run_id": "123456789",
  "workflow_url": "https://github.com/owner/repo/actions/runs/123456789",
  "started_at": "2026-06-19T10:00:00Z",
  "finished_at": "2026-06-19T10:00:30Z",
  "duration_ms": 30000,
  "summary": {
    "language": "typescript",
    "tool": "tsc",
    "command": "npm run build",
    "exit_code": 2,
    "error_count": 4,
    "warning_count": 1,
    "files_with_errors": 3
  },
  "findings": [
    {
      "scanner": "typescript",
      "severity": "high",
      "rule_id": "TS2304",
      "title": "Cannot find name",
      "message": "Cannot find name 'foo'.",
      "file_path": "src/app.ts",
      "line_number": 12,
      "recommendation": "Import or define the missing symbol."
    }
  ],
  "artifacts": {
    "compiler_report": "compiler-report.json",
    "compiler_log": "compiler-log.txt",
    "github_artifact": "quality-report"
  },
  "next_stage": "ai_remediation",
  "errors": [],
  "raw_report": {
    "tool_output_summary": "sanitized compact output only"
  }
}
```

For a passing compiler check:

```json
{
  "stage": "compiler_check",
  "status": "passed",
  "blocking": false,
  "repo": "owner/repo",
  "branch": "feature/test",
  "commit_sha": "abc123",
  "workflow_run_id": "123456789",
  "summary": {
    "language": "typescript",
    "tool": "tsc",
    "command": "npm run build",
    "exit_code": 0,
    "error_count": 0,
    "warning_count": 0,
    "files_with_errors": 0
  },
  "findings": [],
  "artifacts": {
    "compiler_report": "compiler-report.json",
    "compiler_log": "compiler-log.txt",
    "github_artifact": "quality-report"
  },
  "next_stage": null,
  "errors": []
}
```

## Required Field Rules

Required fields:

- `stage`
- `status`
- `blocking`
- `repo`
- `commit_sha`
- `workflow_run_id`

Strongly recommended fields:

- `branch`
- `pr_number`
- `workflow_url`
- `started_at`
- `finished_at`
- `duration_ms`
- `summary`
- `findings`
- `artifacts`

Allowed stage value for your module:

```text
compiler_check
```

Allowed status values:

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

Compiler status policy:

- Build/compile success: `status=passed`, `blocking=false`.
- Compile errors found: `status=failed`, `blocking=true`.
- Compiler command crashes: `status=error`, `blocking=true`.
- Compiler cannot be detected: `status=skipped` locally, but `status=failed` or `error` in strict CI if the project is expected to compile.
- Unsafe or ambiguous remediation path: `status=needs_human`, `blocking=true`.

## Finding Format

Every compiler error should become one finding when possible:

```json
{
  "scanner": "typescript",
  "severity": "high",
  "rule_id": "TS2304",
  "title": "Cannot find name",
  "message": "Cannot find name 'foo'.",
  "file_path": "src/app.ts",
  "line_number": 12,
  "recommendation": "Import or define the missing symbol."
}
```

Severity guidance:

- `critical`: compile failure that blocks production build and touches security-sensitive code.
- `high`: normal compile failure that blocks build.
- `medium`: warning or partial compile issue that should be fixed.
- `low`: style or informational compiler warning.

The database currently stores stage findings in `quality_findings`, but the
storage is now stage-generic. Compiler findings are attached to the
`compiler_check` stage and returned in `GET /api/pipeline/runs/{id}`.

## Artifact Strategy

The workflow should upload artifacts with `if: always()`.

Recommended files:

```text
reports/compiler-report.json
reports/compiler-log.txt
reports/workflow-summary.json
```

Store large raw logs as GitHub Actions artifacts. Do not send huge logs into the
database payload. Send a summary and artifact reference instead.

## GitHub Actions Job Contract

The compiler job must keep this name:

```yaml
compiler-check:
  name: compiler-check
```

It should run only after the quality gate succeeds:

```yaml
needs: quality-gate
```

Recommended job behavior:

```text
1. Check out code.
2. Detect project language/build command.
3. Run compiler/build command.
4. Capture exit code.
5. Generate reports/compiler-report.json.
6. Generate reports/compiler-log.txt.
7. POST normalized compiler payload to /api/pipeline/report.
8. Upload artifacts with if: always().
9. Exit with compiler exit code after report upload.
```

The report POST must happen before the final failing exit.

## Minimal Workflow Pseudocode

```yaml
compiler-check:
  name: compiler-check
  runs-on: ubuntu-latest
  needs: quality-gate

  steps:
    - uses: actions/checkout@v4

    - name: Run compiler check
      run: |
        set +e
        # Replace this with real detection and compiler execution.
        npm run build > reports/compiler-log.txt 2>&1
        COMPILER_EXIT=$?
        set -e
        echo "COMPILER_EXIT=$COMPILER_EXIT" >> $GITHUB_ENV

    - name: Build compiler dashboard payload
      if: always()
      run: |
        # Create reports/compiler-report.json and dashboard payload here.
        echo "Build normalized compiler_check payload"

    - name: Send Compiler Report to Dashboard
      if: always()
      run: |
        curl -sS -X POST "${{ secrets.DASHBOARD_URL }}/api/pipeline/report" \
          -H "Content-Type: application/json" \
          -H "Authorization: Bearer ${{ secrets.DASHBOARD_API_KEY }}" \
          --data-binary @reports/dashboard-compiler-payload.json

    - name: Upload Compiler Reports
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: compiler-report
        path: reports/

    - name: Fail if compiler failed
      run: |
        exit "$COMPILER_EXIT"
```

## Security Requirements

The compiler module must not:

- Log secrets.
- Send raw secrets to the dashboard.
- Send raw secrets to AI remediation.
- Auto-merge code.
- Write directly to protected branches.

Before sending context to AI remediation:

- Remove raw secret values.
- Keep only file path, line number, error code, safe message, and recommendation.
- For secret findings, only suggest removal, environment variables, and credential rotation.

## Suggested Module Structure

Add this later when implementing the real compiler module:

```text
github-repo-intelligence/modules/compiler/
  __init__.py
  detector.py
  runner.py
  normalizer.py
  schemas.py
  routes.py
  README.md
```

Suggested responsibilities:

- `detector.py`: detect language/ecosystem/build commands.
- `runner.py`: run compiler/build command in GitHub Actions or controlled environment.
- `normalizer.py`: convert raw compiler output into stage payload.
- `schemas.py`: define compiler report models.
- `routes.py`: optional local/demo compiler endpoints only if needed.

## Test Cases Satyam Should Add

Add tests for:

- TypeScript compile failure -> `compiler_check.failed`.
- Python syntax error -> `compiler_check.failed`.
- Java/Maven build failure -> `compiler_check.failed`.
- Successful build -> `compiler_check.passed`.
- Compiler command missing -> fail closed in CI.
- Duplicate compiler report -> same stage row updated, not duplicated.
- Compiler findings are returned by `GET /api/pipeline/runs/{id}`.
- Secret-like values in compiler logs are redacted before storage.

## Handoff Acceptance Criteria

The compiler integration is ready when:

- GitHub Actions `compiler-check` runs after `quality-gate`.
- `compiler-check` posts to `/api/pipeline/report`.
- Pipeline Monitor shows compiler status.
- Compiler findings appear in run detail.
- Passing compiler check marks the run completed.
- Failing compiler check blocks merge.
- Dashboard stores artifact references, not huge raw logs.
- No raw secrets are stored or sent to AI.
- The ruleset still requires exactly `quality-gate` and `compiler-check`.
