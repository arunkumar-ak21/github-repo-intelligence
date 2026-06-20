"""Repository provisioning helpers for workflow, secrets, and rulesets."""

from __future__ import annotations

import base64
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any

import requests
from sqlalchemy.orm import Session

from core.config import settings
from core.models import GitHubInstallation, MonitoredRepository, RepositoryApiKey
from modules.github_app.service import upsert_repositories_from_payload
from modules.tenancy.api_keys import rotate_repository_api_key
from modules.tenancy.service import record_audit_event


QUALITY_RULESET_NAME = "Arya Quality Required Checks"
REQUIRED_SECRET_NAMES = {"DASHBOARD_URL", "DASHBOARD_API_KEY"}
SCANNER_REPO_SECRET_NAME = "ARYA_SCANNER_REPO_TOKEN"
MANAGED_SECRET_NAMES = REQUIRED_SECRET_NAMES | {SCANNER_REPO_SECRET_NAME}
REQUIRED_STATUS_CHECKS = {"quality-gate", "compiler-check"}


def required_secret_names() -> set[str]:
    """Secrets that must exist for the generated workflow in the current mode.

    ARYA_SCANNER_REPO_TOKEN is only required when the scanner repository is private
    or the platform admin explicitly configured QUALITY_SCANNER_REPO_TOKEN.
    Public scanner repositories do not need this secret.
    """

    names = set(REQUIRED_SECRET_NAMES)
    if settings.QUALITY_SCANNER_REPO_TOKEN:
        names.add(SCANNER_REPO_SECRET_NAME)
    return names


class ProvisioningError(RuntimeError):
    """Raised when repository provisioning cannot complete."""


class GitHubApiError(ProvisioningError):
    """Raised when GitHub returns a non-success API response."""

    def __init__(self, method: str, url: str, status_code: int, response_text: str) -> None:
        self.method = method
        self.url = url
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(f"GitHub API {method} {url} failed: {status_code} {response_text}")


def _github_ruleset_blocks_direct_write(exc: GitHubApiError) -> bool:
    text = exc.response_text.lower()
    return exc.status_code == 409 and (
        "repository rule violations" in text
        or "changes must be made through a pull request" in text
    )


def _dashboard_url_is_local(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"} or host.startswith("192.168.") or host.startswith("10.")


def normalized_public_base_url() -> str:
    """Return the dashboard URL that will be written into GitHub Actions secrets.

    GitHub Actions cannot recover from an empty or malformed DASHBOARD_URL secret, so
    repository provisioning must fail before writing secrets when this value is invalid.
    """

    url = (settings.PUBLIC_BASE_URL or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProvisioningError(
            "PUBLIC_BASE_URL must be a full URL such as https://your-ngrok-url.ngrok-free.app. "
            "Configure this before provisioning repositories."
        )
    if _dashboard_url_is_local(url) and not settings.ALLOW_LOCAL_DASHBOARD_URL_FOR_PROVISIONING:
        raise ProvisioningError(
            "PUBLIC_BASE_URL is local. GitHub Actions cannot post reports to localhost. "
            "Use a deployed HTTPS dashboard URL, or use ngrok/cloudflared for local testing."
        )
    return url


def _model_has_attr(obj: Any, name: str) -> bool:
    """Return True when a SQLAlchemy model has this mapped/runtime attribute.

    This keeps the provisioning module compatible while local DB/model migrations
    are being applied across machines.
    """

    return hasattr(type(obj), name) or hasattr(obj, name)


def _set_model_attr(obj: Any, name: str, value: Any) -> None:
    if _model_has_attr(obj, name):
        setattr(obj, name, value)


def _get_model_attr(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default) if _model_has_attr(obj, name) else default


def _iso_optional(value: Any) -> str | None:
    return value.isoformat() if value else None


def _clear_setup_pr_fields(repo: MonitoredRepository) -> None:
    _set_model_attr(repo, "setup_pr_number", None)
    _set_model_attr(repo, "setup_pr_url", None)
    _set_model_attr(repo, "setup_pr_branch", None)


def _set_setup_pr_fields(repo: MonitoredRepository, workflow_delivery: dict[str, Any]) -> None:
    _set_model_attr(repo, "setup_pr_number", workflow_delivery.get("pull_request_number"))
    _set_model_attr(repo, "setup_pr_url", workflow_delivery.get("pull_request_url"))
    _set_model_attr(repo, "setup_pr_branch", workflow_delivery.get("branch"))


def _clear_cleanup_pr_fields(repo: MonitoredRepository) -> None:
    _set_model_attr(repo, "cleanup_pr_number", None)
    _set_model_attr(repo, "cleanup_pr_url", None)
    _set_model_attr(repo, "cleanup_pr_branch", None)


def _set_cleanup_pr_fields(repo: MonitoredRepository, delivery: dict[str, Any]) -> None:
    _set_model_attr(repo, "cleanup_pr_number", delivery.get("pull_request_number"))
    _set_model_attr(repo, "cleanup_pr_url", delivery.get("pull_request_url"))
    _set_model_attr(repo, "cleanup_pr_branch", delivery.get("branch"))


def provisioning_blockers() -> list[str]:
    blockers: list[str] = []
    if settings.PROVISIONING_DRY_RUN:
        blockers.append("Real provisioning is disabled because PROVISIONING_DRY_RUN is true.")
    try:
        normalized_public_base_url()
    except ProvisioningError as exc:
        blockers.append(str(exc))
    if settings.QUALITY_WORKFLOW_MODE == "reusable" and settings.QUALITY_REUSABLE_WORKFLOW_REF.startswith("company/"):
        blockers.append("QUALITY_REUSABLE_WORKFLOW_REF is still the placeholder central workflow reference.")
    if settings.QUALITY_WORKFLOW_MODE == "standalone" and not settings.QUALITY_SCANNER_REPOSITORY:
        blockers.append("QUALITY_SCANNER_REPOSITORY is not configured; the client workflow cannot install the real Code-Quality scanner.")
    if not settings.GITHUB_APP_ID:
        blockers.append("GITHUB_APP_ID is not configured.")
    if not (settings.GITHUB_APP_PRIVATE_KEY or settings.GITHUB_APP_PRIVATE_KEY_PATH):
        blockers.append("GitHub App private key is not configured on the backend.")
    return blockers



def _workflow_scalar(value: str) -> str:
    """Return a safe one-line value for insertion into generated YAML."""

    return str(value or "").replace('"', '\\"').replace("\n", " ").strip()


def _quality_gate_enforcement() -> str:
    value = (settings.QUALITY_GATE_ENFORCEMENT or "monitor").strip().lower()
    return value if value in {"monitor", "enforce"} else "monitor"


def _scanner_package_path_expression() -> str:
    """Bash expression used by generated workflows to install the scanner package."""

    return """SCANNER_ROOT=\"$GITHUB_WORKSPACE/.arya/code-quality\"
if [ -n \"$ARYA_SCANNER_SUBDIRECTORY\" ]; then
  SCANNER_ROOT=\"$SCANNER_ROOT/$ARYA_SCANNER_SUBDIRECTORY\"
fi
if [ ! -f \"$SCANNER_ROOT/pyproject.toml\" ]; then
  echo \"::error::Code-Quality scanner pyproject.toml was not found at $SCANNER_ROOT\"
  echo \"Check QUALITY_SCANNER_REPOSITORY, QUALITY_SCANNER_REF and QUALITY_SCANNER_SUBDIRECTORY.\"
  exit 1
fi
if [ -n \"$ARYA_SCANNER_PACKAGE_EXTRAS\" ]; then
  python -m pip install -e \"$SCANNER_ROOT[$ARYA_SCANNER_PACKAGE_EXTRAS]\"
else
  python -m pip install -e \"$SCANNER_ROOT\"
fi"""


def render_caller_workflow() -> str:
    if settings.QUALITY_WORKFLOW_MODE != "reusable":
        return render_standalone_workflow()
    return "\n".join(
        [
            "name: Company Quality Pipeline",
            "",
            "on:",
            "  push:",
            '    branches: [main, develop, "feature/**"]',
            "  pull_request:",
            "    branches: [main, develop]",
            "",
            "jobs:",
            "  quality:",
            f"    uses: {settings.QUALITY_REUSABLE_WORKFLOW_REF}",
            "    with:",
            f'      scanner_repository: "{_workflow_scalar(settings.QUALITY_SCANNER_REPOSITORY)}"',
            f'      scanner_ref: "{_workflow_scalar(settings.QUALITY_SCANNER_REF)}"',
            f'      scanner_subdirectory: "{_workflow_scalar(settings.QUALITY_SCANNER_SUBDIRECTORY)}"',
            f'      scanner_package_extras: "{_workflow_scalar(settings.QUALITY_SCANNER_PACKAGE_EXTRAS)}"',
            f'      enforcement: "{_quality_gate_enforcement()}"',
            "    secrets: inherit",
            "",
        ]
    )

def render_standalone_workflow() -> str:
    """Generate the client-repository workflow that runs the real Code-Quality package.

    The previous temporary scanner is intentionally kept below as
    render_builtin_fallback_workflow() for local emergency fallback, but the
    production path must install and run the standalone cq-pipeline package.
    """

    scanner_repository = _workflow_scalar(settings.QUALITY_SCANNER_REPOSITORY)
    if not scanner_repository or scanner_repository.lower() == "builtin":
        return render_builtin_fallback_workflow()

    scanner_ref = _workflow_scalar(settings.QUALITY_SCANNER_REF or "main")
    scanner_subdirectory = _workflow_scalar(settings.QUALITY_SCANNER_SUBDIRECTORY)
    scanner_package_extras = _workflow_scalar(settings.QUALITY_SCANNER_PACKAGE_EXTRAS)
    enforcement = _quality_gate_enforcement()
    install_scanner_script = _scanner_package_path_expression()

    return f"""name: Company Quality Pipeline

on:
  push:
    branches: [main, develop, "feature/**"]
  pull_request:
    branches: [main, develop]

permissions:
  contents: read
  pull-requests: write
  checks: write
  actions: read

env:
  ARYA_SCANNER_REPOSITORY: "{scanner_repository}"
  ARYA_SCANNER_REF: "{scanner_ref}"
  ARYA_SCANNER_SUBDIRECTORY: "{scanner_subdirectory}"
  ARYA_SCANNER_PACKAGE_EXTRAS: "{scanner_package_extras}"
  ARYA_QUALITY_GATE_ENFORCEMENT: "{enforcement}"

jobs:
  quality-gate:
    name: quality-gate
    runs-on: ubuntu-latest

    steps:
      - name: Checkout target repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          path: source

      - name: Checkout Arya Code Quality scanner
        uses: actions/checkout@v4
        with:
          repository: ${{{{ env.ARYA_SCANNER_REPOSITORY }}}}
          ref: ${{{{ env.ARYA_SCANNER_REF }}}}
          path: .arya/code-quality
          token: ${{{{ secrets.ARYA_SCANNER_REPO_TOKEN || github.token }}}}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Arya Code Quality scanner
        run: |
          python -m pip install --upgrade pip
{_indent_for_yaml(install_scanner_script, 10)}

      - name: Install external scanner tools
        run: |
          set -e
          if ! command -v gitleaks >/dev/null 2>&1; then
            curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.22.1/gitleaks_8.22.1_linux_x64.tar.gz \
              | sudo tar -xz -C /usr/local/bin/ gitleaks
          fi
          gitleaks version || true
          semgrep --version || true

      - name: Run Arya Code Quality scan
        run: |
          mkdir -p reports source/reports
          echo "SCAN_STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_ENV"

          set +e
          cq-pipeline scan --all --format all --project "$GITHUB_WORKSPACE/source"
          SCAN_EXIT=$?
          set -e

          echo "SCAN_EXIT=$SCAN_EXIT" >> "$GITHUB_ENV"

      - name: Normalize report filenames
        if: always()
        run: |
          mkdir -p reports

          TARGET_JSON="reports/quality-report.json"
          TARGET_HTML="reports/quality-report.html"

          JSON_REPORT="$(ls -t source/reports/*.json reports/*.json 2>/dev/null | head -n 1 || true)"
          HTML_REPORT="$(ls -t source/reports/*.html reports/*.html 2>/dev/null | head -n 1 || true)"

          if [ -n "$JSON_REPORT" ]; then
            if [ "$JSON_REPORT" != "$TARGET_JSON" ]; then
              cp "$JSON_REPORT" "$TARGET_JSON"
            fi
          else
            echo '{{"verdict":"error","error":"No JSON report generated by cq-pipeline"}}' > "$TARGET_JSON"
          fi

          if [ -n "$HTML_REPORT" ]; then
            if [ "$HTML_REPORT" != "$TARGET_HTML" ]; then
              cp "$HTML_REPORT" "$TARGET_HTML"
            fi
          else
            echo "<html><body><h1>No HTML report generated</h1></body></html>" > "$TARGET_HTML"
          fi

      - name: Build dashboard quality payload
        if: always()
        run: |
          python - <<'PY'
          import json, os
          from datetime import datetime, timezone
          from pathlib import Path

          report_path = Path("reports/quality-report.json")
          raw = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {{"verdict": "error"}}
          verdict = str(raw.get("verdict") or "error").lower()
          if verdict in {{"pass", "passed"}}:
              verdict, status, blocking = "pass", "passed", False
          elif verdict in {{"warn", "warning"}}:
              verdict, status, blocking = "warn", "passed", False
          elif verdict in {{"fail", "failed"}}:
              verdict, status, blocking = "fail", "failed", True
          else:
              verdict, status, blocking = "error", "error", True

          event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
          pr_number = (event.get("pull_request") or {{}}).get("number")
          repo = os.environ["GITHUB_REPOSITORY"]
          run_id = os.environ["GITHUB_RUN_ID"]
          findings = []
          for scan in raw.get("scan_results") or []:
              scanner_name = scan.get("scanner_name") or scan.get("scanner")
              for finding in scan.get("findings") or []:
                  findings.append({{
                      "scanner": finding.get("scanner") or scanner_name,
                      "severity": finding.get("severity"),
                      "rule_id": finding.get("rule_id"),
                      "title": finding.get("title"),
                      "message": finding.get("message"),
                      "file_path": finding.get("file_path"),
                      "line_number": finding.get("line_number"),
                      "recommendation": finding.get("recommendation") or finding.get("suggestion"),
                  }})

          payload = {{
              "repo": repo,
              "branch": os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME"),
              "commit_sha": os.environ["GITHUB_SHA"],
              "pr_number": pr_number,
              "workflow_run_id": run_id,
              "workflow_url": f"https://github.com/{{repo}}/actions/runs/{{run_id}}",
              "stage": "quality_gate",
              "status_check": "quality-gate",
              "verdict": verdict,
              "status": status,
              "blocking": blocking,
              "started_at": os.environ.get("SCAN_STARTED_AT"),
              "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "summary": {{
                  "total_findings": raw.get("total_findings", len(findings)),
                  "critical": raw.get("critical_count", 0),
                  "high": raw.get("high_count", 0),
                  "medium": raw.get("medium_count", 0),
                  "low": raw.get("low_count", 0),
                  "files_scanned": raw.get("files_scanned", 0),
                  "duration_seconds": raw.get("duration_seconds", 0),
                  "enforcement": os.environ.get("ARYA_QUALITY_GATE_ENFORCEMENT", "monitor"),
                  "scanner_repository": os.environ.get("ARYA_SCANNER_REPOSITORY", ""),
              }},
              "findings": findings[:500],
              "artifacts": {{
                  "json_report": "quality-report.json",
                  "html_report": "quality-report.html",
                  "github_artifact": "quality-report",
              }},
              "raw_report": raw,
          }}
          Path("reports/dashboard-quality-payload.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
          summary = {{key: payload[key] for key in ["repo", "branch", "commit_sha", "pr_number", "workflow_run_id", "workflow_url", "stage", "status_check", "verdict", "status", "blocking", "started_at", "finished_at", "summary", "artifacts"]}}
          Path("reports/workflow-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
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
          DASHBOARD_URL="${{{{ secrets.DASHBOARD_URL }}}}"
          DASHBOARD_API_KEY="${{{{ secrets.DASHBOARD_API_KEY }}}}"

          if [ -z "$DASHBOARD_URL" ]; then
            echo "::warning::DASHBOARD_URL secret is missing or empty. Report was not sent."
            exit 0
          fi
          case "$DASHBOARD_URL" in
            http://*|https://*) ;;
            *) echo "::warning::DASHBOARD_URL must start with http:// or https://. Report was not sent."; exit 0 ;;
          esac
          if [ -z "$DASHBOARD_API_KEY" ]; then
            echo "::warning::DASHBOARD_API_KEY secret is missing or empty. Report was not sent."
            exit 0
          fi

          HTTP_CODE=$(curl -sS -o /tmp/dashboard_response.txt -w "%{{http_code}}" \
            --connect-timeout 10 \
            --max-time 30 \
            -X POST "$DASHBOARD_URL/api/quality/report" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $DASHBOARD_API_KEY" \
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

      - name: Complete quality gate
        if: ${{{{ !startsWith(github.head_ref, 'arya/setup-quality-pipeline') && !startsWith(github.ref_name, 'arya/setup-quality-pipeline') }}}}
        run: |
          ENFORCEMENT="${{{{ vars.QUALITY_GATE_ENFORCEMENT || env.ARYA_QUALITY_GATE_ENFORCEMENT }}}}"
          if [ "$ENFORCEMENT" = "enforce" ]; then
            echo "Enforce mode enabled. Exiting with scan result: $SCAN_EXIT"
            exit "$SCAN_EXIT"
          fi
          echo "Monitor mode enabled. Findings are reported to dashboard but this GitHub check will pass."
          exit 0

  compiler-check:
    name: compiler-check
    runs-on: ubuntu-latest
    needs: quality-gate

    steps:
      - uses: actions/checkout@v4
        with:
          path: source

      - name: Run compiler check
        run: |
          echo "Compiler check placeholder"
"""


def _indent_for_yaml(script: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in script.splitlines())


def render_builtin_fallback_workflow() -> str:
    return r"""name: Company Quality Pipeline

on:
  push:
    branches: [main, develop, "feature/**"]
  pull_request:
    branches: [main, develop]

permissions:
  contents: read
  pull-requests: write
  checks: write
  actions: read

jobs:
  quality-gate:
    name: quality-gate
    runs-on: ubuntu-latest

    steps:
      - name: Checkout pushed code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Code Quality Tool
        run: |
          python -m pip install --upgrade pip
          echo "Using built-in Arya quality scanner bundled in this workflow."

      - name: Run Code Quality Scan
        run: |
          mkdir -p reports
          echo "SCAN_STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_ENV"

          set +e
          python - <<'PY'
          import json
          import os
          import re
          from datetime import datetime, timezone
          from html import escape
          from pathlib import Path

          ROOT = Path.cwd()
          IGNORE_DIRS = {
              ".git", ".github", "node_modules", ".venv", "venv", "env", "__pycache__",
              "dist", "build", "coverage", ".next", ".cache", "reports", "target", ".mypy_cache",
              ".pytest_cache", ".ruff_cache", ".turbo",
          }
          TEXT_SUFFIXES = {
              ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rb", ".php",
              ".cs", ".cpp", ".c", ".h", ".hpp", ".rs", ".swift", ".scala", ".sql",
              ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".conf", ".env", ".txt",
              ".md", ".xml", ".html", ".css", ".scss", ".sh", ".ps1", "",
          }
          SECRET_PATTERNS = [
              ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
              ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
              ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
              ("private_key", re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----")),
              ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{25,}\b")),
              ("generic_secret_assignment", re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['\"]?[A-Za-z0-9_.:/+=-]{24,}")),
          ]

          findings = []
          files_scanned = 0

          def add_finding(scanner, severity, rule_id, title, message, file_path, line_number=None, recommendation=""):
              findings.append({
                  "scanner": scanner,
                  "severity": severity,
                  "rule_id": rule_id,
                  "title": title,
                  "message": message,
                  "file_path": file_path,
                  "line_number": line_number,
                  "recommendation": recommendation,
              })

          def should_skip(path: Path) -> bool:
              return any(part in IGNORE_DIRS for part in path.parts)

          for path in ROOT.rglob("*"):
              if not path.is_file() or should_skip(path.relative_to(ROOT)):
                  continue
              if path.suffix.lower() not in TEXT_SUFFIXES:
                  continue
              rel = path.relative_to(ROOT).as_posix()
              try:
                  text = path.read_text(encoding="utf-8", errors="ignore")
              except Exception:
                  continue
              files_scanned += 1
              for line_no, line in enumerate(text.splitlines(), start=1):
                  for rule_id, pattern in SECRET_PATTERNS:
                      if pattern.search(line):
                          add_finding(
                              "built_in_secrets",
                              "critical",
                              rule_id,
                              "Potential secret detected",
                              "A token/credential-shaped value was detected. Secret value is intentionally redacted.",
                              rel,
                              line_no,
                              "Remove the credential from Git history, move it to a secret manager/environment variable, and rotate it.",
                          )

          req = ROOT / "requirements.txt"
          if req.exists():
              for line_no, raw_line in enumerate(req.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                  line = raw_line.strip()
                  if not line or line.startswith("#") or line.startswith("-") or "git+" in line or "://" in line:
                      continue
                  if "==" not in line:
                      add_finding(
                          "dependency_policy",
                          "medium",
                          "unpinned_python_dependency",
                          "Unpinned Python dependency",
                          "A requirements.txt dependency is not pinned with ==.",
                          "requirements.txt",
                          line_no,
                          "Pin production dependencies to exact versions for repeatable builds.",
                      )

          package_json = ROOT / "package.json"
          if package_json.exists():
              try:
                  package_data = json.loads(package_json.read_text(encoding="utf-8"))
                  for section in ("dependencies", "devDependencies"):
                      deps = package_data.get(section) or {}
                      if isinstance(deps, dict):
                          for name, version in deps.items():
                              version_text = str(version)
                              if version_text in {"*", "latest"} or version_text.startswith(("^", "~")):
                                  add_finding(
                                      "dependency_policy",
                                      "low",
                                      "loose_node_dependency",
                                      "Loose Node dependency version",
                                      f"{name} uses a non-exact version range in {section}.",
                                      "package.json",
                                      None,
                                      "Use exact versions or a lockfile for production deployments.",
                                  )
              except Exception as exc:
                  add_finding(
                      "dependency_policy",
                      "medium",
                      "package_json_parse_error",
                      "Could not parse package.json",
                      str(exc),
                      "package.json",
                      None,
                      "Fix package.json syntax.",
                  )

          counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
          for finding in findings:
              severity = str(finding.get("severity") or "low").lower()
              if severity in counts:
                  counts[severity] += 1

          if counts["critical"] or counts["high"]:
              verdict = "fail"
              exit_code = 1
          elif counts["medium"] or counts["low"]:
              verdict = "warn"
              exit_code = 0
          else:
              verdict = "pass"
              exit_code = 0

          report = {
              "verdict": verdict,
              "scanner": "arya_builtin_quality_scanner",
              "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "total_findings": len(findings),
              "critical_count": counts["critical"],
              "high_count": counts["high"],
              "medium_count": counts["medium"],
              "low_count": counts["low"],
              "files_scanned": files_scanned,
              "duration_seconds": 0,
              "scan_results": [
                  {
                      "scanner": "built_in_quality_gate",
                      "success": True,
                      "skipped": False,
                      "findings": findings,
                  }
              ],
          }
          Path("reports/quality-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

          rows = "\n".join(
              f"<tr><td>{escape(str(f.get('severity','')))}</td><td>{escape(str(f.get('title','')))}</td><td>{escape(str(f.get('file_path','')))}:{escape(str(f.get('line_number') or ''))}</td><td>{escape(str(f.get('recommendation','')))}</td></tr>"
              for f in findings[:500]
          )
          empty_row = '<tr><td colspan="4">No findings.</td></tr>'
          html = (
              "<!doctype html><html><head><meta charset='utf-8'><title>Arya Quality Report</title>"
              "<style>body{font-family:Arial,sans-serif;margin:32px;color:#24292f}"
              "table{border-collapse:collapse;width:100%}td,th{border:1px solid #d0d7de;padding:8px;text-align:left}"
              "th{background:#f6f8fa}</style></head><body>"
              f"<h1>Arya Quality Report</h1><p>Verdict: <strong>{escape(verdict)}</strong></p>"
              f"<p>Files scanned: {files_scanned}. Findings: {len(findings)}.</p>"
              f"<table><thead><tr><th>Severity</th><th>Title</th><th>Location</th><th>Recommendation</th></tr></thead><tbody>{rows or empty_row}</tbody></table>"
              "</body></html>"
          )
          Path("reports/quality-report.html").write_text(html, encoding="utf-8")

          raise SystemExit(exit_code)
          PY
          SCAN_EXIT=$?
          set -e

          echo "SCAN_EXIT=$SCAN_EXIT" >> "$GITHUB_ENV"

      - name: Normalize report filenames
        if: always()
        run: |
          mkdir -p reports

          TARGET_JSON="reports/quality-report.json"
          TARGET_HTML="reports/quality-report.html"

          JSON_REPORT="$(ls -t reports/*.json 2>/dev/null | head -n 1 || true)"
          HTML_REPORT="$(ls -t reports/*.html 2>/dev/null | head -n 1 || true)"

          if [ -n "$JSON_REPORT" ]; then
            if [ "$JSON_REPORT" != "$TARGET_JSON" ]; then
              cp "$JSON_REPORT" "$TARGET_JSON"
            fi
          else
            echo '{"verdict":"error","error":"No JSON report generated"}' > "$TARGET_JSON"
          fi

          if [ -n "$HTML_REPORT" ]; then
            if [ "$HTML_REPORT" != "$TARGET_HTML" ]; then
              cp "$HTML_REPORT" "$TARGET_HTML"
            fi
          else
            echo "<html><body><h1>No HTML report generated</h1></body></html>" > "$TARGET_HTML"
          fi

      - name: Build dashboard quality payload
        if: always()
        run: |
          python - <<'PY'
          import json, os
          from datetime import datetime, timezone
          from pathlib import Path

          report_path = Path("reports/quality-report.json")
          raw = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"verdict": "error"}
          verdict = str(raw.get("verdict") or "error").lower()
          if verdict in {"pass", "passed"}:
              verdict, status, blocking = "pass", "passed", False
          elif verdict in {"warn", "warning"}:
              verdict, status, blocking = "warn", "passed", False
          elif verdict in {"fail", "failed"}:
              verdict, status, blocking = "fail", "failed", True
          else:
              verdict, status, blocking = "error", "error", True

          event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
          pr_number = (event.get("pull_request") or {}).get("number")
          repo = os.environ["GITHUB_REPOSITORY"]
          run_id = os.environ["GITHUB_RUN_ID"]
          findings = []
          for scan in raw.get("scan_results") or []:
              findings.extend(scan.get("findings") or [])

          payload = {
              "repo": repo,
              "branch": os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME"),
              "commit_sha": os.environ["GITHUB_SHA"],
              "pr_number": pr_number,
              "workflow_run_id": run_id,
              "workflow_url": f"https://github.com/{repo}/actions/runs/{run_id}",
              "stage": "quality_gate",
              "status_check": "quality-gate",
              "verdict": verdict,
              "status": status,
              "blocking": blocking,
              "started_at": os.environ.get("SCAN_STARTED_AT"),
              "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "summary": {
                  "total_findings": raw.get("total_findings", len(findings)),
                  "critical": raw.get("critical_count", 0),
                  "high": raw.get("high_count", 0),
                  "medium": raw.get("medium_count", 0),
                  "low": raw.get("low_count", 0),
                  "files_scanned": raw.get("files_scanned", 0),
                  "duration_seconds": raw.get("duration_seconds", 0),
              },
              "findings": findings[:500],
              "artifacts": {
                  "json_report": "quality-report.json",
                  "html_report": "quality-report.html",
                  "github_artifact": "quality-report",
              },
              "raw_report": raw,
          }
          Path("reports/dashboard-quality-payload.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
          summary = {key: payload[key] for key in ["repo", "branch", "commit_sha", "pr_number", "workflow_run_id", "workflow_url", "stage", "status_check", "verdict", "status", "blocking", "started_at", "finished_at", "summary", "artifacts"]}
          Path("reports/workflow-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
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
          DASHBOARD_URL="${{ secrets.DASHBOARD_URL }}"
          DASHBOARD_API_KEY="${{ secrets.DASHBOARD_API_KEY }}"

          if [ -z "$DASHBOARD_URL" ]; then
            echo "::warning::DASHBOARD_URL secret is missing or empty. Report was not sent."
            exit 0
          fi
          case "$DASHBOARD_URL" in
            http://*|https://*) ;;
            *) echo "::warning::DASHBOARD_URL must start with http:// or https://. Report was not sent."; exit 0 ;;
          esac
          if [ -z "$DASHBOARD_API_KEY" ]; then
            echo "::warning::DASHBOARD_API_KEY secret is missing or empty. Report was not sent."
            exit 0
          fi

          HTTP_CODE=$(curl -sS -o /tmp/dashboard_response.txt -w "%{http_code}" \
            --connect-timeout 10 \
            --max-time 30 \
            -X POST "$DASHBOARD_URL/api/quality/report" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $DASHBOARD_API_KEY" \
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
        if: ${{ !startsWith(github.head_ref, 'arya/setup-quality-pipeline') && !startsWith(github.ref_name, 'arya/setup-quality-pipeline') }}
        run: |
          exit "$SCAN_EXIT"

  compiler-check:
    name: compiler-check
    runs-on: ubuntu-latest
    needs: quality-gate

    steps:
      - uses: actions/checkout@v4

      - name: Run compiler check
        run: |
          echo "Compiler check placeholder"
"""



def repo_setup_dict(repo: MonitoredRepository, key: RepositoryApiKey | None = None) -> dict[str, Any]:
    blockers = provisioning_blockers()
    effective_status = repo.setup_status
    if repo.setup_status not in {"ignored", "setup_pr_open", "deprovisioning", "deprovisioned", "cleanup_pr_open", "removed"}:
        if repo.workflow_installed_at and repo.secrets_configured_at and repo.ruleset_configured_at:
            effective_status = "active"

    data: dict[str, Any] = {
        "id": repo.id,
        "tenant_id": repo.tenant_id,
        "installation_id": repo.installation_id,
        "full_name": repo.full_name,
        "owner": repo.owner,
        "repo": repo.repo,
        "default_branch": repo.default_branch,
        "setup_status": effective_status,
        "is_active": repo.is_active,
        "workflow_installed_at": _iso_optional(repo.workflow_installed_at),
        "secrets_configured_at": _iso_optional(repo.secrets_configured_at),
        "ruleset_configured_at": _iso_optional(repo.ruleset_configured_at),
        "last_verified_at": _iso_optional(repo.last_verified_at),
        "api_key_prefix": key.key_prefix if key else None,
        "provisioning_ready": not blockers,
        "provisioning_blockers": blockers,
    }

    optional_fields = {
        "ignored_at": _iso_optional(_get_model_attr(repo, "ignored_at")),
        "deprovisioned_at": _iso_optional(_get_model_attr(repo, "deprovisioned_at")),
        "setup_pr_number": _get_model_attr(repo, "setup_pr_number"),
        "setup_pr_url": _get_model_attr(repo, "setup_pr_url"),
        "setup_pr_branch": _get_model_attr(repo, "setup_pr_branch"),
        "cleanup_pr_number": _get_model_attr(repo, "cleanup_pr_number"),
        "cleanup_pr_url": _get_model_attr(repo, "cleanup_pr_url"),
        "cleanup_pr_branch": _get_model_attr(repo, "cleanup_pr_branch"),
        "last_sync_at": _iso_optional(_get_model_attr(repo, "last_sync_at")),
        "last_deprovision_error": _get_model_attr(repo, "last_deprovision_error"),
    }
    data.update(optional_fields)
    return data

def redact_provisioning_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return a browser-safe copy of a provisioning result."""
    safe = dict(result)
    if "raw_api_key" in safe:
        safe["raw_api_key"] = "[REDACTED]"
    return safe


def sync_installed_repository_records(db: Session, installation: GitHubInstallation) -> list[MonitoredRepository]:
    """Sync the full selected-repository list from GitHub into the DB.

    This operation is idempotent:
    - existing selected repos are updated,
    - new selected repos are inserted,
    - repos removed from the GitHub App installation are marked inactive.
    """
    github = GitHubAppApi()
    token = github.installation_token(installation.installation_id)
    repositories = github.list_installation_repositories(token)
    records = upsert_repositories_from_payload(db, installation, repositories)

    selected_full_names = {record.full_name for record in records}
    existing_for_installation = (
        db.query(MonitoredRepository)
        .filter(
            MonitoredRepository.tenant_id == installation.tenant_id,
            MonitoredRepository.installation_id == installation.id,
        )
        .all()
    )
    inactive_count = 0
    now = datetime.now(timezone.utc)
    for record in existing_for_installation:
        if record.full_name not in selected_full_names and record.is_active:
            record.is_active = False
            record.setup_status = "removed"
            _set_model_attr(record, "last_sync_at", now)
            inactive_count += 1

    record_audit_event(
        db,
        tenant_id=installation.tenant_id,
        event_type="github_installation_repositories_synced",
        target_type="installation",
        target_id=str(installation.installation_id),
        metadata={
            "repository_count": len(records),
            "inactive_repository_count": inactive_count,
        },
    )
    return records


def repository_needs_provisioning(repo: MonitoredRepository) -> bool:
    if repo.setup_status in {"ignored", "setup_pr_open", "deprovisioning", "deprovisioned", "cleanup_pr_open", "removed"}:
        return False
    return not (
        repo.setup_status == "active"
        and repo.workflow_installed_at
        and repo.secrets_configured_at
        and repo.ruleset_configured_at
    )


class GitHubAppApi:
    """Minimal GitHub App API client for repository setup."""

    def __init__(self) -> None:
        self.api_base = "https://api.github.com"

    def _private_key(self) -> str:
        if settings.GITHUB_APP_PRIVATE_KEY:
            return settings.GITHUB_APP_PRIVATE_KEY.replace("\\n", "\n")
        if settings.GITHUB_APP_PRIVATE_KEY_PATH:
            return settings.GITHUB_APP_PRIVATE_KEY_PATH and open(settings.GITHUB_APP_PRIVATE_KEY_PATH, encoding="utf-8").read()
        raise ProvisioningError("GitHub App private key is not configured.")

    def _jwt(self) -> str:
        if not settings.GITHUB_APP_ID:
            raise ProvisioningError("GITHUB_APP_ID is not configured.")
        try:
            import jwt
        except ImportError as exc:
            raise ProvisioningError("PyJWT is required for GitHub App authentication.") from exc

        now = int(time.time())
        return jwt.encode(
            {
                "iat": now - 60,
                "exp": now + 540,
                "iss": settings.GITHUB_APP_ID,
            },
            self._private_key(),
            algorithm="RS256",
        )

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": settings.GITHUB_API_VERSION,
        }

    def installation_token(self, installation_id: int) -> str:
        response = requests.post(
            f"{self.api_base}/app/installations/{installation_id}/access_tokens",
            headers=self._headers(self._jwt()),
            timeout=30,
        )
        if not response.ok:
            raise ProvisioningError(f"Could not create installation token: {response.status_code} {response.text}")
        token = response.json().get("token")
        if not token:
            raise ProvisioningError("GitHub did not return an installation token.")
        return str(token)

    def list_installation_repositories(self, token: str) -> list[dict[str, Any]]:
        repos: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.request(
                "GET",
                f"{self.api_base}/installation/repositories?per_page=100&page={page}",
                token,
            )
            batch = payload.get("repositories", []) if isinstance(payload, dict) else []
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return repos

    def request(self, method: str, url: str, token: str, **kwargs):
        response = requests.request(method, url, headers=self._headers(token), timeout=30, **kwargs)
        if response.status_code >= 400:
            raise GitHubApiError(method, url, response.status_code, response.text)
        if response.status_code == 204 or not response.text:
            return None
        return response.json()

    def get_repository(self, owner: str, repo: str, token: str) -> dict[str, Any]:
        payload = self.request("GET", f"{self.api_base}/repos/{owner}/{repo}", token)
        return payload if isinstance(payload, dict) else {}

    def get_ref(self, owner: str, repo: str, branch: str, token: str) -> dict[str, Any] | None:
        try:
            payload = self.request(
                "GET",
                f"{self.api_base}/repos/{owner}/{repo}/git/ref/heads/{branch}",
                token,
            )
            return payload if isinstance(payload, dict) else None
        except GitHubApiError as exc:
            if exc.status_code == 404:
                return None
            raise

    def ensure_branch(self, owner: str, repo: str, branch: str, base_branch: str, token: str) -> None:
        if self.get_ref(owner, repo, branch, token):
            return
        base_ref = self.get_ref(owner, repo, base_branch, token)
        base_sha = ((base_ref or {}).get("object") or {}).get("sha")
        if not base_sha:
            raise ProvisioningError(f"Could not resolve base branch {base_branch} for {owner}/{repo}.")
        try:
            self.request(
                "POST",
                f"{self.api_base}/repos/{owner}/{repo}/git/refs",
                token,
                json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            )
        except GitHubApiError as exc:
            if exc.status_code == 422 and self.get_ref(owner, repo, branch, token):
                return
            raise

    def get_contents(self, owner: str, repo: str, path: str, token: str, *, ref: str | None = None) -> dict[str, Any] | None:
        params = {"ref": ref} if ref else None
        response = requests.get(
            f"{self.api_base}/repos/{owner}/{repo}/contents/{path}",
            headers=self._headers(token),
            params=params,
            timeout=30,
        )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ProvisioningError(f"Could not read {path}: {response.status_code} {response.text}")
        return response.json()


    def get_content_text(self, owner: str, repo: str, path: str, token: str, *, ref: str | None = None) -> str | None:
        payload = self.get_contents(owner, repo, path, token, ref=ref)
        if not payload:
            return None
        content = payload.get("content")
        if not content:
            return ""
        if payload.get("encoding") == "base64":
            try:
                return base64.b64decode(str(content).replace("\n", "")).decode("utf-8")
            except Exception:
                return None
        return str(content)

    def upsert_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        token: str,
        *,
        branch: str | None = None,
    ) -> None:
        existing = self.get_contents(owner, repo, path, token, ref=branch)
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if branch:
            payload["branch"] = branch
        if existing and existing.get("sha"):
            payload["sha"] = existing["sha"]
        self.request(
            "PUT",
            f"{self.api_base}/repos/{owner}/{repo}/contents/{path}",
            token,
            json=payload,
        )

    def create_or_get_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        base_branch: str,
        title: str,
        body: str,
        token: str,
    ) -> dict[str, Any]:
        existing = self.request(
            "GET",
            f"{self.api_base}/repos/{owner}/{repo}/pulls",
            token,
            params={"state": "open", "head": f"{owner}:{branch}", "base": base_branch},
        )
        if isinstance(existing, list) and existing:
            return existing[0]
        try:
            payload = self.request(
                "POST",
                f"{self.api_base}/repos/{owner}/{repo}/pulls",
                token,
                json={
                    "title": title,
                    "head": branch,
                    "base": base_branch,
                    "body": body,
                    "maintainer_can_modify": True,
                },
            )
            return payload if isinstance(payload, dict) else {}
        except GitHubApiError as exc:
            if exc.status_code == 422:
                existing = self.request(
                    "GET",
                    f"{self.api_base}/repos/{owner}/{repo}/pulls",
                    token,
                    params={"state": "open", "head": f"{owner}:{branch}", "base": base_branch},
                )
                if isinstance(existing, list) and existing:
                    return existing[0]
            raise

    def upsert_file_or_pull_request(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        token: str,
        *,
        default_branch: str | None = None,
    ) -> dict[str, Any]:
        repo_payload = self.get_repository(owner, repo, token)
        base_branch = default_branch or str(repo_payload.get("default_branch") or "main")

        existing_text = self.get_content_text(owner, repo, path, token, ref=base_branch)
        if existing_text == content:
            return {"mode": "already_exists", "base_branch": base_branch}

        try:
            self.upsert_file(owner, repo, path, content, message, token)
            return {"mode": "direct", "base_branch": base_branch}
        except GitHubApiError as exc:
            if not _github_ruleset_blocks_direct_write(exc):
                raise

        branch = "arya/setup-quality-pipeline"
        self.ensure_branch(owner, repo, branch, base_branch, token)
        self.upsert_file(owner, repo, path, content, message, token, branch=branch)
        pull = self.create_or_get_pull_request(
            owner,
            repo,
            branch=branch,
            base_branch=base_branch,
            title="Install Arya quality pipeline workflow",
            body=(
                "This pull request was created automatically by Arya tech Repo Quality Platform.\n\n"
                "It installs or updates the GitHub Actions workflow required for quality-gate enforcement. "
                "Repository secrets are configured by the platform. Final branch protection is applied after "
                "the workflow is present on the default branch."
            ),
            token=token,
        )
        return {
            "mode": "pull_request",
            "branch": branch,
            "base_branch": base_branch,
            "pull_request_number": pull.get("number"),
            "pull_request_url": pull.get("html_url"),
            "reason": "Repository rules require workflow changes through a pull request.",
        }


    def delete_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        token: str,
        *,
        branch: str | None = None,
    ) -> bool:
        existing = self.get_contents(owner, repo, path, token, ref=branch)
        if not existing or not existing.get("sha"):
            return False
        payload: dict[str, Any] = {"message": message, "sha": existing["sha"]}
        if branch:
            payload["branch"] = branch
        self.request(
            "DELETE",
            f"{self.api_base}/repos/{owner}/{repo}/contents/{path}",
            token,
            json=payload,
        )
        return True

    def delete_file_or_pull_request(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        token: str,
        *,
        default_branch: str | None = None,
    ) -> dict[str, Any]:
        try:
            deleted = self.delete_file(owner, repo, path, message, token)
            return {"mode": "direct", "deleted": deleted}
        except GitHubApiError as exc:
            if not _github_ruleset_blocks_direct_write(exc):
                raise

        repo_payload = self.get_repository(owner, repo, token)
        base_branch = default_branch or str(repo_payload.get("default_branch") or "main")
        branch = "arya/remove-quality-pipeline"
        self.ensure_branch(owner, repo, branch, base_branch, token)
        deleted = self.delete_file(owner, repo, path, message, token, branch=branch)
        pull = self.create_or_get_pull_request(
            owner,
            repo,
            branch=branch,
            base_branch=base_branch,
            title="Remove Arya quality pipeline workflow",
            body=(
                "This pull request was created automatically by Arya tech Repo Quality Platform.\n\n"
                "It removes the GitHub Actions workflow installed by the platform. "
                "Pipeline history is preserved in the dashboard."
            ),
            token=token,
        )
        return {
            "mode": "pull_request",
            "deleted": deleted,
            "branch": branch,
            "base_branch": base_branch,
            "pull_request_number": pull.get("number"),
            "pull_request_url": pull.get("html_url"),
            "reason": "Repository rules require workflow changes through a pull request.",
        }

    def _encrypt_secret(self, public_key: str, secret_value: str) -> str:
        try:
            from nacl import encoding, public
        except ImportError as exc:
            raise ProvisioningError("PyNaCl is required to encrypt GitHub Actions secrets.") from exc
        key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
        sealed_box = public.SealedBox(key)
        encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    def set_repo_secret(self, owner: str, repo: str, secret_name: str, secret_value: str, token: str) -> None:
        key_payload = self.request(
            "GET",
            f"{self.api_base}/repos/{owner}/{repo}/actions/secrets/public-key",
            token,
        )
        encrypted_value = self._encrypt_secret(str(key_payload["key"]), secret_value)
        self.request(
            "PUT",
            f"{self.api_base}/repos/{owner}/{repo}/actions/secrets/{secret_name}",
            token,
            json={"encrypted_value": encrypted_value, "key_id": key_payload["key_id"]},
        )

    def list_repo_secret_names(self, owner: str, repo: str, token: str) -> set[str]:
        payload = self.request(
            "GET",
            f"{self.api_base}/repos/{owner}/{repo}/actions/secrets?per_page=100",
            token,
        )
        secrets = payload.get("secrets", []) if isinstance(payload, dict) else []
        return {str(item.get("name")) for item in secrets if item.get("name")}

    def delete_repo_secret(self, owner: str, repo: str, secret_name: str, token: str) -> bool:
        try:
            self.request(
                "DELETE",
                f"{self.api_base}/repos/{owner}/{repo}/actions/secrets/{secret_name}",
                token,
            )
            return True
        except GitHubApiError as exc:
            if exc.status_code == 404:
                return False
            raise

    def _quality_ruleset_payload(self) -> dict[str, Any]:
        return {
            "name": QUALITY_RULESET_NAME,
            "target": "branch",
            "enforcement": "active",
            "conditions": {
                "ref_name": {
                    "include": ["~DEFAULT_BRANCH", "refs/heads/develop"],
                    "exclude": [],
                }
            },
            "rules": [
                {"type": "pull_request"},
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [
                            {"context": "quality-gate"},
                            {"context": "compiler-check"},
                        ],
                    },
                },
            ],
            "bypass_actors": [],
        }

    def get_quality_ruleset(self, owner: str, repo: str, token: str) -> dict[str, Any] | None:
        rulesets = self.request(
            "GET",
            f"{self.api_base}/repos/{owner}/{repo}/rulesets",
            token,
        )
        if not isinstance(rulesets, list):
            return None
        summary = next((item for item in rulesets if item.get("name") == QUALITY_RULESET_NAME), None)
        if not summary or not summary.get("id"):
            return None
        detail = self.request(
            "GET",
            f"{self.api_base}/repos/{owner}/{repo}/rulesets/{summary['id']}",
            token,
        )
        return detail if isinstance(detail, dict) else summary

    def delete_quality_ruleset(self, owner: str, repo: str, token: str) -> bool:
        ruleset = self.get_quality_ruleset(owner, repo, token)
        ruleset_id = ruleset.get("id") if isinstance(ruleset, dict) else None
        if not ruleset_id:
            return False
        self.request(
            "DELETE",
            f"{self.api_base}/repos/{owner}/{repo}/rulesets/{ruleset_id}",
            token,
        )
        return True

    def quality_ruleset_status(self, owner: str, repo: str, token: str) -> dict[str, Any]:
        ruleset = self.get_quality_ruleset(owner, repo, token)
        if not ruleset:
            return {
                "ok": False,
                "name": QUALITY_RULESET_NAME,
                "exists": False,
                "required_status_checks": [],
                "missing_status_checks": sorted(REQUIRED_STATUS_CHECKS),
            }

        contexts: set[str] = set()
        for rule in ruleset.get("rules") or []:
            if rule.get("type") != "required_status_checks":
                continue
            parameters = rule.get("parameters") or {}
            for item in parameters.get("required_status_checks") or []:
                context = item.get("context") if isinstance(item, dict) else None
                if context:
                    contexts.add(str(context))

        missing = sorted(REQUIRED_STATUS_CHECKS - contexts)
        return {
            "ok": not missing and ruleset.get("enforcement") == "active",
            "name": ruleset.get("name") or QUALITY_RULESET_NAME,
            "exists": True,
            "id": ruleset.get("id"),
            "enforcement": ruleset.get("enforcement"),
            "required_status_checks": sorted(contexts),
            "missing_status_checks": missing,
        }

    def upsert_ruleset(self, owner: str, repo: str, token: str) -> None:
        payload = self._quality_ruleset_payload()
        existing_rulesets = self.request(
            "GET",
            f"{self.api_base}/repos/{owner}/{repo}/rulesets",
            token,
        )
        existing = None
        if isinstance(existing_rulesets, list):
            existing = next((item for item in existing_rulesets if item.get("name") == payload["name"]), None)
        if existing and existing.get("id"):
            self.request(
                "PUT",
                f"{self.api_base}/repos/{owner}/{repo}/rulesets/{existing['id']}",
                token,
                json=payload,
            )
            return
        self.request(
            "POST",
            f"{self.api_base}/repos/{owner}/{repo}/rulesets",
            token,
            json=payload,
        )

    def create_ruleset(self, owner: str, repo: str, token: str) -> None:
        payload = {
            "name": "Arya Quality Required Checks",
            "target": "branch",
            "enforcement": "active",
            "conditions": {
                "ref_name": {
                    "include": ["~DEFAULT_BRANCH", "refs/heads/develop"],
                    "exclude": [],
                }
            },
            "rules": [
                {"type": "pull_request"},
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [
                            {"context": "quality-gate"},
                            {"context": "compiler-check"},
                        ],
                    },
                },
            ],
            "bypass_actors": [],
        }
        self.request(
            "POST",
            f"{self.api_base}/repos/{owner}/{repo}/rulesets",
            token,
            json=payload,
        )


def provision_repository(db: Session, repo: MonitoredRepository) -> dict[str, Any]:
    """Configure a repository for autonomous quality reporting.

    Important order: create and verify GitHub Actions secrets before pushing the
    workflow file. A workflow commit immediately triggers GitHub Actions, so if
    the workflow is pushed before DASHBOARD_URL/DASHBOARD_API_KEY exist, the
    first automatic run cannot post to the dashboard and needs a manual rerun.
    """

    key, raw_key = rotate_repository_api_key(db, repo)
    now = datetime.now(timezone.utc)
    workflow = render_caller_workflow()
    result: dict[str, Any] = {
        "repository": repo.full_name,
        "dry_run": settings.PROVISIONING_DRY_RUN,
        "api_key_prefix": key.key_prefix,
        "raw_api_key": raw_key,
        "workflow_path": settings.QUALITY_CALLER_WORKFLOW_PATH,
        "actions": [],
    }

    if repo.setup_status in {"ignored", "deprovisioning", "deprovisioned", "cleanup_pr_open", "removed"}:
        raise ProvisioningError(f"Repository is {repo.setup_status}; restore it before configuring.")

    installation = db.query(GitHubInstallation).filter(GitHubInstallation.id == repo.installation_id).first() if repo.installation_id else None
    if settings.PROVISIONING_DRY_RUN:
        repo.setup_status = "needs_attention"
        repo.last_verified_at = now
        result["actions"] = [
            "would_set_dashboard_url_secret",
            "would_set_dashboard_api_key_secret",
            "would_verify_secrets",
            "would_install_workflow",
            "would_configure_ruleset",
        ]
        record_audit_event(
            db,
            tenant_id=repo.tenant_id,
            event_type="repository_provisioning_dry_run",
            target_type="repository",
            target_id=repo.full_name,
            metadata={"workflow_path": settings.QUALITY_CALLER_WORKFLOW_PATH},
        )
        return result

    if not installation:
        raise ProvisioningError("Repository is not linked to a GitHub App installation.")

    dashboard_url = normalized_public_base_url()

    github = GitHubAppApi()
    token = github.installation_token(installation.installation_id)
    repository_payload = github.get_repository(repo.owner, repo.repo, token)
    repo.default_branch = repository_payload.get("default_branch") or repo.default_branch or "main"

    # 1) Secrets first. This is the core automation fix.
    github.set_repo_secret(repo.owner, repo.repo, "DASHBOARD_URL", dashboard_url, token)
    github.set_repo_secret(repo.owner, repo.repo, "DASHBOARD_API_KEY", raw_key, token)
    if settings.QUALITY_SCANNER_REPO_TOKEN:
        github.set_repo_secret(
            repo.owner,
            repo.repo,
            SCANNER_REPO_SECRET_NAME,
            settings.QUALITY_SCANNER_REPO_TOKEN,
            token,
        )

    secret_names = github.list_repo_secret_names(repo.owner, repo.repo, token)
    missing_secrets = sorted(required_secret_names() - secret_names)
    if missing_secrets:
        raise ProvisioningError(
            "GitHub Actions secrets were not created correctly: " + ", ".join(missing_secrets)
        )

    repo.secrets_configured_at = now
    result["actions"].extend([
        "dashboard_url_secret_configured",
        "dashboard_api_key_secret_configured",
        "secrets_verified_before_workflow",
    ])
    if settings.QUALITY_SCANNER_REPO_TOKEN:
        result["actions"].append("scanner_repo_token_secret_configured")
    result["dashboard_url_configured"] = dashboard_url
    result["secrets_verified"] = sorted(secret_names & required_secret_names())

    # Make the newly rotated repository API key visible to the report receiver
    # before the workflow commit triggers the first GitHub Actions run.
    # Without this commit, the first automatic report can race the DB transaction
    # and get a 401 until the user manually re-runs the job.
    db.flush()
    db.commit()
    result["actions"].append("repo_api_key_committed_before_workflow")

    # 2) Push workflow after secrets exist. This commit may trigger the first automatic run.
    workflow_delivery = github.upsert_file_or_pull_request(
        repo.owner,
        repo.repo,
        settings.QUALITY_CALLER_WORKFLOW_PATH,
        workflow,
        "Install Arya quality pipeline workflow",
        token,
        default_branch=repo.default_branch,
    )
    result["workflow_delivery"] = workflow_delivery
    delivery_mode = workflow_delivery.get("mode")

    if delivery_mode in {"direct", "already_exists"}:
        repo.workflow_installed_at = now
        _clear_setup_pr_fields(repo)
        result["actions"].append("workflow_installed" if delivery_mode == "direct" else "workflow_already_exists")
    else:
        repo.setup_status = "setup_pr_open"
        _set_setup_pr_fields(repo, workflow_delivery)
        result["actions"].append("workflow_pull_request_opened")

    if delivery_mode in {"direct", "already_exists"}:
        # 3) Apply final ruleset only after workflow is present on default branch.
        github.upsert_ruleset(repo.owner, repo.repo, token)
        repo.ruleset_configured_at = now
        repo.setup_status = "active"
        repo.is_active = True
        _set_model_attr(repo, "ignored_at", None)
        _set_model_attr(repo, "deprovisioned_at", None)
        _clear_cleanup_pr_fields(repo)
        _set_model_attr(repo, "last_deprovision_error", None)
        repo.last_verified_at = now
        result["actions"].append("ruleset_configured")
        try:
            verification = verify_repository_setup(db, repo)
            result["verification"] = verification
        except ProvisioningError:
            raise
        except Exception as exc:
            repo.setup_status = "needs_attention"
            result["verification_error"] = str(exc)
    else:
        # Do not apply final required-check ruleset before the workflow reaches the default branch.
        # Otherwise the setup PR can be blocked by the quality gate it is trying to install.
        repo.ruleset_configured_at = None
        repo.last_verified_at = now
        result["actions"].append("ruleset_waiting_for_setup_pr_merge")

    event_type = "repository_provisioned" if delivery_mode in {"direct", "already_exists"} else "repository_provisioning_pr_opened"
    record_audit_event(
        db,
        tenant_id=repo.tenant_id,
        event_type=event_type,
        target_type="repository",
        target_id=repo.full_name,
        metadata={
            "workflow_path": settings.QUALITY_CALLER_WORKFLOW_PATH,
            "workflow_delivery": workflow_delivery,
            "actions": result.get("actions", []),
            "secrets_verified_before_workflow": True,
        },
    )
    return result


def ignore_repository(db: Session, repo: MonitoredRepository, *, user_id: int | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    repo.is_active = False
    repo.setup_status = "ignored"
    _set_model_attr(repo, "ignored_at", now)
    record_audit_event(db, tenant_id=repo.tenant_id, user_id=user_id, event_type="repository_ignored", target_type="repository", target_id=repo.full_name, metadata={"repository": repo.full_name})
    return {"status": "ignored", "repository": repo.full_name}


def restore_repository(db: Session, repo: MonitoredRepository, *, user_id: int | None = None) -> dict[str, Any]:
    repo.is_active = True
    _set_model_attr(repo, "ignored_at", None)
    _set_model_attr(repo, "deprovisioned_at", None)
    _set_model_attr(repo, "last_deprovision_error", None)
    if repo.setup_status in {"ignored", "removed", "deprovisioned", "deprovisioning", "cleanup_pr_open"}:
        repo.setup_status = "discovered"
    record_audit_event(db, tenant_id=repo.tenant_id, user_id=user_id, event_type="repository_restored", target_type="repository", target_id=repo.full_name, metadata={"repository": repo.full_name})
    return {"status": "restored", "repository": repo.full_name}


def _revoke_repository_keys(db: Session, repo: MonitoredRepository, now: datetime) -> int:
    count = 0
    keys = db.query(RepositoryApiKey).filter(RepositoryApiKey.repository_id == repo.id, RepositoryApiKey.status == "active").all()
    for key in keys:
        key.status = "revoked"
        key.revoked_at = now
        count += 1
    return count


def deprovision_repository(db: Session, repo: MonitoredRepository, *, user_id: int | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    result: dict[str, Any] = {"repository": repo.full_name, "dry_run": settings.PROVISIONING_DRY_RUN, "actions": []}

    if settings.PROVISIONING_DRY_RUN:
        repo.setup_status = "deprovisioning"
        repo.last_verified_at = now
        result["actions"] = ["would_delete_dashboard_url_secret", "would_delete_dashboard_api_key_secret", "would_delete_ruleset", "would_remove_workflow", "would_revoke_repo_api_keys"]
        return result

    installation = db.query(GitHubInstallation).filter(GitHubInstallation.id == repo.installation_id).first() if repo.installation_id else None
    if not installation:
        raise ProvisioningError("Repository is not linked to a GitHub App installation.")

    repo.setup_status = "deprovisioning"
    github = GitHubAppApi()
    token = github.installation_token(installation.installation_id)
    try:
        for secret_name in sorted(MANAGED_SECRET_NAMES):
            github.delete_repo_secret(repo.owner, repo.repo, secret_name, token)
        repo.secrets_configured_at = None
        result["actions"].append("secrets_deleted")

        github.delete_quality_ruleset(repo.owner, repo.repo, token)
        repo.ruleset_configured_at = None
        result["actions"].append("ruleset_deleted")

        delivery = github.delete_file_or_pull_request(repo.owner, repo.repo, settings.QUALITY_CALLER_WORKFLOW_PATH, "Remove Arya quality pipeline workflow", token, default_branch=repo.default_branch)
        result["workflow_removal"] = delivery
        if delivery.get("mode") == "pull_request":
            repo.setup_status = "cleanup_pr_open"
            _set_model_attr(repo, "cleanup_pr_number", delivery.get("pull_request_number"))
            _set_model_attr(repo, "cleanup_pr_url", delivery.get("pull_request_url"))
            _set_model_attr(repo, "cleanup_pr_branch", delivery.get("branch"))
            result["actions"].append("cleanup_pull_request_opened")
        else:
            repo.workflow_installed_at = None
            _set_model_attr(repo, "cleanup_pr_number", None)
            _set_model_attr(repo, "cleanup_pr_url", None)
            _set_model_attr(repo, "cleanup_pr_branch", None)
            repo.setup_status = "deprovisioned"
            _set_model_attr(repo, "deprovisioned_at", now)
            repo.is_active = False
            result["actions"].append("workflow_removed")

        revoked_count = _revoke_repository_keys(db, repo, now)
        result["revoked_api_keys"] = revoked_count
        if revoked_count:
            result["actions"].append("repo_api_keys_revoked")
        repo.last_verified_at = now
        _set_model_attr(repo, "last_deprovision_error", None)
        record_audit_event(db, tenant_id=repo.tenant_id, user_id=user_id, event_type="repository_deprovisioned" if repo.setup_status == "deprovisioned" else "repository_cleanup_pr_opened", target_type="repository", target_id=repo.full_name, metadata=result)
        return result
    except Exception as exc:
        repo.setup_status = "needs_attention"
        _set_model_attr(repo, "last_deprovision_error", str(exc))
        record_audit_event(db, tenant_id=repo.tenant_id, user_id=user_id, event_type="repository_deprovision_failed", target_type="repository", target_id=repo.full_name, metadata={"error": str(exc), "repository": repo.full_name})
        raise

def verify_repository_setup(db: Session, repo: MonitoredRepository) -> dict[str, Any]:
    """Verify the live GitHub setup needed for autonomous enforcement."""

    installation = db.query(GitHubInstallation).filter(GitHubInstallation.id == repo.installation_id).first() if repo.installation_id else None
    if not installation:
        raise ProvisioningError("Repository is not linked to a GitHub App installation.")

    github = GitHubAppApi()
    token = github.installation_token(installation.installation_id)
    now = datetime.now(timezone.utc)

    repository_payload = github.get_repository(repo.owner, repo.repo, token)
    repo.default_branch = repository_payload.get("default_branch") or repo.default_branch

    workflow_content = github.get_contents(
        repo.owner,
        repo.repo,
        settings.QUALITY_CALLER_WORKFLOW_PATH,
        token,
        ref=repo.default_branch,
    )
    workflow_ok = bool(workflow_content)

    secret_names = github.list_repo_secret_names(repo.owner, repo.repo, token)
    missing_secrets = sorted(required_secret_names() - secret_names)
    secrets_ok = not missing_secrets

    ruleset_status = github.quality_ruleset_status(repo.owner, repo.repo, token)
    ruleset_ok = bool(ruleset_status.get("ok"))

    active_key = (
        db.query(RepositoryApiKey)
        .filter(
            RepositoryApiKey.repository_id == repo.id,
            RepositoryApiKey.status == "active",
        )
        .order_by(RepositoryApiKey.created_at.desc())
        .first()
    )
    api_key_ok = active_key is not None

    repo.workflow_installed_at = now if workflow_ok else None
    repo.secrets_configured_at = now if secrets_ok else None
    repo.ruleset_configured_at = now if ruleset_ok else None
    repo.last_verified_at = now
    ready = workflow_ok and secrets_ok and ruleset_ok and api_key_ok
    repo.setup_status = "active" if ready else "needs_attention"

    missing: list[str] = []
    if not workflow_ok:
        missing.append(f"workflow file {settings.QUALITY_CALLER_WORKFLOW_PATH}")
    if missing_secrets:
        missing.append("GitHub Actions secrets: " + ", ".join(missing_secrets))
    if not ruleset_ok:
        missing_checks = ruleset_status.get("missing_status_checks") or []
        if missing_checks:
            missing.append("ruleset required checks: " + ", ".join(missing_checks))
        else:
            missing.append("active repository ruleset")
    if not api_key_ok:
        missing.append("active repository API key")

    result = {
        "repository": repo.full_name,
        "ready": ready,
        "status": repo.setup_status,
        "checked_at": now.isoformat(),
        "checks": {
            "workflow": {
                "ok": workflow_ok,
                "path": settings.QUALITY_CALLER_WORKFLOW_PATH,
                "default_branch": repo.default_branch,
            },
            "secrets": {
                "ok": secrets_ok,
                "required": sorted(required_secret_names()),
                "present": sorted(secret_names & required_secret_names()),
                "missing": missing_secrets,
            },
            "ruleset": ruleset_status,
            "api_key": {
                "ok": api_key_ok,
                "prefix": active_key.key_prefix if active_key else None,
            },
        },
        "missing": missing,
    }
    record_audit_event(
        db,
        tenant_id=repo.tenant_id,
        event_type="repository_setup_verified",
        target_type="repository",
        target_id=repo.full_name,
        metadata=result,
    )
    return result


def sync_installed_repositories(db: Session, installation: GitHubInstallation) -> dict[str, Any]:
    records = sync_installed_repository_records(db, installation)
    return {
        "installation_id": installation.installation_id,
        "repository_count": len(records),
        "repositories": [repo_setup_dict(record) for record in records],
    }
