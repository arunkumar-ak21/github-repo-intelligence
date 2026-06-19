"""Repo-scoped report ingestion API keys."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.config import settings
from core.models import MonitoredRepository, RepositoryApiKey
from modules.quality.normalizer import normalize_repo_name
from modules.quality.report_receiver import ensure_repo_allowed


class ReportAuthError(PermissionError):
    """Raised when a report bearer token is missing or invalid."""


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_repo_api_key() -> tuple[str, str]:
    prefix = f"rqp_{secrets.token_hex(4)}"
    secret = secrets.token_urlsafe(32)
    return prefix, f"{prefix}_{secret}"


def create_repository_api_key(db: Session, repository: MonitoredRepository) -> tuple[RepositoryApiKey, str]:
    prefix, raw_key = generate_repo_api_key()
    key = RepositoryApiKey(
        tenant_id=repository.tenant_id,
        repository_id=repository.id,
        key_prefix=prefix,
        key_hash=hash_api_key(raw_key),
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    db.add(key)
    db.flush()
    return key, raw_key


def rotate_repository_api_key(db: Session, repository: MonitoredRepository) -> tuple[RepositoryApiKey, str]:
    now = datetime.now(timezone.utc)
    existing = (
        db.query(RepositoryApiKey)
        .filter(
            RepositoryApiKey.repository_id == repository.id,
            RepositoryApiKey.status == "active",
        )
        .all()
    )
    for key in existing:
        key.status = "revoked"
        key.revoked_at = now
        key.rotated_at = now
    return create_repository_api_key(db, repository)


def validate_report_token(db: Session, token: str | None, repo: str) -> MonitoredRepository:
    if not token:
        raise ReportAuthError("Missing bearer token.")

    normalized_repo = normalize_repo_name(repo)

    if settings.DASHBOARD_API_KEY and hmac.compare_digest(token, settings.DASHBOARD_API_KEY):
        return ensure_repo_allowed(db, normalized_repo)

    key_hash = hash_api_key(token)
    api_key = (
        db.query(RepositoryApiKey)
        .filter(
            RepositoryApiKey.key_hash == key_hash,
            RepositoryApiKey.status == "active",
        )
        .first()
    )
    if not api_key:
        raise ReportAuthError("Invalid bearer token.")

    repository = (
        db.query(MonitoredRepository)
        .filter(
            MonitoredRepository.id == api_key.repository_id,
            MonitoredRepository.tenant_id == api_key.tenant_id,
            MonitoredRepository.is_active.is_(True),
        )
        .first()
    )
    if not repository:
        raise ReportAuthError("Repository for this API key is not active.")
    if repository.full_name != normalized_repo:
        raise ReportAuthError("API key does not match report repository.")
    return repository
