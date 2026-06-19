"""Routes for GitHub App installation callbacks and webhooks."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from core.database import SessionLocal
from core.models import GitHubInstallation
from modules.auth.service import AuthRequiredError, get_session_user, resolve_request_tenant
from modules.github_app.service import (
    WebhookSignatureError,
    github_app_install_url,
    handle_installation_repositories_webhook,
    handle_installation_webhook,
    installation_to_dict,
    upsert_installation_from_payload,
    verify_webhook_signature,
)
from modules.provisioning.automation import run_installation_automation
from modules.tenancy.service import record_audit_event


router = APIRouter(tags=["GitHub App"])


@router.get("/api/github-app/install")
async def start_install():
    install_url = github_app_install_url()
    if not install_url:
        return JSONResponse({"error": "GitHub App install URL is not configured."}, status_code=501)
    return RedirectResponse(install_url, status_code=302)


@router.get("/api/github-app/setup-callback")
async def setup_callback(request: Request, installation_id: str = "", setup_action: str = ""):
    if not installation_id:
        return JSONResponse({"error": "installation_id is required."}, status_code=400)

    db = SessionLocal()
    try:
        user = get_session_user(db, request)
        tenant = resolve_request_tenant(db, request, allow_dev_fallback=True)
        installation = upsert_installation_from_payload(
            db,
            {
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
            },
            user_id=user.id if user else None,
        )
        record_audit_event(
            db,
            tenant_id=installation.tenant_id,
            user_id=user.id if user else None,
            event_type="github_app_setup_callback",
            target_type="installation",
            target_id=str(installation.installation_id),
            metadata={"setup_action": setup_action},
        )
        automation = run_installation_automation(
            db,
            installation,
            source="setup_callback",
            user_id=user.id if user else None,
        )
        db.commit()
        request.session["last_setup_automation"] = automation
        return RedirectResponse("/#setup", status_code=302)
    except AuthRequiredError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.post("/api/github-app/webhook")
async def github_webhook(request: Request):
    raw_body = await request.body()
    try:
        verify_webhook_signature(raw_body, request.headers.get("X-Hub-Signature-256"))
        payload = json.loads(raw_body.decode("utf-8"))
        event = request.headers.get("X-GitHub-Event", "")
    except WebhookSignatureError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception:
        return JSONResponse({"error": "Invalid GitHub webhook payload."}, status_code=400)

    db = SessionLocal()
    try:
        installation = None
        if event == "installation":
            installation = handle_installation_webhook(db, payload)
        elif event == "installation_repositories":
            installation = handle_installation_repositories_webhook(db, payload)
        else:
            record_audit_event(
                db,
                event_type="github_webhook_ignored",
                target_type="github_event",
                target_id=event or "unknown",
                metadata={"event": event},
            )
        automation = None
        action = payload.get("action")
        can_automate = event == "installation_repositories" or action in {"created", "new_permissions_accepted", "unsuspend"}
        if installation and can_automate:
            automation = run_installation_automation(
                db,
                installation,
                source=f"webhook:{event}",
            )
        db.commit()
        return JSONResponse(
            {
                "status": "accepted",
                "event": event,
                "installation": installation_to_dict(installation) if installation else None,
                "automation": automation,
            }
        )
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.get("/api/github-app/installations")
async def list_installations(request: Request):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        rows = (
            db.query(GitHubInstallation)
            .filter(GitHubInstallation.tenant_id == tenant.id)
            .order_by(GitHubInstallation.created_at.desc())
            .all()
        )
        return JSONResponse([installation_to_dict(row) for row in rows])
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    finally:
        db.close()
