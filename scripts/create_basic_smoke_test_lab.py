"""Create the basic GitHub Actions -> Dashboard smoke-test lab.

This script scaffolds a safe local lab:

    C:\\Users\\kumar\\Videos\\test-system
    ├── repo\\
    │   ├── .github\\workflows\\basic-pipeline-smoke-test.yml
    │   ├── README.md
    │   └── .gitignore
    ├── test-file-bank\\
    │   ├── test-1-good\\
    │   ├── test-2-wrong\\
    │   └── ...
    └── push-smoke-test.ps1

The test-file bank stays outside the Git repo so `git add -A` cannot
accidentally stage every future test case into `main`.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


WORKFLOW_YAML = """name: Basic Pipeline Smoke Test

on:
  push:
    branches: [main, "feature/**"]
  pull_request:
    branches: [main]

permissions:
  contents: read
  actions: read

jobs:
  quality-gate:
    name: quality-gate
    runs-on: ubuntu-latest

    steps:
      - name: Checkout pushed code
        uses: actions/checkout@v4

      - name: Create mock quality report
        env:
          REPO: ${{ github.repository }}
          BRANCH: ${{ github.head_ref || github.ref_name }}
          COMMIT_SHA: ${{ github.sha }}
          WORKFLOW_RUN_ID: ${{ github.run_id }}
          WORKFLOW_URL: https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          mkdir -p reports

          python - <<'PY'
          import json
          import os
          from datetime import datetime, timezone
          from pathlib import Path

          repo = os.environ.get("REPO", "")
          branch = os.environ.get("BRANCH", "")
          commit_sha = os.environ.get("COMMIT_SHA", "")
          workflow_run_id = os.environ.get("WORKFLOW_RUN_ID", "")
          workflow_url = os.environ.get("WORKFLOW_URL", "")
          pr_raw = os.environ.get("PR_NUMBER", "")
          pr_number = int(pr_raw) if pr_raw.strip().isdigit() else None

          test_dirs = sorted(
              p.name for p in Path(".").iterdir()
              if p.is_dir() and p.name.startswith("test-")
          )
          wrong_tests = [name for name in test_dirs if "wrong" in name]
          good_tests = [name for name in test_dirs if "good" in name]

          status = "passed"
          verdict = "pass"
          blocking = False
          findings = []

          if wrong_tests:
              status = "failed"
              verdict = "fail"
              blocking = True
              for test_name in wrong_tests:
                  findings.append({
                      "scanner": "mock-quality-gate",
                      "severity": "high",
                      "rule_id": "MOCK_WRONG_TEST",
                      "title": f"Wrong test detected: {test_name}",
                      "message": f"{test_name} is intentionally marked as wrong for pipeline testing.",
                      "file_path": test_name,
                      "line_number": 1,
                      "recommendation": "This is expected for wrong test branches."
                  })

          summary = {
              "total_findings": len(findings),
              "critical": 0,
              "high": len(findings),
              "medium": 0,
              "low": 0,
              "files_scanned": len(test_dirs),
              "duration_seconds": 2.0,
          }

          now = datetime.now(timezone.utc).isoformat()
          raw_report = {
              "verdict": verdict,
              "status": status,
              "blocking": blocking,
              "summary": summary,
              "findings": findings,
              "good_tests": good_tests,
              "wrong_tests": wrong_tests,
              "generated_at": now,
          }

          payload = {
              "repo": repo,
              "branch": branch,
              "commit_sha": commit_sha,
              "pr_number": pr_number,
              "workflow_run_id": workflow_run_id,
              "workflow_url": workflow_url,
              "stage": "quality_gate",
              "status_check": "quality-gate",
              "verdict": verdict,
              "status": status,
              "blocking": blocking,
              "started_at": now,
              "finished_at": now,
              "summary": summary,
              "findings": findings,
              "artifacts": {
                  "json_report": "quality-report.json",
                  "html_report": "quality-report.html",
                  "github_artifact": "quality-report"
              },
              "raw_report": raw_report
          }

          Path("reports/quality-report.json").write_text(
              json.dumps(raw_report, indent=2), encoding="utf-8"
          )
          Path("reports/dashboard-quality-payload.json").write_text(
              json.dumps(payload, indent=2), encoding="utf-8"
          )
          Path("reports/workflow-summary.json").write_text(
              json.dumps(payload, indent=2), encoding="utf-8"
          )

          html = f\"\"\"
          <html><body>
          <h1>Basic Quality Report</h1>
          <p><b>Repo:</b> {repo}</p>
          <p><b>Branch:</b> {branch}</p>
          <p><b>Status:</b> {status}</p>
          <p><b>Verdict:</b> {verdict}</p>
          <p><b>Good tests:</b> {good_tests}</p>
          <p><b>Wrong tests:</b> {wrong_tests}</p>
          </body></html>
          \"\"\"
          Path("reports/quality-report.html").write_text(html, encoding="utf-8")
          if blocking:
              Path("reports/SCAN_FAILED").write_text("true", encoding="utf-8")
          PY

      - name: Upload Quality Reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: quality-report
          path: reports/

      - name: Send Quality Report to Dashboard
        if: always()
        run: |
          set +e
          HTTP_CODE=$(curl -sS -o /tmp/dashboard_response.txt -w "%{http_code}" \
            --connect-timeout 10 \
            --max-time 30 \
            -X POST "${{ secrets.DASHBOARD_URL }}/api/quality/report" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${{ secrets.DASHBOARD_API_KEY }}" \
            --data-binary @reports/dashboard-quality-payload.json)
          CURL_EXIT=$?
          set -e

          if [ "$CURL_EXIT" != "0" ]; then
            echo "::warning::Dashboard submission failed with curl exit code $CURL_EXIT"
            cat /tmp/dashboard_response.txt || true
          elif [ "$HTTP_CODE" -lt 200 ] || [ "$HTTP_CODE" -ge 300 ]; then
            echo "::warning::Dashboard submission returned HTTP $HTTP_CODE"
            cat /tmp/dashboard_response.txt || true
          else
            echo "Dashboard submission successful with HTTP $HTTP_CODE"
          fi

      - name: Fail if quality gate failed
        run: |
          if [ -f reports/SCAN_FAILED ]; then
            echo "Quality gate failed because wrong test folder exists."
            exit 1
          fi
          echo "Quality gate passed."

  compiler-check:
    name: compiler-check
    runs-on: ubuntu-latest
    needs: quality-gate

    steps:
      - uses: actions/checkout@v4
      - name: Compiler placeholder
        run: echo "Compiler check placeholder passed."
"""


README = """# Basic Pipeline Test Repo

This repo tests:

```text
GitHub Actions -> Dashboard API -> Pipeline Monitor
```

Good test branches should pass.
Wrong test branches should fail.

The folders under `../test-file-bank` are copied into this repo one at a time.
Do not use `git add -A` during smoke tests.
"""


GITIGNORE = """.venv/
__pycache__/
*.pyc
node_modules/
.env
*.pem
*.key
"""


TEST_FILES = {
    "test-1-good/clean_app.py": """def add(a, b):
    return a + b

print(add(10, 20))
""",
    "test-2-wrong/fake_secret.py": """# Fake secret for smoke testing only
FAKE_API_KEY = "fake_secret_test_123456789"
""",
    "test-3-good/env_example.txt": """DATABASE_URL=your_database_url_here
API_KEY=your_api_key_here
""",
    "test-4-wrong/danger_env.txt": """DATABASE_PASSWORD=fake_password_123
SECRET_KEY=fake_secret_key_123
""",
    "test-5-good/requirements.txt": """requests>=2.31.0
fastapi>=0.110.0
""",
    "test-6-wrong/requirements.txt": """django==1.2
requests==2.19.1
pyyaml==3.13
""",
    "test-7-good/good_python.py": """def greet(name):
    return f"Hello, {name}"

print(greet("Arun"))
""",
    "test-8-wrong/broken_python.py": """def broken_function():
    print("missing closing parenthesis"

broken_function()
""",
}


PUSH_SCRIPT = r"""param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "test-1-good",
        "test-2-wrong",
        "test-3-good",
        "test-4-wrong",
        "test-5-good",
        "test-6-wrong",
        "test-7-good",
        "test-8-wrong"
    )]
    [string]$TestName
)

$ErrorActionPreference = "Stop"

$LabRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Join-Path $LabRoot "repo"
$BankDir = Join-Path $LabRoot "test-file-bank"
$Source = Join-Path $BankDir $TestName
$Destination = Join-Path $RepoDir $TestName
$Branch = "feature/$TestName"

if (-not (Test-Path $RepoDir)) {
    throw "Repo folder not found: $RepoDir"
}
if (-not (Test-Path $Source)) {
    throw "Test folder not found: $Source"
}

Push-Location $RepoDir
try {
    git checkout main
    git pull origin main

    if (Test-Path $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }

    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force

    git checkout -b $Branch
    git add $TestName
    git commit -m "add $TestName"
    git push -u origin $Branch

    Write-Host ""
    Write-Host "Pushed $Branch"
    Write-Host "Expected result: " -NoNewline
    if ($TestName -like "*wrong*") {
        Write-Host "quality-gate should fail"
    } else {
        Write-Host "quality-gate should pass"
    }
} finally {
    Pop-Location
}
"""


def default_lab_root() -> Path:
    return Path.home() / "Videos" / "test-system"


def write_file(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def init_git(repo_dir: Path) -> None:
    if (repo_dir / ".git").exists():
        return
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo_dir, check=True)


def create_lab(lab_root: Path, force: bool, skip_git: bool) -> None:
    repo_dir = lab_root / "repo"
    bank_dir = lab_root / "test-file-bank"

    write_file(repo_dir / ".github" / "workflows" / "basic-pipeline-smoke-test.yml", WORKFLOW_YAML, force)
    write_file(repo_dir / "README.md", README, force)
    write_file(repo_dir / ".gitignore", GITIGNORE, force)

    for relative_path, content in TEST_FILES.items():
        write_file(bank_dir / relative_path, content, force)

    write_file(lab_root / "push-smoke-test.ps1", PUSH_SCRIPT, force)

    if not skip_git:
        init_git(repo_dir)

    print(f"Smoke-test lab created at: {lab_root}")
    print(f"Git repo folder: {repo_dir}")
    print(f"Test-file bank: {bank_dir}")
    print("")
    print("Next:")
    print("1. Add a GitHub remote in the repo folder.")
    print("2. Commit only .github, README.md, and .gitignore to main.")
    print("3. Start the dashboard with scripts/start_dashboard_smoke.ps1.")
    print("4. Start ngrok on port 8012.")
    print("5. Set DASHBOARD_URL and DASHBOARD_API_KEY as GitHub Actions secrets.")
    print("6. Push test folders using push-smoke-test.ps1 test-1-good, etc.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the basic smoke-test lab.")
    parser.add_argument(
        "--lab-root",
        default=str(default_lab_root()),
        help="Target lab root. Default: C:\\Users\\<you>\\Videos\\test-system",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated files.")
    parser.add_argument("--skip-git", action="store_true", help="Do not run git init.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    create_lab(Path(args.lab_root), force=args.force, skip_git=args.skip_git)


if __name__ == "__main__":
    main()
