"""GitHub login and tenant session routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from core.config import settings
from core.database import SessionLocal
from modules.auth.service import (
    AuthConfigurationError,
    AuthRequiredError,
    build_github_login_url,
    exchange_code_for_token,
    fetch_github_user,
    get_session_user,
    get_user_memberships,
    github_login_configured,
    new_oauth_state,
    resolve_request_tenant,
    select_tenant_for_session,
    tenant_to_dict,
    upsert_user_from_github,
    user_to_dict,
    ensure_personal_tenant_for_user,
)
from modules.github_app.service import github_app_install_url, upsert_installation_from_payload
from modules.provisioning.automation import run_installation_automation
from modules.tenancy.service import record_audit_event


router = APIRouter(tags=["Authentication"])


def _login_not_configured_response(message: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GitHub Login Setup Required</title>
  <style>
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: Inter, system-ui, sans-serif; background: #0b1020; color: #f7fbff; }}
    main {{ width: min(720px, calc(100vw - 32px)); border: 1px solid rgba(148,163,184,.22); border-radius: 16px; padding: 28px; background: rgba(16,21,34,.88); box-shadow: 0 24px 70px rgba(0,0,0,.34); }}
    h1 {{ margin: 0 0 10px; font-size: 1.55rem; }}
    p {{ color: #b6c2d6; line-height: 1.6; }}
    code {{ color: #00d4ff; }}
    a {{ color: #031016; background: #00d4ff; display: inline-flex; padding: 10px 14px; border-radius: 10px; text-decoration: none; font-weight: 800; }}
  </style>
</head>
<body>
  <main>
    <h1>GitHub sign up is not configured yet</h1>
    <p>{message}</p>
    <p>Add <code>GITHUB_APP_CLIENT_ID</code> and <code>GITHUB_APP_CLIENT_SECRET</code> in <code>.env</code>, confirm <code>PUBLIC_BASE_URL</code>, then restart the server.</p>
    <a href="/">Back to landing page</a>
  </main>
</body>
</html>""",
        status_code=501,
    )


@router.get("/api/auth/status")
async def auth_status(request: Request):
    db = SessionLocal()
    try:
        user = get_session_user(db, request)
        tenants = []
        selected_tenant_id = request.session.get("tenant_id")
        if user:
            tenants = [
                tenant_to_dict(tenant, role)
                for tenant, role in get_user_memberships(db, user.id)
            ]
            if selected_tenant_id and not any(item["id"] == int(selected_tenant_id) for item in tenants):
                selected_tenant_id = None
                request.session.pop("tenant_id", None)

        return JSONResponse(
            {
                "authenticated": bool(user),
                "require_login": settings.REQUIRE_LOGIN,
                "app_name": settings.APP_NAME,
                "github_login_configured": github_login_configured(),
                "github_app_configured": bool(settings.GITHUB_APP_ID and (settings.GITHUB_APP_PRIVATE_KEY or settings.GITHUB_APP_PRIVATE_KEY_PATH)),
                "github_app_install_url": github_app_install_url(),
                "user": user_to_dict(user) if user else None,
                "tenants": tenants,
                "selected_tenant_id": selected_tenant_id,
            }
        )
    finally:
        db.close()


@router.get("/api/auth/login")
async def github_login(request: Request, next: str = ""):
    try:
        state = new_oauth_state()
        request.session["oauth_state"] = state
        if next.startswith("/") and not next.startswith("//"):
            request.session["post_login_redirect"] = next
        return RedirectResponse(build_github_login_url(state), status_code=302)
    except AuthConfigurationError as exc:
        return _login_not_configured_response(str(exc))


def _installation_payload_for_current_tenant(installation_id: str, setup_action: str, tenant) -> dict:
    return {
        "installation": {
            "id": int(installation_id),
            "account": {
                "id": tenant.github_account_id,
                "login": tenant.github_account_login or tenant.slug,
                "type": tenant.github_account_type or "Unknown",
            },
            "repository_selection": None,
        },
        "setup_action": setup_action,
    }


@router.get("/api/auth/callback")
async def github_callback(
    request: Request,
    code: str = "",
    state: str = "",
    installation_id: str = "",
    setup_action: str = "",
):
    expected_state = request.session.get("oauth_state")

    if installation_id and (not state or state != expected_state):
        db = SessionLocal()
        try:
            user = get_session_user(db, request)
            tenant = resolve_request_tenant(db, request, allow_dev_fallback=True)
            installation = upsert_installation_from_payload(
                db,
                _installation_payload_for_current_tenant(installation_id, setup_action, tenant),
                user_id=user.id if user else None,
            )
            request.session["tenant_id"] = installation.tenant_id
            record_audit_event(
                db,
                tenant_id=installation.tenant_id,
                user_id=user.id if user else None,
                event_type="github_app_install_callback_on_auth_route",
                target_type="installation",
                target_id=str(installation.installation_id),
                metadata={"setup_action": setup_action},
            )
            automation = run_installation_automation(
                db,
                installation,
                source="auth_callback_installation",
                user_id=user.id if user else None,
            )
            request.session["last_setup_automation"] = automation
            db.commit()
            return RedirectResponse("/#setup", status_code=302)
        except AuthRequiredError as exc:
            db.rollback()
            return JSONResponse({"error": str(exc)}, status_code=401)
        except Exception as exc:
            db.rollback()
            return JSONResponse({"error": str(exc)}, status_code=500)
        finally:
            db.close()

    request.session.pop("oauth_state", None)
    if not code or not state or not expected_state or state != expected_state:
        return JSONResponse({"error": "Invalid GitHub OAuth state."}, status_code=400)

    db = SessionLocal()
    try:
        token = exchange_code_for_token(code)
        profile = fetch_github_user(token)
        user = upsert_user_from_github(db, profile)
        tenant = ensure_personal_tenant_for_user(db, user, profile)
        request.session["user_id"] = user.id
        request.session["tenant_id"] = tenant.id
        request.session["github_login"] = user.github_login
        record_audit_event(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            event_type="login",
            target_type="user",
            target_id=str(user.id),
        )
        redirect_target = request.session.pop("post_login_redirect", "/#dashboard")
        db.commit()
        return RedirectResponse(redirect_target, status_code=302)
    except AuthConfigurationError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=501)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=502)
    finally:
        db.close()


@router.post("/api/auth/logout")
async def logout(request: Request):
    db = SessionLocal()
    try:
        user = get_session_user(db, request)
        tenant_id = request.session.get("tenant_id")
        if user:
            record_audit_event(
                db,
                tenant_id=tenant_id,
                user_id=user.id,
                event_type="logout",
                target_type="user",
                target_id=str(user.id),
            )
            db.commit()
        request.session.clear()
        return JSONResponse({"status": "logged_out"})
    finally:
        db.close()


@router.get("/api/auth/tenants")
async def list_tenants(request: Request):
    db = SessionLocal()
    try:
        user = get_session_user(db, request)
        if not user:
            return JSONResponse({"error": "Login is required."}, status_code=401)
        return JSONResponse(
            {
                "selected_tenant_id": request.session.get("tenant_id"),
                "tenants": [
                    tenant_to_dict(tenant, role)
                    for tenant, role in get_user_memberships(db, user.id)
                ],
            }
        )
    finally:
        db.close()


@router.post("/api/auth/select-tenant")
async def select_tenant(request: Request):
    try:
        body = await request.json()
        tenant_id = int(body.get("tenant_id"))
    except Exception:
        return JSONResponse({"error": "tenant_id is required."}, status_code=400)

    db = SessionLocal()
    try:
        tenant = select_tenant_for_session(db, request, tenant_id)
        db.commit()
        return JSONResponse({"status": "selected", "tenant": tenant_to_dict(tenant)})
    except AuthRequiredError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=403)
    finally:
        db.close()
