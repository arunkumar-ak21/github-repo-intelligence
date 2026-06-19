# import os
# import unittest
# from datetime import datetime, timezone
# from pathlib import Path


# os.environ["ALLOW_UNREGISTERED_REPOS"] = "true"
# os.environ["DASHBOARD_API_KEY"] = "test-key"
# os.environ["MAX_FINDINGS_PER_REPORT"] = "2"
# os.environ["DATABASE_URL"] = "sqlite:///data/test_quality_pipeline.db"

# from core.config import settings
# from core.database import Base, SessionLocal, engine
# from core.models import AnalysisHistory, AuditEvent, GitHubInstallation, MonitoredRepository, PipelineRun, PipelineStage, QualityFinding, RepositoryApiKey, Tenant
# from modules.metadata.models import Commit, Contributor, FileTree, Repository
# from modules.github_app.service import WebhookSignatureError, get_or_create_tenant_for_account, verify_webhook_signature
# from modules.provisioning.automation import run_installation_automation
# import modules.provisioning.service as provisioning_service
# from modules.provisioning.service import provision_repository, render_standalone_workflow, verify_repository_setup
# from modules.quality.normalizer import cap_and_sanitize_findings, run_status_from_stage
# from modules.quality.report_receiver import ensure_repo_allowed, run_to_dict, upsert_stage_report
# from modules.quality.schemas import PipelineStagePayload
# from modules.security.sanitizer import sanitize_payload
# from modules.tenancy.api_keys import ReportAuthError, create_repository_api_key, validate_report_token
# from server import _history_to_dict


# TEST_DB = Path("data/test_quality_pipeline.db")


# class QualityPipelineTests(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         TEST_DB.parent.mkdir(parents=True, exist_ok=True)

#     def setUp(self):
#         Base.metadata.drop_all(bind=engine)
#         Base.metadata.create_all(bind=engine)

#     def tearDown(self):
#         Base.metadata.drop_all(bind=engine)

#     @classmethod
#     def tearDownClass(cls):
#         engine.dispose()
#         if TEST_DB.exists():
#             TEST_DB.unlink()

#     def test_secret_payload_is_redacted_recursively(self):
#         payload = {
#             "token": "raw-token",
#             "nested": {"client_secret": "raw-secret"},
#             "findings": [
#                 {
#                     "category": "secrets",
#                     "scanner": "gitleaks",
#                     "line": "AWS_SECRET_ACCESS_KEY=raw-secret",
#                 }
#             ],
#         }

#         sanitized = sanitize_payload(payload)

#         self.assertEqual(sanitized["token"], "[REDACTED]")
#         self.assertEqual(sanitized["nested"]["client_secret"], "[REDACTED]")
#         self.assertEqual(sanitized["findings"][0]["line"], "[REDACTED]")
#         self.assertNotIn("raw-secret", str(sanitized))

#     def test_findings_are_sorted_capped_and_sanitized(self):
#         findings = [
#             {"severity": "low", "scanner": "lint", "message": "low"},
#             {"severity": "critical", "scanner": "gitleaks", "message": "secret", "value": "raw"},
#             {"severity": "high", "scanner": "bandit", "message": "high"},
#         ]

#         capped = cap_and_sanitize_findings(findings)

#         self.assertEqual([item["severity"] for item in capped], ["critical", "high"])
#         self.assertNotIn("raw", str(capped))

#     def test_compiler_check_pass_marks_pipeline_completed(self):
#         stage = PipelineStagePayload(
#             stage="compiler_check",
#             status="passed",
#             repo="owner/repo",
#             branch="main",
#             commit_sha="abc123",
#             workflow_run_id="100",
#         )

#         self.assertEqual(run_status_from_stage(stage), "completed")

#     def test_duplicate_quality_report_updates_existing_rows(self):
#         db = SessionLocal()
#         try:
#             payload = PipelineStagePayload(
#                 stage="quality_gate",
#                 status="failed",
#                 blocking=True,
#                 repo="owner/repo",
#                 branch="feature/test",
#                 commit_sha="abc123",
#                 workflow_run_id="100",
#                 summary={"critical": 1, "total_findings": 1},
#                 findings=[
#                     {
#                         "scanner": "gitleaks",
#                         "severity": "critical",
#                         "rule_id": "secret",
#                         "message": "Secret detected",
#                         "file_path": "app.py",
#                         "line_number": 4,
#                         "value": "AKIA1234567890SECRET",
#                     }
#                 ],
#             )
#             raw = payload.model_dump(mode="json") | {"token": "AKIA1234567890SECRET"}

#             upsert_stage_report(db, payload, raw)
#             payload.summary["critical"] = 2
#             upsert_stage_report(db, payload, raw)

#             self.assertEqual(db.query(MonitoredRepository).count(), 1)
#             self.assertEqual(db.query(PipelineRun).count(), 1)
#             self.assertEqual(db.query(PipelineStage).count(), 1)
#             self.assertEqual(db.query(QualityFinding).count(), 1)
#             self.assertEqual(db.query(Tenant).count(), 1)
#             self.assertEqual(db.query(AuditEvent).count(), 1)

#             run = db.query(PipelineRun).one()
#             stage = db.query(PipelineStage).one()
#             finding = db.query(QualityFinding).one()
#             repo = db.query(MonitoredRepository).one()

#             self.assertEqual(run.tenant_id, repo.tenant_id)
#             self.assertEqual(run.repository_id, repo.id)
#             self.assertEqual(stage.tenant_id, repo.tenant_id)
#             self.assertEqual(finding.tenant_id, repo.tenant_id)
#             self.assertEqual(run.overall_status, "failed")
#             self.assertEqual(stage.summary_json["critical"], 2)
#             self.assertEqual(finding.scanner, "gitleaks")
#             self.assertNotIn("AKIA1234567890SECRET", str(stage.raw_json))
#             self.assertNotIn("AKIA1234567890SECRET", str(run.raw_json))
#         finally:
#             db.close()

#     def test_compiler_report_findings_are_stored_with_stage_details(self):
#         db = SessionLocal()
#         try:
#             tenant = Tenant(name="Alpha", slug="alpha")
#             db.add(tenant)
#             db.flush()
#             repo = ensure_repo_allowed(db, "owner/repo", tenant)
#             payload = PipelineStagePayload(
#                 stage="compiler_check",
#                 status="failed",
#                 blocking=True,
#                 repo="owner/repo",
#                 branch="feature/compiler",
#                 commit_sha="abc123",
#                 workflow_run_id="100",
#                 summary={"error_count": 1, "command": "npm run build"},
#                 findings=[
#                     {
#                         "scanner": "typescript",
#                         "severity": "high",
#                         "rule_id": "TS2304",
#                         "title": "Cannot find name",
#                         "message": "Cannot find name 'foo'.",
#                         "file_path": "src/app.ts",
#                         "line_number": 12,
#                         "recommendation": "Import or define the missing symbol.",
#                     }
#                 ],
#             )

#             run, _stage = upsert_stage_report(db, payload, payload.model_dump(mode="json"), repo)
#             details = run_to_dict(db, run, include_details=True)

#             compiler_stage = next(stage for stage in details["stages"] if stage["stage_name"] == "compiler_check")
#             self.assertEqual(compiler_stage["findings"][0]["rule_id"], "TS2304")
#             self.assertEqual(db.query(QualityFinding).count(), 1)
#             self.assertEqual(run.overall_status, "failed")
#         finally:
#             db.close()

#     def test_history_payload_can_include_deep_metadata_details(self):
#         db = SessionLocal()
#         try:
#             repo = Repository(
#                 owner="owner",
#                 name="repo",
#                 full_name="owner/repo",
#                 description="Repository description",
#                 url="https://github.com/owner/repo",
#                 language="Python",
#                 stars=42,
#                 forks=7,
#                 open_issues=3,
#                 readme="# README",
#                 topics="security, ci",
#                 default_branch="main",
#                 license_name="MIT",
#                 is_archived=False,
#             )
#             db.add(repo)
#             db.commit()
#             db.refresh(repo)

#             db.add(Commit(
#                 repo_id=repo.id,
#                 commit_hash="abc123",
#                 author_name="Dev",
#                 message="Initial commit",
#                 timestamp=datetime.now(timezone.utc),
#             ))
#             db.add(Contributor(
#                 repo_id=repo.id,
#                 username="dev",
#                 profile_url="https://github.com/dev",
#                 avatar_url="https://example.com/avatar.png",
#                 total_commits=10,
#             ))
#             db.add(FileTree(
#                 repo_id=repo.id,
#                 file_path="app.py",
#                 file_type="blob",
#                 size=120,
#             ))
#             history = AnalysisHistory(
#                 repo="owner/repo",
#                 metadata_json={"repo_id": repo.id, "language": "Python"},
#                 cicd_json={},
#                 dependencies_json={},
#             )
#             db.add(history)
#             db.commit()
#             db.refresh(history)

#             payload = _history_to_dict(history, include_metadata_details=True)

#             self.assertEqual(payload["history_id"], history.id)
#             self.assertEqual(payload["metadata_details"]["repository"]["readme"], "# README")
#             self.assertEqual(payload["metadata_details"]["contributors"][0]["username"], "dev")
#             self.assertEqual(payload["metadata_details"]["commits"][0]["commit_hash"], "abc123")
#             self.assertEqual(payload["metadata_details"]["file_trees"][0]["file_path"], "app.py")
#         finally:
#             db.close()

#     def test_same_repo_can_be_registered_for_different_tenants(self):
#         db = SessionLocal()
#         try:
#             alpha = Tenant(name="Alpha", slug="alpha")
#             beta = Tenant(name="Beta", slug="beta")
#             db.add_all([alpha, beta])
#             db.flush()

#             alpha_repo = ensure_repo_allowed(db, "owner/repo", alpha)
#             beta_repo = ensure_repo_allowed(db, "owner/repo", beta)

#             self.assertNotEqual(alpha_repo.id, beta_repo.id)
#             self.assertEqual(alpha_repo.full_name, beta_repo.full_name)
#             self.assertEqual(db.query(MonitoredRepository).count(), 2)
#         finally:
#             db.rollback()
#             db.close()

#     def test_repo_scoped_api_key_validates_only_matching_repository(self):
#         db = SessionLocal()
#         try:
#             tenant = Tenant(name="Alpha", slug="alpha")
#             db.add(tenant)
#             db.flush()
#             repo = ensure_repo_allowed(db, "owner/repo", tenant)
#             _key, raw_key = create_repository_api_key(db, repo)

#             resolved = validate_report_token(db, raw_key, "owner/repo")

#             self.assertEqual(resolved.id, repo.id)
#             with self.assertRaises(ReportAuthError):
#                 validate_report_token(db, raw_key, "owner/other")
#         finally:
#             db.rollback()
#             db.close()

#     def test_webhook_signature_verification_uses_hmac_sha256(self):
#         original = settings.GITHUB_APP_WEBHOOK_SECRET
#         try:
#             settings.GITHUB_APP_WEBHOOK_SECRET = "webhook-secret"
#             body = b'{"action":"created"}'
#             import hashlib
#             import hmac

#             signature = "sha256=" + hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()
#             verify_webhook_signature(body, signature)
#             with self.assertRaises(WebhookSignatureError):
#                 verify_webhook_signature(body, "sha256=bad")
#         finally:
#             settings.GITHUB_APP_WEBHOOK_SECRET = original

#     def test_github_installation_reuses_existing_account_tenant(self):
#         db = SessionLocal()
#         try:
#             tenant = Tenant(
#                 name="arunkumar-ak21",
#                 slug="github-arunkumar-ak21",
#                 github_account_id=158503662,
#                 github_account_login="arunkumar-ak21",
#                 github_account_type="User",
#             )
#             db.add(tenant)
#             db.flush()

#             resolved = get_or_create_tenant_for_account(
#                 db,
#                 {"id": 158503662, "login": "arunkumar-ak21", "type": "User"},
#             )

#             self.assertEqual(resolved.id, tenant.id)
#             self.assertEqual(db.query(Tenant).count(), 1)
#         finally:
#             db.rollback()
#             db.close()

#     def test_provisioning_dry_run_creates_repo_key_without_external_calls(self):
#         original = settings.PROVISIONING_DRY_RUN
#         try:
#             settings.PROVISIONING_DRY_RUN = True
#             db = SessionLocal()
#             try:
#                 tenant = Tenant(name="Alpha", slug="alpha")
#                 db.add(tenant)
#                 db.flush()
#                 repo = ensure_repo_allowed(db, "owner/repo", tenant)

#                 result = provision_repository(db, repo)

#                 self.assertTrue(result["dry_run"])
#                 self.assertTrue(result["raw_api_key"].startswith(result["api_key_prefix"]))
#                 self.assertEqual(repo.setup_status, "needs_attention")
#                 self.assertEqual(db.query(RepositoryApiKey).count(), 1)
#             finally:
#                 db.rollback()
#                 db.close()
#         finally:
#             settings.PROVISIONING_DRY_RUN = original

#     def test_installation_automation_dry_run_redacts_repo_api_key(self):
#         original_dry_run = settings.PROVISIONING_DRY_RUN
#         original_reprovision = settings.AUTO_REPROVISION_ACTIVE_REPOS
#         try:
#             settings.PROVISIONING_DRY_RUN = True
#             settings.AUTO_REPROVISION_ACTIVE_REPOS = False
#             db = SessionLocal()
#             try:
#                 tenant = Tenant(name="Alpha", slug="alpha")
#                 db.add(tenant)
#                 db.flush()
#                 installation = GitHubInstallation(
#                     tenant_id=tenant.id,
#                     installation_id=123,
#                     account_login="alpha",
#                     account_type="Organization",
#                 )
#                 db.add(installation)
#                 db.flush()
#                 repo = ensure_repo_allowed(db, "owner/repo", tenant)
#                 repo.installation_id = installation.id

#                 result = run_installation_automation(
#                     db,
#                     installation,
#                     source="test",
#                     auto_sync=False,
#                     auto_provision=True,
#                 )

#                 self.assertEqual(result["provisioned_repository_count"], 1)
#                 self.assertEqual(result["repositories"][0]["status"], "dry_run")
#                 self.assertEqual(result["repositories"][0]["result"]["raw_api_key"], "[REDACTED]")
#                 self.assertEqual(db.query(RepositoryApiKey).count(), 1)
#             finally:
#                 db.rollback()
#                 db.close()
#         finally:
#             settings.PROVISIONING_DRY_RUN = original_dry_run
#             settings.AUTO_REPROVISION_ACTIVE_REPOS = original_reprovision

#     def test_verify_repository_setup_marks_repo_active_when_live_checks_pass(self):
#         original_github = provisioning_service.GitHubAppApi

#         class FakeGitHubAppApi:
#             def installation_token(self, installation_id):
#                 return "installation-token"

#             def get_repository(self, owner, repo, token):
#                 return {"default_branch": "main"}

#             def get_contents(self, owner, repo, path, token, *, ref=None):
#                 return {"sha": "workflow-sha"}

#             def list_repo_secret_names(self, owner, repo, token):
#                 return {"DASHBOARD_URL", "DASHBOARD_API_KEY"}

#             def quality_ruleset_status(self, owner, repo, token):
#                 return {
#                     "ok": True,
#                     "name": "Arya Quality Required Checks",
#                     "exists": True,
#                     "enforcement": "active",
#                     "required_status_checks": ["compiler-check", "quality-gate"],
#                     "missing_status_checks": [],
#                 }

#         try:
#             provisioning_service.GitHubAppApi = FakeGitHubAppApi
#             db = SessionLocal()
#             try:
#                 tenant = Tenant(name="Alpha", slug="alpha")
#                 db.add(tenant)
#                 db.flush()
#                 installation = GitHubInstallation(
#                     tenant_id=tenant.id,
#                     installation_id=123,
#                     account_login="alpha",
#                     account_type="Organization",
#                 )
#                 db.add(installation)
#                 db.flush()
#                 repo = ensure_repo_allowed(db, "owner/repo", tenant)
#                 repo.installation_id = installation.id
#                 create_repository_api_key(db, repo)

#                 verification = verify_repository_setup(db, repo)

#                 self.assertTrue(verification["ready"])
#                 self.assertEqual(repo.setup_status, "active")
#                 self.assertIsNotNone(repo.workflow_installed_at)
#                 self.assertIsNotNone(repo.secrets_configured_at)
#                 self.assertIsNotNone(repo.ruleset_configured_at)
#             finally:
#                 db.rollback()
#                 db.close()
#         finally:
#             provisioning_service.GitHubAppApi = original_github


# if __name__ == "__main__":
#     unittest.main()

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path


os.environ["ALLOW_UNREGISTERED_REPOS"] = "true"
os.environ["DASHBOARD_API_KEY"] = "test-key"
os.environ["MAX_FINDINGS_PER_REPORT"] = "2"
os.environ["DATABASE_URL"] = "sqlite:///data/test_quality_pipeline.db"

from core.config import settings
from core.database import Base, SessionLocal, engine
from core.models import AnalysisHistory, AuditEvent, GitHubInstallation, MonitoredRepository, PipelineRun, PipelineStage, QualityFinding, RepositoryApiKey, Tenant
from modules.metadata.models import Commit, Contributor, FileTree, Repository
from modules.github_app.service import WebhookSignatureError, get_or_create_tenant_for_account, verify_webhook_signature, upsert_repositories_from_payload, handle_installation_repositories_webhook
from modules.provisioning.automation import run_installation_automation
import modules.provisioning.service as provisioning_service
from modules.provisioning.service import provision_repository, render_standalone_workflow, verify_repository_setup
from modules.quality.normalizer import cap_and_sanitize_findings, run_status_from_stage
from modules.quality.report_receiver import ensure_repo_allowed, run_to_dict, upsert_stage_report
from modules.quality.schemas import PipelineStagePayload
from modules.security.sanitizer import sanitize_payload
from modules.tenancy.api_keys import ReportAuthError, create_repository_api_key, validate_report_token
from server import _history_to_dict


TEST_DB = Path("data/test_quality_pipeline.db")


class QualityPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_DB.parent.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        if TEST_DB.exists():
            TEST_DB.unlink()

    def test_secret_payload_is_redacted_recursively(self):
        payload = {
            "token": "raw-token",
            "nested": {"client_secret": "raw-secret"},
            "findings": [
                {
                    "category": "secrets",
                    "scanner": "gitleaks",
                    "line": "AWS_SECRET_ACCESS_KEY=raw-secret",
                }
            ],
        }

        sanitized = sanitize_payload(payload)

        self.assertEqual(sanitized["token"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["client_secret"], "[REDACTED]")
        self.assertEqual(sanitized["findings"][0]["line"], "[REDACTED]")
        self.assertNotIn("raw-secret", str(sanitized))

    def test_findings_are_sorted_capped_and_sanitized(self):
        findings = [
            {"severity": "low", "scanner": "lint", "message": "low"},
            {"severity": "critical", "scanner": "gitleaks", "message": "secret", "value": "raw"},
            {"severity": "high", "scanner": "bandit", "message": "high"},
        ]

        capped = cap_and_sanitize_findings(findings)

        self.assertEqual([item["severity"] for item in capped], ["critical", "high"])
        self.assertNotIn("raw", str(capped))

    def test_compiler_check_pass_marks_pipeline_completed(self):
        stage = PipelineStagePayload(
            stage="compiler_check",
            status="passed",
            repo="owner/repo",
            branch="main",
            commit_sha="abc123",
            workflow_run_id="100",
        )

        self.assertEqual(run_status_from_stage(stage), "completed")

    def test_duplicate_quality_report_updates_existing_rows(self):
        db = SessionLocal()
        try:
            payload = PipelineStagePayload(
                stage="quality_gate",
                status="failed",
                blocking=True,
                repo="owner/repo",
                branch="feature/test",
                commit_sha="abc123",
                workflow_run_id="100",
                summary={"critical": 1, "total_findings": 1},
                findings=[
                    {
                        "scanner": "gitleaks",
                        "severity": "critical",
                        "rule_id": "secret",
                        "message": "Secret detected",
                        "file_path": "app.py",
                        "line_number": 4,
                        "value": "AKIA1234567890SECRET",
                    }
                ],
            )
            raw = payload.model_dump(mode="json") | {"token": "AKIA1234567890SECRET"}

            upsert_stage_report(db, payload, raw)
            payload.summary["critical"] = 2
            upsert_stage_report(db, payload, raw)

            self.assertEqual(db.query(MonitoredRepository).count(), 1)
            self.assertEqual(db.query(PipelineRun).count(), 1)
            self.assertEqual(db.query(PipelineStage).count(), 1)
            self.assertEqual(db.query(QualityFinding).count(), 1)
            self.assertEqual(db.query(Tenant).count(), 1)
            self.assertEqual(db.query(AuditEvent).count(), 1)

            run = db.query(PipelineRun).one()
            stage = db.query(PipelineStage).one()
            finding = db.query(QualityFinding).one()
            repo = db.query(MonitoredRepository).one()

            self.assertEqual(run.tenant_id, repo.tenant_id)
            self.assertEqual(run.repository_id, repo.id)
            self.assertEqual(stage.tenant_id, repo.tenant_id)
            self.assertEqual(finding.tenant_id, repo.tenant_id)
            self.assertEqual(run.overall_status, "failed")
            self.assertEqual(stage.summary_json["critical"], 2)
            self.assertEqual(finding.scanner, "gitleaks")
            self.assertNotIn("AKIA1234567890SECRET", str(stage.raw_json))
            self.assertNotIn("AKIA1234567890SECRET", str(run.raw_json))
        finally:
            db.close()

    def test_compiler_report_findings_are_stored_with_stage_details(self):
        db = SessionLocal()
        try:
            tenant = Tenant(name="Alpha", slug="alpha")
            db.add(tenant)
            db.flush()
            repo = ensure_repo_allowed(db, "owner/repo", tenant)
            payload = PipelineStagePayload(
                stage="compiler_check",
                status="failed",
                blocking=True,
                repo="owner/repo",
                branch="feature/compiler",
                commit_sha="abc123",
                workflow_run_id="100",
                summary={"error_count": 1, "command": "npm run build"},
                findings=[
                    {
                        "scanner": "typescript",
                        "severity": "high",
                        "rule_id": "TS2304",
                        "title": "Cannot find name",
                        "message": "Cannot find name 'foo'.",
                        "file_path": "src/app.ts",
                        "line_number": 12,
                        "recommendation": "Import or define the missing symbol.",
                    }
                ],
            )

            run, _stage = upsert_stage_report(db, payload, payload.model_dump(mode="json"), repo)
            details = run_to_dict(db, run, include_details=True)

            compiler_stage = next(stage for stage in details["stages"] if stage["stage_name"] == "compiler_check")
            self.assertEqual(compiler_stage["findings"][0]["rule_id"], "TS2304")
            self.assertEqual(db.query(QualityFinding).count(), 1)
            self.assertEqual(run.overall_status, "failed")
        finally:
            db.close()

    def test_history_payload_can_include_deep_metadata_details(self):
        db = SessionLocal()
        try:
            repo = Repository(
                owner="owner",
                name="repo",
                full_name="owner/repo",
                description="Repository description",
                url="https://github.com/owner/repo",
                language="Python",
                stars=42,
                forks=7,
                open_issues=3,
                readme="# README",
                topics="security, ci",
                default_branch="main",
                license_name="MIT",
                is_archived=False,
            )
            db.add(repo)
            db.commit()
            db.refresh(repo)

            db.add(Commit(
                repo_id=repo.id,
                commit_hash="abc123",
                author_name="Dev",
                message="Initial commit",
                timestamp=datetime.now(timezone.utc),
            ))
            db.add(Contributor(
                repo_id=repo.id,
                username="dev",
                profile_url="https://github.com/dev",
                avatar_url="https://example.com/avatar.png",
                total_commits=10,
            ))
            db.add(FileTree(
                repo_id=repo.id,
                file_path="app.py",
                file_type="blob",
                size=120,
            ))
            history = AnalysisHistory(
                repo="owner/repo",
                metadata_json={"repo_id": repo.id, "language": "Python"},
                cicd_json={},
                dependencies_json={},
            )
            db.add(history)
            db.commit()
            db.refresh(history)

            payload = _history_to_dict(history, include_metadata_details=True)

            self.assertEqual(payload["history_id"], history.id)
            self.assertEqual(payload["metadata_details"]["repository"]["readme"], "# README")
            self.assertEqual(payload["metadata_details"]["contributors"][0]["username"], "dev")
            self.assertEqual(payload["metadata_details"]["commits"][0]["commit_hash"], "abc123")
            self.assertEqual(payload["metadata_details"]["file_trees"][0]["file_path"], "app.py")
        finally:
            db.close()

    def test_same_repo_can_be_registered_for_different_tenants(self):
        db = SessionLocal()
        try:
            alpha = Tenant(name="Alpha", slug="alpha")
            beta = Tenant(name="Beta", slug="beta")
            db.add_all([alpha, beta])
            db.flush()

            alpha_repo = ensure_repo_allowed(db, "owner/repo", alpha)
            beta_repo = ensure_repo_allowed(db, "owner/repo", beta)

            self.assertNotEqual(alpha_repo.id, beta_repo.id)
            self.assertEqual(alpha_repo.full_name, beta_repo.full_name)
            self.assertEqual(db.query(MonitoredRepository).count(), 2)
        finally:
            db.rollback()
            db.close()

    def test_repo_scoped_api_key_validates_only_matching_repository(self):
        db = SessionLocal()
        try:
            tenant = Tenant(name="Alpha", slug="alpha")
            db.add(tenant)
            db.flush()
            repo = ensure_repo_allowed(db, "owner/repo", tenant)
            _key, raw_key = create_repository_api_key(db, repo)

            resolved = validate_report_token(db, raw_key, "owner/repo")

            self.assertEqual(resolved.id, repo.id)
            with self.assertRaises(ReportAuthError):
                validate_report_token(db, raw_key, "owner/other")
        finally:
            db.rollback()
            db.close()

    def test_webhook_signature_verification_uses_hmac_sha256(self):
        original = settings.GITHUB_APP_WEBHOOK_SECRET
        try:
            settings.GITHUB_APP_WEBHOOK_SECRET = "webhook-secret"
            body = b'{"action":"created"}'
            import hashlib
            import hmac

            signature = "sha256=" + hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()
            verify_webhook_signature(body, signature)
            with self.assertRaises(WebhookSignatureError):
                verify_webhook_signature(body, "sha256=bad")
        finally:
            settings.GITHUB_APP_WEBHOOK_SECRET = original

    def test_github_installation_reuses_existing_account_tenant(self):
        db = SessionLocal()
        try:
            tenant = Tenant(
                name="arunkumar-ak21",
                slug="github-arunkumar-ak21",
                github_account_id=158503662,
                github_account_login="arunkumar-ak21",
                github_account_type="User",
            )
            db.add(tenant)
            db.flush()

            resolved = get_or_create_tenant_for_account(
                db,
                {"id": 158503662, "login": "arunkumar-ak21", "type": "User"},
            )

            self.assertEqual(resolved.id, tenant.id)
            self.assertEqual(db.query(Tenant).count(), 1)
        finally:
            db.rollback()
            db.close()

    def test_provisioning_dry_run_creates_repo_key_without_external_calls(self):
        original = settings.PROVISIONING_DRY_RUN
        try:
            settings.PROVISIONING_DRY_RUN = True
            db = SessionLocal()
            try:
                tenant = Tenant(name="Alpha", slug="alpha")
                db.add(tenant)
                db.flush()
                repo = ensure_repo_allowed(db, "owner/repo", tenant)

                result = provision_repository(db, repo)

                self.assertTrue(result["dry_run"])
                self.assertTrue(result["raw_api_key"].startswith(result["api_key_prefix"]))
                self.assertEqual(repo.setup_status, "needs_attention")
                self.assertEqual(db.query(RepositoryApiKey).count(), 1)
            finally:
                db.rollback()
                db.close()
        finally:
            settings.PROVISIONING_DRY_RUN = original

    def test_installation_automation_dry_run_redacts_repo_api_key(self):
        original_dry_run = settings.PROVISIONING_DRY_RUN
        original_reprovision = settings.AUTO_REPROVISION_ACTIVE_REPOS
        try:
            settings.PROVISIONING_DRY_RUN = True
            settings.AUTO_REPROVISION_ACTIVE_REPOS = False
            db = SessionLocal()
            try:
                tenant = Tenant(name="Alpha", slug="alpha")
                db.add(tenant)
                db.flush()
                installation = GitHubInstallation(
                    tenant_id=tenant.id,
                    installation_id=123,
                    account_login="alpha",
                    account_type="Organization",
                )
                db.add(installation)
                db.flush()
                repo = ensure_repo_allowed(db, "owner/repo", tenant)
                repo.installation_id = installation.id

                result = run_installation_automation(
                    db,
                    installation,
                    source="test",
                    auto_sync=False,
                    auto_provision=True,
                )

                self.assertEqual(result["provisioned_repository_count"], 1)
                self.assertEqual(result["repositories"][0]["status"], "dry_run")
                self.assertEqual(result["repositories"][0]["result"]["raw_api_key"], "[REDACTED]")
                self.assertEqual(db.query(RepositoryApiKey).count(), 1)
            finally:
                db.rollback()
                db.close()
        finally:
            settings.PROVISIONING_DRY_RUN = original_dry_run
            settings.AUTO_REPROVISION_ACTIVE_REPOS = original_reprovision

    def test_github_app_repo_upsert_is_idempotent(self):
        db = SessionLocal()
        try:
            tenant = Tenant(name="Alpha", slug="alpha")
            db.add(tenant)
            db.flush()
            installation = GitHubInstallation(
                tenant_id=tenant.id,
                installation_id=12345,
                account_login="alpha",
                account_type="User",
            )
            db.add(installation)
            db.flush()

            first = upsert_repositories_from_payload(
                db,
                installation,
                [{"full_name": "owner/repo", "default_branch": "main"}],
            )
            first_id = first[0].id

            second = upsert_repositories_from_payload(
                db,
                installation,
                [
                    {"full_name": "owner/repo", "default_branch": "develop"},
                    {"full_name": "owner/second", "default_branch": "main"},
                ],
            )

            self.assertEqual(db.query(MonitoredRepository).count(), 2)
            self.assertEqual(second[0].id, first_id)
            self.assertEqual(second[0].default_branch, "develop")
            self.assertTrue(second[0].is_active)
        finally:
            db.rollback()
            db.close()

    def test_github_app_repo_upsert_adopts_legacy_tenantless_row(self):
        db = SessionLocal()
        try:
            tenant = Tenant(name="Alpha", slug="alpha")
            db.add(tenant)
            db.flush()
            installation = GitHubInstallation(
                tenant_id=tenant.id,
                installation_id=12345,
                account_login="alpha",
                account_type="User",
            )
            db.add(installation)
            db.flush()

            legacy = MonitoredRepository(
                tenant_id=None,
                full_name="owner/repo",
                owner="owner",
                repo="repo",
                setup_status="pending",
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(legacy)
            db.flush()
            legacy_id = legacy.id

            records = upsert_repositories_from_payload(
                db,
                installation,
                [{"full_name": "owner/repo", "default_branch": "main"}],
            )

            self.assertEqual(db.query(MonitoredRepository).count(), 1)
            self.assertEqual(records[0].id, legacy_id)
            self.assertEqual(records[0].tenant_id, tenant.id)
            self.assertEqual(records[0].installation_id, installation.id)
        finally:
            db.rollback()
            db.close()

    def test_removed_installation_repository_is_marked_inactive(self):
        db = SessionLocal()
        try:
            payload = {
                "installation": {
                    "id": 12345,
                    "account": {"id": 99, "login": "alpha", "type": "User"},
                },
                "repositories_added": [{"full_name": "owner/repo"}],
                "repositories_removed": [],
            }
            installation = handle_installation_repositories_webhook(db, payload)
            repo = db.query(MonitoredRepository).filter(MonitoredRepository.full_name == "owner/repo").first()
            self.assertIsNotNone(installation)
            self.assertIsNotNone(repo)
            self.assertTrue(repo.is_active)

            handle_installation_repositories_webhook(
                db,
                {
                    "installation": {
                        "id": 12345,
                        "account": {"id": 99, "login": "alpha", "type": "User"},
                    },
                    "repositories_added": [],
                    "repositories_removed": [{"full_name": "owner/repo"}],
                },
            )

            self.assertFalse(repo.is_active)
            self.assertEqual(repo.setup_status, "needs_attention")
        finally:
            db.rollback()
            db.close()

    def test_verify_repository_setup_marks_repo_active_when_live_checks_pass(self):
        original_github = provisioning_service.GitHubAppApi

        class FakeGitHubAppApi:
            def installation_token(self, installation_id):
                return "installation-token"

            def get_repository(self, owner, repo, token):
                return {"default_branch": "main"}

            def get_contents(self, owner, repo, path, token, *, ref=None):
                return {"sha": "workflow-sha"}

            def list_repo_secret_names(self, owner, repo, token):
                return {"DASHBOARD_URL", "DASHBOARD_API_KEY"}

            def quality_ruleset_status(self, owner, repo, token):
                return {
                    "ok": True,
                    "name": "Arya Quality Required Checks",
                    "exists": True,
                    "enforcement": "active",
                    "required_status_checks": ["compiler-check", "quality-gate"],
                    "missing_status_checks": [],
                }

        try:
            provisioning_service.GitHubAppApi = FakeGitHubAppApi
            db = SessionLocal()
            try:
                tenant = Tenant(name="Alpha", slug="alpha")
                db.add(tenant)
                db.flush()
                installation = GitHubInstallation(
                    tenant_id=tenant.id,
                    installation_id=123,
                    account_login="alpha",
                    account_type="Organization",
                )
                db.add(installation)
                db.flush()
                repo = ensure_repo_allowed(db, "owner/repo", tenant)
                repo.installation_id = installation.id
                create_repository_api_key(db, repo)

                verification = verify_repository_setup(db, repo)

                self.assertTrue(verification["ready"])
                self.assertEqual(repo.setup_status, "active")
                self.assertIsNotNone(repo.workflow_installed_at)
                self.assertIsNotNone(repo.secrets_configured_at)
                self.assertIsNotNone(repo.ruleset_configured_at)
            finally:
                db.rollback()
                db.close()
        finally:
            provisioning_service.GitHubAppApi = original_github

    def test_standalone_workflow_uses_builtin_scanner_not_missing_pypi_package(self):
        workflow = render_standalone_workflow()
        self.assertIn("Using built-in Arya quality scanner", workflow)
        self.assertIn("Potential secret detected", workflow)
        self.assertIn("DASHBOARD_URL secret is missing or empty", workflow)
        self.assertNotIn("cq-pipeline[all]", workflow)
        self.assertNotIn("pip install cq-pipeline", workflow)

    def test_provision_repository_creates_setup_pr_without_final_ruleset_when_workflow_blocked(self):
        original_github = provisioning_service.GitHubAppApi
        original_dry_run = settings.PROVISIONING_DRY_RUN
        original_base_url = settings.PUBLIC_BASE_URL
        original_allow_local = settings.ALLOW_LOCAL_DASHBOARD_URL_FOR_PROVISIONING

        class FakeGitHubAppApi:
            def __init__(self):
                self.ruleset_called = False

            def installation_token(self, installation_id):
                return "installation-token"

            def get_repository(self, owner, repo, token):
                return {"default_branch": "main"}

            def upsert_file_or_pull_request(self, *args, **kwargs):
                return {
                    "mode": "pull_request",
                    "branch": "arya/setup-quality-pipeline",
                    "pull_request_number": 7,
                    "pull_request_url": "https://github.com/owner/repo/pull/7",
                }

            def set_repo_secret(self, owner, repo, secret_name, secret_value, token):
                self.last_secret = (secret_name, secret_value)

            def upsert_ruleset(self, owner, repo, token):
                self.ruleset_called = True

        try:
            provisioning_service.GitHubAppApi = FakeGitHubAppApi
            settings.PROVISIONING_DRY_RUN = False
            settings.PUBLIC_BASE_URL = "https://example.ngrok-free.app"
            settings.ALLOW_LOCAL_DASHBOARD_URL_FOR_PROVISIONING = False

            db = SessionLocal()
            try:
                tenant = Tenant(name="Alpha", slug="alpha")
                db.add(tenant)
                db.flush()
                installation = GitHubInstallation(
                    tenant_id=tenant.id,
                    installation_id=123,
                    account_login="alpha",
                    account_type="Organization",
                )
                db.add(installation)
                db.flush()
                repo = ensure_repo_allowed(db, "owner/repo", tenant)
                repo.installation_id = installation.id

                result = provision_repository(db, repo)

                self.assertEqual(result["workflow_delivery"]["mode"], "pull_request")
                self.assertEqual(repo.setup_status, "setup_pr_open")
                self.assertIsNotNone(repo.secrets_configured_at)
                self.assertIsNone(repo.ruleset_configured_at)
                self.assertIn("ruleset_waiting_for_setup_pr_merge", result["actions"])
            finally:
                db.rollback()
                db.close()
        finally:
            provisioning_service.GitHubAppApi = original_github
            settings.PROVISIONING_DRY_RUN = original_dry_run
            settings.PUBLIC_BASE_URL = original_base_url
            settings.ALLOW_LOCAL_DASHBOARD_URL_FOR_PROVISIONING = original_allow_local


if __name__ == "__main__":
    unittest.main()
