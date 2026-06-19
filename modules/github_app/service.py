"""GitHub App installation, webhook, and tenant sync helpers."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from core.config import settings
from core.models import GitHubInstallation, MonitoredRepository, Tenant, TenantMembership
from modules.quality.normalizer import normalize_repo_name, split_repo
from modules.tenancy.service import get_or_create_default_tenant, record_audit_event


class WebhookSignatureError(PermissionError):
    """Raised when a GitHub webhook signature is missing or invalid."""


def github_app_install_url() -> str | None:
    if settings.GITHUB_APP_INSTALL_URL:
        return settings.GITHUB_APP_INSTALL_URL
    if settings.GITHUB_APP_SLUG:
        return f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new"
    return None


def verify_webhook_signature(raw_body: bytes, signature_header: str | None) -> None:
    if not settings.GITHUB_APP_WEBHOOK_SECRET:
        raise WebhookSignatureError("GITHUB_APP_WEBHOOK_SECRET is not configured.")
    if not signature_header or not signature_header.startswith("sha256="):
        raise WebhookSignatureError("Missing X-Hub-Signature-256 header.")
    expected = "sha256=" + hmac.new(
        settings.GITHUB_APP_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature_header, expected):
        raise WebhookSignatureError("Invalid GitHub webhook signature.")


def _tenant_slug(account_login: str, account_id: int | None) -> str:
    suffix = str(account_id) if account_id is not None else account_login.lower()
    return f"github-installation-{suffix}"


def get_or_create_tenant_for_account(db: Session, account: dict[str, Any] | None) -> Tenant:
    if not account:
        return get_or_create_default_tenant(db)

    account_id = account.get("id")
    account_login = account.get("login") or account.get("name") or f"account-{account_id}"
    account_type = account.get("type") or "Unknown"
    if account_id:
        existing = db.query(Tenant).filter(Tenant.github_account_id == int(account_id)).first()
        if existing:
            existing.name = str(account_login)
            existing.github_account_login = str(account_login)
            existing.github_account_type = str(account_type)
            return existing

    slug = _tenant_slug(str(account_login), int(account_id) if account_id else None)
    tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
    if not tenant:
        tenant = Tenant(
            name=str(account_login),
            slug=slug,
            github_account_id=int(account_id) if account_id else None,
            github_account_login=str(account_login),
            github_account_type=str(account_type),
            plan="starter",
            created_at=datetime.now(timezone.utc),
        )
        db.add(tenant)
        db.flush()
    else:
        tenant.name = str(account_login)
        tenant.github_account_id = int(account_id) if account_id else tenant.github_account_id
        tenant.github_account_login = str(account_login)
        tenant.github_account_type = str(account_type)
    return tenant


def attach_user_to_tenant(db: Session, *, tenant_id: int, user_id: int, role: str = "owner") -> None:
    membership = (
        db.query(TenantMembership)
        .filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
        .first()
    )
    if membership:
        return
    db.add(
        TenantMembership(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.flush()


def upsert_installation_from_payload(
    db: Session,
    payload: dict[str, Any],
    *,
    user_id: int | None = None,
) -> GitHubInstallation:
    installation = payload.get("installation") or payload
    account = installation.get("account") or payload.get("account")
    tenant = get_or_create_tenant_for_account(db, account)
    if user_id:
        attach_user_to_tenant(db, tenant_id=tenant.id, user_id=user_id, role="owner")

    installation_id = int(installation["id"])
    record = (
        db.query(GitHubInstallation)
        .filter(GitHubInstallation.installation_id == installation_id)
        .first()
    )
    now = datetime.now(timezone.utc)
    if not record:
        record = GitHubInstallation(
            tenant_id=tenant.id,
            installation_id=installation_id,
            created_at=now,
        )
        db.add(record)
        db.flush()

    record.tenant_id = tenant.id
    record.account_id = int(account["id"]) if account and account.get("id") else None
    record.account_login = account.get("login") if account else None
    record.account_type = account.get("type") if account else None
    record.permissions_json = installation.get("permissions")
    record.repository_selection = installation.get("repository_selection")
    record.installed_at = now if record.installed_at is None else record.installed_at
    record.suspended_at = installation.get("suspended_at")
    record.raw_json = payload
    return record


def upsert_repositories_from_payload(
    db: Session,
    installation: GitHubInstallation,
    repositories: list[dict[str, Any]],
) -> list[MonitoredRepository]:
    records: list[MonitoredRepository] = []
    for item in repositories:
        full_name = normalize_repo_name(item.get("full_name") or f"{item.get('owner', {}).get('login')}/{item.get('name')}")
        owner, repo_name = split_repo(full_name)
        record = (
            db.query(MonitoredRepository)
            .filter(
                MonitoredRepository.tenant_id == installation.tenant_id,
                MonitoredRepository.full_name == full_name,
            )
            .first()
        )
        if not record:
            record = MonitoredRepository(
                tenant_id=installation.tenant_id,
                installation_id=installation.id,
                full_name=full_name,
                owner=owner,
                repo=repo_name,
                setup_status="pending",
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(record)
            db.flush()
        record.installation_id = installation.id
        record.default_branch = item.get("default_branch") or record.default_branch
        record.is_active = True
        records.append(record)
    return records


def handle_installation_webhook(db: Session, payload: dict[str, Any]) -> GitHubInstallation | None:
    action = payload.get("action")
    installation = upsert_installation_from_payload(db, payload)
    repos = payload.get("repositories") or []

    if action in {"created", "new_permissions_accepted", "unsuspended"}:
        installation.suspended_at = None
        upsert_repositories_from_payload(db, installation, repos)
        record_audit_event(
            db,
            tenant_id=installation.tenant_id,
            event_type="github_app_installed",
            target_type="installation",
            target_id=str(installation.installation_id),
            metadata={"action": action},
        )
    elif action in {"suspend", "suspended"}:
        installation.suspended_at = datetime.now(timezone.utc)
    elif action == "deleted":
        installation.suspended_at = datetime.now(timezone.utc)
        db.query(MonitoredRepository).filter(
            MonitoredRepository.installation_id == installation.id
        ).update({"is_active": False, "setup_status": "needs_attention"})
    return installation


def handle_installation_repositories_webhook(db: Session, payload: dict[str, Any]) -> GitHubInstallation | None:
    installation = upsert_installation_from_payload(db, payload)
    added = payload.get("repositories_added") or []
    removed = payload.get("repositories_removed") or []
    upsert_repositories_from_payload(db, installation, added)
    for item in removed:
        full_name = normalize_repo_name(item.get("full_name") or f"{item.get('owner', {}).get('login')}/{item.get('name')}")
        record = (
            db.query(MonitoredRepository)
            .filter(
                MonitoredRepository.tenant_id == installation.tenant_id,
                MonitoredRepository.full_name == full_name,
            )
            .first()
        )
        if record:
            record.is_active = False
            record.setup_status = "needs_attention"
    return installation


def installation_to_dict(installation: GitHubInstallation) -> dict[str, Any]:
    return {
        "id": installation.id,
        "tenant_id": installation.tenant_id,
        "installation_id": installation.installation_id,
        "account_id": installation.account_id,
        "account_login": installation.account_login,
        "account_type": installation.account_type,
        "repository_selection": installation.repository_selection,
        "installed_at": installation.installed_at.isoformat() if installation.installed_at else None,
        "suspended_at": installation.suspended_at.isoformat() if installation.suspended_at else None,
    }
