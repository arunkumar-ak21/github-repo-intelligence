"""Routes for autonomous quality and pipeline report ingestion."""

from __future__ import annotations

import hmac
import json
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from core.config import settings
from core.database import SessionLocal
from core.models import PipelineRun
from modules.auth.service import AuthRequiredError, resolve_request_tenant
from modules.quality.local_runner import run_local_quality_scan
from modules.quality.normalizer import normalize_repo_name, quality_payload_to_stage
from modules.quality.report_receiver import (
    RepoNotAllowedError,
    run_to_dict,
    upsert_stage_report,
)
from modules.quality.schemas import PipelineStagePayload, QualityReportPayload
from modules.tenancy.api_keys import ReportAuthError, validate_report_token


router = APIRouter(tags=["Autonomous Pipeline"])

_rate_limit_lock = threading.Lock()
_rate_limit_hits: dict[str, list[float]] = {}


def _auth_error(message: str = "Unauthorized") -> JSONResponse:
    return JSONResponse({"error": message}, status_code=401)


def _extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _verify_global_report_auth(request: Request) -> JSONResponse | None:
    if not settings.DASHBOARD_API_KEY:
        return _auth_error("DASHBOARD_API_KEY is not configured.")

    token = _extract_bearer_token(request)
    if not token:
        return _auth_error("Missing bearer token.")

    if not hmac.compare_digest(token, settings.DASHBOARD_API_KEY):
        return _auth_error("Invalid bearer token.")

    return None


def _rate_limit_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(request: Request) -> JSONResponse | None:
    now = time.monotonic()
    window_start = now - 60
    key = _rate_limit_key(request)

    with _rate_limit_lock:
        hits = [hit for hit in _rate_limit_hits.get(key, []) if hit >= window_start]
        if len(hits) >= settings.REPORT_RATE_LIMIT_PER_MINUTE:
            _rate_limit_hits[key] = hits
            return JSONResponse({"error": "Rate limit exceeded."}, status_code=429)
        hits.append(now)
        _rate_limit_hits[key] = hits

    return None


async def _read_limited_json(request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > settings.MAX_REPORT_PAYLOAD_BYTES:
                return None, JSONResponse({"error": "Payload too large."}, status_code=413)
        except ValueError:
            return None, JSONResponse({"error": "Invalid Content-Length header."}, status_code=400)

    body = await request.body()
    if len(body) > settings.MAX_REPORT_PAYLOAD_BYTES:
        return None, JSONResponse({"error": "Payload too large."}, status_code=413)

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return None, JSONResponse({"error": "Invalid JSON body."}, status_code=400)

    if not isinstance(payload, dict):
        return None, JSONResponse({"error": "JSON payload must be an object."}, status_code=400)

    return payload, None


def _global_security_gate(request: Request) -> JSONResponse | None:
    auth_error = _verify_global_report_auth(request)
    if auth_error:
        return auth_error
    return _enforce_rate_limit(request)


@router.post("/api/quality/report")
async def receive_quality_report(request: Request):
    security_error = _enforce_rate_limit(request)
    if security_error:
        return security_error

    raw_payload, body_error = await _read_limited_json(request)
    if body_error:
        return body_error

    try:
        payload = QualityReportPayload.model_validate(raw_payload)
        payload.repo = normalize_repo_name(payload.repo)
        stage_payload = quality_payload_to_stage(payload)
    except (ValidationError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    db = SessionLocal()
    try:
        repository = validate_report_token(db, _extract_bearer_token(request), stage_payload.repo)
        run, stage = upsert_stage_report(db, stage_payload, raw_payload or {}, repository)
        return JSONResponse(
            {
                "status": "stored",
                "pipeline_run_id": run.id,
                "pipeline_stage_id": stage.id,
                "tenant_id": run.tenant_id,
                "repo": run.repo,
                "stage": stage.stage_name,
                "overall_status": run.overall_status,
            }
        )
    except ReportAuthError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=401)
    except RepoNotAllowedError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=403)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.post("/api/pipeline/report")
async def receive_pipeline_report(request: Request):
    security_error = _enforce_rate_limit(request)
    if security_error:
        return security_error

    raw_payload, body_error = await _read_limited_json(request)
    if body_error:
        return body_error

    try:
        payload = PipelineStagePayload.model_validate(raw_payload)
        payload.repo = normalize_repo_name(payload.repo)
    except (ValidationError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    db = SessionLocal()
    try:
        repository = validate_report_token(db, _extract_bearer_token(request), payload.repo)
        run, stage = upsert_stage_report(db, payload, raw_payload or {}, repository)
        return JSONResponse(
            {
                "status": "stored",
                "pipeline_run_id": run.id,
                "pipeline_stage_id": stage.id,
                "tenant_id": run.tenant_id,
                "repo": run.repo,
                "stage": stage.stage_name,
                "overall_status": run.overall_status,
            }
        )
    except ReportAuthError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=401)
    except RepoNotAllowedError as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=403)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.post("/api/quality/local-scan")
async def run_local_scan(request: Request):
    security_error = _global_security_gate(request)
    if security_error:
        return security_error

    if not settings.ENABLE_LOCAL_QUALITY_SCAN:
        return JSONResponse(
            {
                "error": (
                    "Local quality scanning is disabled. Production enforcement must use "
                    "GitHub Actions report submission."
                )
            },
            status_code=403,
        )

    raw_payload, body_error = await _read_limited_json(request)
    if body_error:
        return body_error

    project_root = (raw_payload or {}).get("project_root")
    if not project_root:
        return JSONResponse({"error": "project_root is required."}, status_code=400)

    try:
        result = run_local_quality_scan(Path(project_root))
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/pipeline/runs")
async def list_pipeline_runs(
    request: Request,
    repo: str = "",
    status: str = "",
    limit: int = 50,
):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        query = db.query(PipelineRun)
        query = query.filter(PipelineRun.tenant_id == tenant.id)
        if repo:
            query = query.filter(PipelineRun.repo == normalize_repo_name(repo))
        if status:
            query = query.filter(PipelineRun.overall_status == status)
        runs = (
            query.order_by(PipelineRun.created_at.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )
        return JSONResponse([run_to_dict(db, run) for run in runs])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.get("/api/pipeline/runs/{run_id}")
async def get_pipeline_run(request: Request, run_id: int):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run or run.tenant_id != tenant.id:
            return JSONResponse({"error": "Pipeline run not found."}, status_code=404)
        return JSONResponse(run_to_dict(db, run, include_details=True))
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.get("/api/pipeline/latest/{owner}/{repo}")
async def get_latest_pipeline_run(request: Request, owner: str, repo: str):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        full_name = normalize_repo_name(f"{owner}/{repo}")
        run = (
            db.query(PipelineRun)
            .filter(
                PipelineRun.tenant_id == tenant.id,
                PipelineRun.repo == full_name,
            )
            .order_by(PipelineRun.created_at.desc())
            .first()
        )
        if not run:
            return JSONResponse({"error": "Pipeline run not found."}, status_code=404)
        return JSONResponse(run_to_dict(db, run, include_details=True))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()
