"""GitHub OAuth login and tenant-session helpers."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from sqlalchemy.orm import Session

from core.config import settings
from core.models import Tenant, TenantMembership, User
from modules.tenancy.service import get_or_create_default_tenant, record_audit_event


GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


class AuthConfigurationError(RuntimeError):
    """Raised when GitHub login is requested before app credentials exist."""


class AuthRequiredError(PermissionError):
    """Raised when a route requires a logged-in user."""


def github_login_configured() -> bool:
    return bool(settings.GITHUB_APP_CLIENT_ID and settings.GITHUB_APP_CLIENT_SECRET)


def callback_url() -> str:
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/auth/callback"


def build_github_login_url(state: str) -> str:
    if not github_login_configured():
        raise AuthConfigurationError("GitHub login is not configured.")
    query = urlencode(
        {
            "client_id": settings.GITHUB_APP_CLIENT_ID,
            "redirect_uri": callback_url(),
            "scope": "read:user user:email",
            "state": state,
            "allow_signup": "true",
        }
    )
    return f"{GITHUB_AUTHORIZE_URL}?{query}"


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def exchange_code_for_token(code: str) -> str:
    if not github_login_configured():
        raise AuthConfigurationError("GitHub login is not configured.")
    response = requests.post(
        GITHUB_TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.GITHUB_APP_CLIENT_ID,
            "client_secret": settings.GITHUB_APP_CLIENT_SECRET,
            "code": code,
            "redirect_uri": callback_url(),
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise AuthConfigurationError(payload.get("error_description") or "GitHub did not return an access token.")
    return str(token)


def fetch_github_user(access_token: str) -> dict[str, Any]:
    response = requests.get(
        GITHUB_USER_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "X-GitHub-Api-Version": settings.GITHUB_API_VERSION,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("id") or not payload.get("login"):
        raise AuthConfigurationError("GitHub user profile response is missing id/login.")
    return payload


def upsert_user_from_github(db: Session, profile: dict[str, Any]) -> User:
    user = db.query(User).filter(User.github_user_id == int(profile["id"])).first()
    now = datetime.now(timezone.utc)
    if not user:
        user = User(
            github_user_id=int(profile["id"]),
            github_login=str(profile["login"]),
            created_at=now,
        )
        db.add(user)
        db.flush()

    user.github_login = str(profile["login"])
    user.name = profile.get("name")
    user.email = profile.get("email")
    user.avatar_url = profile.get("avatar_url")
    user.last_login_at = now
    return user


def ensure_personal_tenant_for_user(db: Session, user: User, profile: dict[str, Any]) -> Tenant:
    slug = f"github-{user.github_login.lower()}"
    tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
    if not tenant:
        tenant = Tenant(
            name=user.github_login,
            slug=slug,
            github_account_id=int(profile["id"]),
            github_account_login=user.github_login,
            github_account_type="User",
            plan="starter",
            created_at=datetime.now(timezone.utc),
        )
        db.add(tenant)
        db.flush()

    membership = (
        db.query(TenantMembership)
        .filter(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.user_id == user.id,
        )
        .first()
    )
    if not membership:
        db.add(
            TenantMembership(
                tenant_id=tenant.id,
                user_id=user.id,
                role="owner",
                created_at=datetime.now(timezone.utc),
            )
        )
        db.flush()
    return tenant


def user_to_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "github_user_id": user.github_user_id,
        "github_login": user.github_login,
        "name": user.name,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def tenant_to_dict(tenant: Tenant, role: str | None = None) -> dict[str, Any]:
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "github_account_id": tenant.github_account_id,
        "github_account_login": tenant.github_account_login,
        "github_account_type": tenant.github_account_type,
        "plan": tenant.plan,
        "role": role,
    }


def get_user_memberships(db: Session, user_id: int) -> list[tuple[Tenant, str]]:
    rows = (
        db.query(Tenant, TenantMembership.role)
        .join(TenantMembership, TenantMembership.tenant_id == Tenant.id)
        .filter(TenantMembership.user_id == user_id)
        .order_by(Tenant.name.asc())
        .all()
    )
    return [(tenant, role) for tenant, role in rows]


def get_session_user(db: Session, request) -> User | None:
    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        return None
    return db.query(User).filter(User.id == int(user_id)).first()


def resolve_request_tenant(db: Session, request, *, allow_dev_fallback: bool = True) -> Tenant:
    user = get_session_user(db, request)
    if user:
        selected_tenant_id = request.session.get("tenant_id")
        memberships = get_user_memberships(db, user.id)
        if selected_tenant_id:
            for tenant, _role in memberships:
                if tenant.id == int(selected_tenant_id):
                    return tenant
        if memberships:
            tenant = memberships[0][0]
            request.session["tenant_id"] = tenant.id
            return tenant

    if allow_dev_fallback and not settings.REQUIRE_LOGIN:
        return get_or_create_default_tenant(db)

    raise AuthRequiredError("Login is required.")


def select_tenant_for_session(db: Session, request, tenant_id: int) -> Tenant:
    user = get_session_user(db, request)
    if not user:
        raise AuthRequiredError("Login is required.")
    membership = (
        db.query(TenantMembership)
        .filter(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == tenant_id,
        )
        .first()
    )
    if not membership:
        raise AuthRequiredError("You do not have access to this tenant.")
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise AuthRequiredError("Tenant not found.")
    request.session["tenant_id"] = tenant.id
    record_audit_event(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        event_type="tenant_selected",
        target_type="tenant",
        target_id=str(tenant.id),
    )
    return tenant
