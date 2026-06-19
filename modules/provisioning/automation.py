"""Install-time repository sync and provisioning orchestration."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from core.config import settings
from core.models import GitHubInstallation, MonitoredRepository
from modules.provisioning.service import (
    ProvisioningError,
    provision_repository,
    redact_provisioning_result,
    repo_setup_dict,
    repository_needs_provisioning,
    sync_installed_repository_records,
)
from modules.tenancy.service import record_audit_event


def _tenant_repositories(db: Session, installation: GitHubInstallation) -> list[MonitoredRepository]:
    db.flush()
    return (
        db.query(MonitoredRepository)
        .filter(
            MonitoredRepository.tenant_id == installation.tenant_id,
            MonitoredRepository.installation_id == installation.id,
            MonitoredRepository.is_active.is_(True),
        )
        .order_by(MonitoredRepository.full_name.asc())
        .all()
    )


def run_installation_automation(
    db: Session,
    installation: GitHubInstallation,
    *,
    source: str,
    user_id: int | None = None,
    auto_sync: bool | None = None,
    auto_provision: bool | None = None,
) -> dict[str, Any]:
    """Sync selected repos and optionally provision them after a GitHub App event.

    This helper intentionally captures errors instead of failing the install
    callback. Clients should land in the dashboard even if the platform needs a
    configuration fix, and the audit log should retain the reason.
    """

    should_sync = settings.AUTO_SYNC_REPOS_ON_INSTALL if auto_sync is None else auto_sync
    should_provision = settings.AUTO_PROVISION_ON_INSTALL if auto_provision is None else auto_provision
    result: dict[str, Any] = {
        "source": source,
        "installation_id": installation.installation_id,
        "auto_sync": should_sync,
        "auto_provision": should_provision,
        "dry_run": settings.PROVISIONING_DRY_RUN,
        "synced_repository_count": 0,
        "provisioned_repository_count": 0,
        "skipped_repository_count": 0,
        "repositories": [],
        "errors": [],
    }

    try:
        repositories = sync_installed_repository_records(db, installation) if should_sync else _tenant_repositories(db, installation)
        result["synced_repository_count"] = len(repositories) if should_sync else 0
    except Exception as exc:
        result["errors"].append({"stage": "sync", "message": str(exc)})
        record_audit_event(
            db,
            tenant_id=installation.tenant_id,
            user_id=user_id,
            event_type="github_installation_automation_failed",
            target_type="installation",
            target_id=str(installation.installation_id),
            metadata=result,
        )
        return result

    for repo in repositories:
        repo_result: dict[str, Any] = {"repo": repo_setup_dict(repo)}
        if not should_provision:
            repo_result["status"] = "synced"
            result["repositories"].append(repo_result)
            continue

        if not settings.AUTO_REPROVISION_ACTIVE_REPOS and not repository_needs_provisioning(repo):
            repo_result["status"] = "skipped_active"
            result["skipped_repository_count"] += 1
            result["repositories"].append(repo_result)
            continue

        try:
            provisioned = provision_repository(db, repo)
            repo_result["status"] = "dry_run" if provisioned["dry_run"] else "provisioned"
            repo_result["result"] = redact_provisioning_result(provisioned)
            result["provisioned_repository_count"] += 1
        except ProvisioningError as exc:
            repo_result["status"] = "failed"
            repo_result["error"] = str(exc)
            result["errors"].append({"stage": "provision", "repo": repo.full_name, "message": str(exc)})
        result["repositories"].append(repo_result)

    record_audit_event(
        db,
        tenant_id=installation.tenant_id,
        user_id=user_id,
        event_type="github_installation_automation_completed" if not result["errors"] else "github_installation_automation_partial",
        target_type="installation",
        target_id=str(installation.installation_id),
        metadata=result,
    )
    return result
