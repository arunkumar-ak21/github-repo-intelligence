"""Tenant service helpers used before full GitHub auth is implemented."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from core.config import settings
from core.models import AuditEvent, Tenant


def get_or_create_default_tenant(db: Session) -> Tenant:
    """Return the local/dev fallback tenant.

    Full production auth will resolve the tenant from a user session or
    repo-scoped API key. Until then, this keeps existing local and smoke-test
    flows tenant-tagged instead of tenantless.
    """
    tenant = db.query(Tenant).filter(Tenant.slug == settings.DEFAULT_TENANT_SLUG).first()
    if tenant:
        return tenant

    tenant = Tenant(
        name=settings.DEFAULT_TENANT_NAME,
        slug=settings.DEFAULT_TENANT_SLUG,
        github_account_login=settings.DEFAULT_TENANT_SLUG,
        github_account_type="local",
        plan="development",
        created_at=datetime.now(timezone.utc),
    )
    db.add(tenant)
    db.flush()
    return tenant


def record_audit_event(
    db: Session,
    *,
    event_type: str,
    tenant_id: int | None = None,
    user_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        created_at=datetime.now(timezone.utc),
        metadata_json=metadata or {},
    )
    db.add(event)
    db.flush()
    return event
