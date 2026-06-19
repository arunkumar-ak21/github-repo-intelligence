"""Repository setup APIs used by the onboarding UI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.config import settings
from core.database import SessionLocal
from core.models import GitHubInstallation, MonitoredRepository, RepositoryApiKey
from modules.auth.service import AuthRequiredError, resolve_request_tenant
from modules.provisioning.automation import run_installation_automation
from modules.provisioning.service import (
    ProvisioningError,
    provision_repository,
    redact_provisioning_result,
    repo_setup_dict,
    verify_repository_setup,
)
from modules.quality.normalizer import normalize_repo_name, split_repo
from modules.tenancy.service import record_audit_event


router = APIRouter(tags=["Repository Provisioning"])


def _active_key(db, repository_id: int) -> RepositoryApiKey | None:
    return (
        db.query(RepositoryApiKey)
        .filter(
            RepositoryApiKey.repository_id == repository_id,
            RepositoryApiKey.status == "active",
        )
        .order_by(RepositoryApiKey.created_at.desc())
        .first()
    )


@router.get("/api/setup/repositories")
async def list_repositories(request: Request):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        repos = (
            db.query(MonitoredRepository)
            .filter(MonitoredRepository.tenant_id == tenant.id)
            .order_by(MonitoredRepository.full_name.asc())
            .all()
        )
        return JSONResponse([repo_setup_dict(repo, _active_key(db, repo.id)) for repo in repos])
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    finally:
        db.close()


@router.post("/api/setup/repositories/register")
async def register_repository(request: Request):
    try:
        body = await request.json()
        full_name = normalize_repo_name(body.get("repo") or body.get("full_name") or "")
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        owner, repo_name = split_repo(full_name)
        repo = (
            db.query(MonitoredRepository)
            .filter(
                MonitoredRepository.tenant_id == tenant.id,
                MonitoredRepository.full_name == full_name,
            )
            .first()
        )
        if not repo:
            repo = MonitoredRepository(
                tenant_id=tenant.id,
                full_name=full_name,
                owner=owner,
                repo=repo_name,
                setup_status="pending",
                is_active=True,
            )
            db.add(repo)
            db.flush()
        repo.is_active = True
        repo.default_branch = body.get("default_branch") or repo.default_branch
        if body.get("installation_id"):
            repo.installation_id = int(body["installation_id"])
        record_audit_event(
            db,
            tenant_id=tenant.id,
            event_type="repository_registered",
            target_type="repository",
            target_id=full_name,
        )
        db.commit()
        return JSONResponse(repo_setup_dict(repo, _active_key(db, repo.id)))
    except AuthRequiredError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.get("/api/setup/repositories/{repo_id}/status")
async def get_repository_status(request: Request, repo_id: int):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        repo = (
            db.query(MonitoredRepository)
            .filter(MonitoredRepository.id == repo_id, MonitoredRepository.tenant_id == tenant.id)
            .first()
        )
        if not repo:
            return JSONResponse({"error": "Repository not found."}, status_code=404)
        return JSONResponse(repo_setup_dict(repo, _active_key(db, repo.id)))
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    finally:
        db.close()


@router.post("/api/setup/repositories/{repo_id}/provision")
async def provision_repo(request: Request, repo_id: int):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        repo = (
            db.query(MonitoredRepository)
            .filter(MonitoredRepository.id == repo_id, MonitoredRepository.tenant_id == tenant.id)
            .first()
        )
        if not repo:
            return JSONResponse({"error": "Repository not found."}, status_code=404)
        result = provision_repository(db, repo)
        db.commit()
        workflow_delivery = result.get("workflow_delivery") or {}
        status = "dry_run" if result["dry_run"] else "provisioned"
        if workflow_delivery.get("mode") == "pull_request":
            status = "pending_pull_request"
        return JSONResponse(
            {
                "status": status,
                "repo": repo_setup_dict(repo, _active_key(db, repo.id)),
                "result": redact_provisioning_result(result),
            }
        )
    except AuthRequiredError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=401)
    except ProvisioningError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=502)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.post("/api/setup/repositories/{repo_id}/verify")
async def verify_repo_setup(request: Request, repo_id: int):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        repo = (
            db.query(MonitoredRepository)
            .filter(MonitoredRepository.id == repo_id, MonitoredRepository.tenant_id == tenant.id)
            .first()
        )
        if not repo:
            return JSONResponse({"error": "Repository not found."}, status_code=404)
        verification = verify_repository_setup(db, repo)
        db.commit()
        return JSONResponse(
            {
                "status": "verified",
                "repo": repo_setup_dict(repo, _active_key(db, repo.id)),
                "verification": verification,
            }
        )
    except AuthRequiredError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=401)
    except ProvisioningError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=502)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.post("/api/setup/sync-installed-repositories")
async def sync_installed_repos(request: Request):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        installations = (
            db.query(GitHubInstallation)
            .filter(
                GitHubInstallation.tenant_id == tenant.id,
                GitHubInstallation.suspended_at.is_(None),
            )
            .order_by(GitHubInstallation.created_at.desc())
            .all()
        )
        if not installations:
            return JSONResponse(
                {
                    "error": (
                        "No GitHub App installation found for this tenant. "
                        "Install the GitHub App first and select repositories."
                    )
                },
                status_code=404,
            )

        results = [
            run_installation_automation(
                db,
                installation,
                source="manual_sync",
                auto_sync=True,
                auto_provision=settings.AUTO_PROVISION_ON_SYNC,
            )
            for installation in installations
        ]
        db.commit()
        return JSONResponse({"status": "synced", "installations": results})
    except AuthRequiredError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=401)
    except ProvisioningError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=502)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()
