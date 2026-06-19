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
REQUIRED_STATUS_CHECKS = {"quality-gate", "compiler-check"}


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


def provisioning_blockers() -> list[str]:
    blockers: list[str] = []
    if settings.PROVISIONING_DRY_RUN:
        blockers.append("Real provisioning is disabled because PROVISIONING_DRY_RUN is true.")
    if _dashboard_url_is_local(settings.PUBLIC_BASE_URL) and not settings.ALLOW_LOCAL_DASHBOARD_URL_FOR_PROVISIONING:
        blockers.append("PUBLIC_BASE_URL is local; GitHub Actions needs a public HTTPS dashboard URL.")
    if settings.QUALITY_WORKFLOW_MODE == "reusable" and settings.QUALITY_REUSABLE_WORKFLOW_REF.startswith("company/"):
        blockers.append("QUALITY_REUSABLE_WORKFLOW_REF is still the placeholder central workflow reference.")
    if not settings.GITHUB_APP_ID:
        blockers.append("GITHUB_APP_ID is not configured.")
    if not (settings.GITHUB_APP_PRIVATE_KEY or settings.GITHUB_APP_PRIVATE_KEY_PATH):
        blockers.append("GitHub App private key is not configured on the backend.")
    return blockers


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
            "    secrets: inherit",
            "",
        ]
    )


def render_standalone_workflow() -> str:
    return """name: Company Quality Pipeline

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
          pip install cq-pipeline[all] semgrep || true

      - name: Run Code Quality Scan
        run: |
          mkdir -p reports
          echo "SCAN_STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_ENV"

          set +e
          if command -v cq-pipeline >/dev/null 2>&1; then
            cq-pipeline scan --all --format all
            SCAN_EXIT=$?
          else
            echo '{"verdict":"error","error":"cq-pipeline is not installed"}' > reports/quality-report.json
            SCAN_EXIT=1
          fi
          set -e

          echo "SCAN_EXIT=$SCAN_EXIT" >> "$GITHUB_ENV"

      - name: Normalize report filenames
        if: always()
        run: |
          mkdir -p reports
          JSON_REPORT="$(ls -t reports/*.json 2>/dev/null | head -n 1 || true)"
          HTML_REPORT="$(ls -t reports/*.html 2>/dev/null | head -n 1 || true)"

          if [ -n "$JSON_REPORT" ]; then
            cp "$JSON_REPORT" reports/quality-report.json
          else
            echo '{"verdict":"error","error":"No JSON report generated"}' > reports/quality-report.json
          fi

          if [ -n "$HTML_REPORT" ]; then
            cp "$HTML_REPORT" reports/quality-report.html
          else
            echo "<html><body><h1>No HTML report generated</h1></body></html>" > reports/quality-report.html
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
    if repo.workflow_installed_at and repo.secrets_configured_at and repo.ruleset_configured_at:
        effective_status = "active"
    return {
        "id": repo.id,
        "tenant_id": repo.tenant_id,
        "installation_id": repo.installation_id,
        "full_name": repo.full_name,
        "owner": repo.owner,
        "repo": repo.repo,
        "default_branch": repo.default_branch,
        "setup_status": effective_status,
        "is_active": repo.is_active,
        "workflow_installed_at": repo.workflow_installed_at.isoformat() if repo.workflow_installed_at else None,
        "secrets_configured_at": repo.secrets_configured_at.isoformat() if repo.secrets_configured_at else None,
        "ruleset_configured_at": repo.ruleset_configured_at.isoformat() if repo.ruleset_configured_at else None,
        "last_verified_at": repo.last_verified_at.isoformat() if repo.last_verified_at else None,
        "api_key_prefix": key.key_prefix if key else None,
        "provisioning_ready": not blockers,
        "provisioning_blockers": blockers,
    }


def redact_provisioning_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return a browser-safe copy of a provisioning result."""
    safe = dict(result)
    if "raw_api_key" in safe:
        safe["raw_api_key"] = "[REDACTED]"
    return safe


def sync_installed_repository_records(db: Session, installation: GitHubInstallation) -> list[MonitoredRepository]:
    github = GitHubAppApi()
    token = github.installation_token(installation.installation_id)
    repositories = github.list_installation_repositories(token)
    records = upsert_repositories_from_payload(db, installation, repositories)
    record_audit_event(
        db,
        tenant_id=installation.tenant_id,
        event_type="github_installation_repositories_synced",
        target_type="installation",
        target_id=str(installation.installation_id),
        metadata={"repository_count": len(records)},
    )
    return records


def repository_needs_provisioning(repo: MonitoredRepository) -> bool:
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
        try:
            self.upsert_file(owner, repo, path, content, message, token)
            return {"mode": "direct"}
        except GitHubApiError as exc:
            if not _github_ruleset_blocks_direct_write(exc):
                raise

        repo_payload = self.get_repository(owner, repo, token)
        base_branch = default_branch or str(repo_payload.get("default_branch") or "main")
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
                "It installs the GitHub Actions workflow required for quality-gate enforcement. "
                "The dashboard has configured repository secrets and rulesets separately where GitHub permissions allow it."
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

    installation = db.query(GitHubInstallation).filter(GitHubInstallation.id == repo.installation_id).first() if repo.installation_id else None
    if settings.PROVISIONING_DRY_RUN:
        repo.setup_status = "needs_attention"
        repo.last_verified_at = now
        result["actions"] = [
            "would_install_workflow",
            "would_set_dashboard_url_secret",
            "would_set_dashboard_api_key_secret",
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
    if _dashboard_url_is_local(settings.PUBLIC_BASE_URL) and not settings.ALLOW_LOCAL_DASHBOARD_URL_FOR_PROVISIONING:
        raise ProvisioningError(
            "PUBLIC_BASE_URL is local. GitHub Actions cannot post reports to localhost. "
            "Use a deployed HTTPS dashboard URL, or use ngrok/cloudflared for local testing."
        )

    github = GitHubAppApi()
    token = github.installation_token(installation.installation_id)
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
    if workflow_delivery["mode"] == "direct":
        repo.workflow_installed_at = now
        result["actions"].append("workflow_installed")
    else:
        repo.setup_status = "needs_attention"
        result["actions"].append("workflow_pull_request_opened")

    github.set_repo_secret(repo.owner, repo.repo, "DASHBOARD_URL", settings.PUBLIC_BASE_URL.rstrip("/"), token)
    github.set_repo_secret(repo.owner, repo.repo, "DASHBOARD_API_KEY", raw_key, token)
    repo.secrets_configured_at = now
    result["actions"].append("secrets_configured")

    github.upsert_ruleset(repo.owner, repo.repo, token)
    repo.ruleset_configured_at = now
    result["actions"].append("ruleset_configured")

    if workflow_delivery["mode"] == "direct":
        repo.setup_status = "active"
    repo.last_verified_at = now
    event_type = "repository_provisioned" if workflow_delivery["mode"] == "direct" else "repository_provisioning_pr_opened"
    record_audit_event(
        db,
        tenant_id=repo.tenant_id,
        event_type=event_type,
        target_type="repository",
        target_id=repo.full_name,
        metadata={
            "workflow_path": settings.QUALITY_CALLER_WORKFLOW_PATH,
            "workflow_delivery": workflow_delivery,
        },
    )
    return result


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
    missing_secrets = sorted(REQUIRED_SECRET_NAMES - secret_names)
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
                "required": sorted(REQUIRED_SECRET_NAMES),
                "present": sorted(secret_names & REQUIRED_SECRET_NAMES),
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
