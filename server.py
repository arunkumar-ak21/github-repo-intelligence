"""GitHub Repository Intelligence Dashboard server."""

from __future__ import annotations

import argparse
import hashlib
import json
import queue
import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from requests.adapters import HTTPAdapter

from core.cache import analysis_cache
from core.config import settings
from core.database import SessionLocal, init_db
from core.errors import RepoHubError
from core.github_client import GitHubAPIError, get_github_client
from core.models import AnalysisBatch, AnalysisHistory
from modules.metadata.models import Commit, Contributor, FileTree, Repository
from core.session import SignedCookieSessionMiddleware
from modules.auth.routes import router as auth_router
from modules.auth.service import AuthRequiredError, resolve_request_tenant
from modules.cicd.routes import router as cicd_router
from modules.cicd.scanner import scan_repo_pipelines
from modules.deps.analysis import analyze_repo as analyze_deps
from modules.deps.routes import router as deps_router
from modules.github_app.routes import router as github_app_router
from modules.metadata.extractor import extract_repo_metadata
from modules.metadata.routes import router as meta_router
from modules.provisioning.routes import router as provisioning_router
from modules.quality.routes import router as quality_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup."""
    init_db()
    yield


app = FastAPI(
    title="GitHub Repository Intelligence Dashboard",
    description="Production-ready GitHub repository metadata, CI/CD, dependency, and architecture intelligence.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    SignedCookieSessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    cookie_name=settings.SESSION_COOKIE_NAME,
    max_age=settings.SESSION_MAX_AGE_SECONDS,
    https_only=settings.SESSION_COOKIE_SECURE,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=settings.ALLOWED_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Attach security headers without blocking local dashboard CDNs."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' blob: https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "connect-src 'self' blob: https://api.github.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "frame-src 'self'; "
        "worker-src 'self' blob:; "
        "object-src 'none'; base-uri 'self';"
    )
    return response


@app.exception_handler(RepoHubError)
async def repohub_exception_handler(request: Request, exc: RepoHubError):
    return JSONResponse(exc.to_dict(), status_code=exc.status_code)


app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")
REACT_DIST = PROJECT_ROOT / "frontend" / "dist"
REACT_ASSETS = REACT_DIST / "assets"
if REACT_ASSETS.exists():
    app.mount("/react/assets", StaticFiles(directory=str(REACT_ASSETS)), name="react-assets")
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))

app.include_router(meta_router)
app.include_router(cicd_router)
app.include_router(deps_router)
app.include_router(quality_router)
app.include_router(auth_router)
app.include_router(github_app_router)
app.include_router(provisioning_router)


@app.get("/react", response_class=HTMLResponse, include_in_schema=False)
@app.get("/react/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
async def react_frontend(full_path: str = ""):
    """Serve the separately built React frontend without replacing the classic dashboard."""
    index_file = REACT_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>React frontend not built</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: system-ui, sans-serif; background: #f6f8fa; color: #1f2328; }
    main { width: min(680px, calc(100vw - 32px)); border: 1px solid #d0d7de; border-radius: 8px; background: #fff; padding: 24px; box-shadow: 0 8px 24px rgba(140,149,159,.2); }
    h1 { margin: 0 0 8px; font-size: 20px; }
    p { color: #57606a; line-height: 1.55; }
    code { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 2px 6px; }
  </style>
</head>
<body>
  <main>
    <h1>React frontend is not built yet</h1>
    <p>Run <code>npm install</code> and <code>npm run build</code> inside <code>frontend/</code>, then restart the FastAPI server to serve the React app at <code>/react</code>.</p>
  </main>
</body>
</html>""",
        status_code=503,
    )

_github_proxy_session = requests.Session()
_github_proxy_session.mount(
    "https://",
    HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0),
)


def sse_event(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(jsonable_encoder(data), default=str)}\n\n"


def normalize_repo_input(repo: str) -> str:
    """Normalize owner/repo, GitHub URLs, SSH URLs, and .git URLs."""
    value = (repo or "").strip()
    if not value:
        raise ValueError("Repository is required. Use owner/repo.")

    if value.startswith("git@github.com:"):
        value = value.replace("git@github.com:", "", 1)
    elif value.startswith("ssh://git@github.com/"):
        value = value.replace("ssh://git@github.com/", "", 1)
    elif re.match(r"^https?://", value, flags=re.I):
        parsed = urlparse(value)
        if parsed.netloc.lower().replace("www.", "") != "github.com":
            raise ValueError("Only GitHub repository URLs are supported.")
        value = parsed.path.strip("/")
    else:
        value = re.sub(r"^(www\.)?github\.com/", "", value, flags=re.I)

    value = value.split("#", 1)[0].split("?", 1)[0].strip("/")
    if value.endswith(".git"):
        value = value[:-4]

    parts = value.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid repo format: '{repo}'. Use owner/repo.")

    owner, name = parts[0], parts[1]
    if not re.match(r"^[A-Za-z0-9_.-]+$", owner) or not re.match(r"^[A-Za-z0-9_.-]+$", name):
        raise ValueError(f"Invalid repo format: '{repo}'. Use owner/repo.")
    return f"{owner}/{name}"


def _first_value(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _extract_history_fields(repo: str, results: dict, duration_ms: int) -> dict:
    metadata = results.get("metadata") or {}
    cicd = results.get("cicd") or {}
    deps = results.get("dependencies") or {}
    deps_info = deps.get("repo_info") or {}
    cicd_meta = cicd.get("meta") or {}
    health = deps.get("health") or {}
    dependencies = deps.get("dependencies") or []
    alerts = deps.get("dependabot_alerts") or []

    detected = cicd.get("detected") or {}
    platforms = sorted(detected.keys())

    build_verification = cicd.get("build_verification") or {}

    outdated_count = 0
    for dep in dependencies:
        current = dep.get("version") or dep.get("current_version") or dep.get("constraint")
        latest = dep.get("latest_version")
        is_outdated = dep.get("is_outdated")
        if is_outdated is True or (latest and current and str(latest) != str(current)):
            outdated_count += 1

    license_value = _first_value(
        deps_info.get("license"),
        deps_info.get("license_name"),
        metadata.get("license_name"),
        cicd_meta.get("license"),
    )

    return {
        "language": _first_value(metadata.get("language"), deps_info.get("language"), cicd_meta.get("language"), "Unknown"),
        "health_score": health.get("score"),
        "risk_level": health.get("risk_level", "UNKNOWN"),
        "stars": _first_value(metadata.get("stars"), deps_info.get("stargazers_count"), cicd_meta.get("stars")),
        "forks": _first_value(metadata.get("forks"), deps_info.get("forks_count"), cicd_meta.get("forks")),
        "open_issues": _first_value(metadata.get("open_issues"), deps_info.get("open_issues_count"), cicd_meta.get("open_issues")),
        "default_branch": _first_value(metadata.get("default_branch"), deps_info.get("default_branch"), cicd_meta.get("default_branch")),
        "license_name": license_value,
        "topics": metadata.get("topics") or deps_info.get("topics") or [],
        "cicd_platforms": platforms,
        "build_health": build_verification.get("build_health", "unknown"),
        "total_dependencies": len(dependencies),
        "vulnerable_count": len(alerts),
        "outdated_count": outdated_count,
        "analysis_duration_ms": duration_ms,
    }


def _metadata_details_from_repo_id(db, repo_id: int | None) -> dict | None:
    if not repo_id:
        return None
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        return None

    commits = (
        db.query(Commit)
        .filter(Commit.repo_id == repo_id)
        .order_by(Commit.timestamp.desc())
        .all()
    )
    contributors = (
        db.query(Contributor)
        .filter(Contributor.repo_id == repo_id)
        .order_by(Contributor.total_commits.desc())
        .all()
    )
    file_trees = db.query(FileTree).filter(FileTree.repo_id == repo_id).all()

    return {
        "repository": {
            "id": repo.id,
            "full_name": repo.full_name,
            "owner": repo.owner,
            "name": repo.name,
            "description": repo.description,
            "url": repo.url,
            "language": repo.language,
            "stars": repo.stars,
            "forks": repo.forks,
            "open_issues": repo.open_issues,
            "default_branch": repo.default_branch,
            "license": repo.license_name,
            "is_archived": repo.is_archived,
            "topics": repo.topics,
            "readme": repo.readme,
            "fetched_at": repo.fetched_at.isoformat() if repo.fetched_at else None,
        },
        "commits": [
            {
                "commit_hash": c.commit_hash,
                "author_name": c.author_name,
                "message": c.message,
                "timestamp": c.timestamp.isoformat() if c.timestamp else None,
            }
            for c in commits
        ],
        "contributors": [
            {
                "username": c.username,
                "profile_url": c.profile_url,
                "avatar_url": c.avatar_url,
                "total_commits": c.total_commits,
            }
            for c in contributors
        ],
        "file_trees": [
            {
                "file_path": f.file_path,
                "file_type": f.file_type,
                "size": f.size,
            }
            for f in file_trees
        ],
    }


def _metadata_details_from_results(results: dict) -> dict | None:
    metadata = results.get("metadata") or {}
    repo_id = metadata.get("repo_id")
    if not repo_id:
        return None
    db = SessionLocal()
    try:
        return _metadata_details_from_repo_id(db, repo_id)
    finally:
        db.close()


def _history_to_dict(record: AnalysisHistory, include_payload: bool = True, include_metadata_details: bool = False) -> dict:
    payload = {
        "id": record.id,
        "history_id": record.id,
        "tenant_id": record.tenant_id,
        "repo": record.repo,
        "analyzed_at": record.analyzed_at.isoformat() if record.analyzed_at else None,
        "language": record.language,
        "health_score": record.health_score,
        "risk_level": record.risk_level,
        "batch_id": record.batch_id,
        "stars": record.stars,
        "forks": record.forks,
        "open_issues": record.open_issues,
        "default_branch": record.default_branch,
        "license_name": record.license_name,
        "topics": record.topics or [],
        "cicd_platforms": record.cicd_platforms or [],
        "build_health": record.build_health,
        "total_dependencies": record.total_dependencies,
        "vulnerable_count": record.vulnerable_count,
        "outdated_count": record.outdated_count,
        "analysis_duration_ms": record.analysis_duration_ms,
    }
    if include_payload:
        payload.update({
            "metadata": record.metadata_json,
            "cicd": record.cicd_json,
            "dependencies": record.dependencies_json,
        })
    if include_metadata_details:
        db = SessionLocal()
        try:
            metadata = record.metadata_json or {}
            payload["metadata_details"] = _metadata_details_from_repo_id(db, metadata.get("repo_id"))
        finally:
            db.close()
    return payload


def _save_history(repo: str, results: dict, batch_id: str | None, duration_ms: int, tenant_id: int | None) -> int | None:
    db = SessionLocal()
    try:
        fields = _extract_history_fields(repo, results, duration_ms)
        record = AnalysisHistory(
            tenant_id=tenant_id,
            repo=repo,
            analyzed_at=datetime.now(timezone.utc),
            metadata_json=results.get("metadata"),
            cicd_json=results.get("cicd"),
            dependencies_json=results.get("dependencies"),
            batch_id=batch_id,
            **fields,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.id
    except Exception as exc:
        db.rollback()
        print(f"Error saving history to DB: {exc}")
        return None
    finally:
        db.close()


def _clean_batch_id(value: str | None) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip()).strip("_.-")
    return base or f"batch_{int(datetime.now(timezone.utc).timestamp())}"


def _unique_batch_id(db, tenant_id: int, requested_batch_id: str | None) -> str:
    base = _clean_batch_id(requested_batch_id)
    existing_history = (
        db.query(AnalysisHistory.id)
        .filter(
            AnalysisHistory.tenant_id == tenant_id,
            AnalysisHistory.batch_id == base,
        )
        .first()
    )
    existing_batch = (
        db.query(AnalysisBatch.id)
        .filter(
            AnalysisBatch.tenant_id == tenant_id,
            AnalysisBatch.batch_id == base,
        )
        .first()
    )
    if not existing_history and not existing_batch:
        return base

    timestamp = int(datetime.now(timezone.utc).timestamp())
    for attempt in range(1, 100):
        candidate = f"{base}_{timestamp}_{attempt}"
        existing_history = (
            db.query(AnalysisHistory.id)
            .filter(
                AnalysisHistory.tenant_id == tenant_id,
                AnalysisHistory.batch_id == candidate,
            )
            .first()
        )
        existing_batch = (
            db.query(AnalysisBatch.id)
            .filter(
                AnalysisBatch.tenant_id == tenant_id,
                AnalysisBatch.batch_id == candidate,
            )
            .first()
        )
        if not existing_history and not existing_batch:
            return candidate
    return f"{base}_{timestamp}_{hashlib.sha1(base.encode('utf-8')).hexdigest()[:8]}"


def _create_analysis_batch(db, tenant_id: int, batch_id: str, repos: list[str]) -> AnalysisBatch:
    record = AnalysisBatch(
        tenant_id=tenant_id,
        batch_id=batch_id,
        status="running",
        requested_count=len(repos),
        completed_count=0,
        failed_count=0,
        requested_repos=repos,
        result_summary={"requested": len(repos), "completed": 0, "failed": 0},
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _finish_analysis_batch(
    tenant_id: int,
    batch_id: str,
    batch_results: list[dict],
    *,
    error: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        record = (
            db.query(AnalysisBatch)
            .filter(
                AnalysisBatch.tenant_id == tenant_id,
                AnalysisBatch.batch_id == batch_id,
            )
            .first()
        )
        if not record:
            return

        completed_count = sum(1 for item in batch_results if item.get("status") != "failed")
        failed_count = sum(1 for item in batch_results if item.get("status") == "failed")
        if error:
            status = "error"
        elif failed_count and not completed_count:
            status = "failed"
        elif failed_count:
            status = "completed_with_errors"
        else:
            status = "completed"

        record.status = status
        record.completed_count = completed_count
        record.failed_count = failed_count
        record.completed_at = datetime.now(timezone.utc)
        record.result_summary = {
            "requested": record.requested_count,
            "completed": completed_count,
            "failed": failed_count,
            "error": error,
        }
        record.raw_json = {"results": batch_results}
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"Error updating analysis batch {batch_id}: {exc}")
    finally:
        db.close()


def _analysis_cache_key(repo: str, tenant_id: int | None) -> str:
    tenant_part = tenant_id if tenant_id is not None else "anonymous"
    return f"analysis:{tenant_part}:{repo.lower()}"


def _cached_analysis(repo: str, tenant_id: int | None) -> dict | None:
    return analysis_cache.get(_analysis_cache_key(repo, tenant_id))


def _set_cached_analysis(repo: str, tenant_id: int | None, data: dict) -> None:
    analysis_cache.set(_analysis_cache_key(repo, tenant_id), data)


def _module_worker(module: str, target, progress_queue: queue.Queue, results: dict) -> None:
    try:
        def cb(event, msg):
            progress_queue.put({"module": module, "event": event, "data": msg, "level": "info"})

        results[module] = target(cb)
    except Exception as exc:
        results[module] = {"error": str(exc)}
        progress_queue.put({"module": module, "event": "module_error", "data": str(exc), "level": "error"})
    finally:
        progress_queue.put({"module": module, "event": "module_done", "data": f"{module} complete", "level": "done"})


def run_single_analysis_stream(repo: str, batch_id: str | None = None, use_cache: bool = True, tenant_id: int | None = None):
    """Run all analyzers in parallel and stream structured SSE messages."""
    cached = _cached_analysis(repo, tenant_id) if use_cache else None
    if cached:
        yield sse_event("progress", {
            "module": "cache",
            "event": "cache_hit",
            "data": f"Loaded cached analysis for {repo}",
            "level": "success",
        })
        now = datetime.now(timezone.utc).isoformat()
        cached_payload = {
            **cached,
            "repo": repo,
            "batch_id": batch_id,
            "analyzed_at": now,
            "analysis_duration_ms": 0,
            "cache_hit": True,
        }
        cached_payload["history_id"] = _save_history(repo, cached_payload, batch_id, 0, tenant_id)
        if not cached_payload.get("metadata_details"):
            cached_payload["metadata_details"] = _metadata_details_from_results(cached_payload)
        yield sse_event("done", cached_payload)
        return

    started = time.perf_counter()
    owner, repo_name = repo.split("/", 1)
    results = {"metadata": None, "cicd": None, "dependencies": None}
    progress_queue: queue.Queue = queue.Queue()

    workers = [
        threading.Thread(
            target=_module_worker,
            args=("metadata", lambda cb: extract_repo_metadata(owner, repo_name, progress_callback=cb), progress_queue, results),
            daemon=True,
        ),
        threading.Thread(
            target=_module_worker,
            args=("cicd", lambda cb: scan_repo_pipelines(owner, repo_name, progress_callback=cb), progress_queue, results),
            daemon=True,
        ),
        threading.Thread(
            target=_module_worker,
            args=("dependencies", lambda cb: analyze_deps(repo, progress_callback=cb), progress_queue, results),
            daemon=True,
        ),
    ]

    try:
        yield sse_event("progress", {
            "module": "system",
            "event": "analysis_started",
            "data": f"Starting full analysis for {repo}",
            "level": "info",
        })

        for worker in workers:
            worker.start()

        modules_done = 0
        while modules_done < 3:
            try:
                msg = progress_queue.get(timeout=30)
                if msg.get("event") == "module_done":
                    modules_done += 1
                yield sse_event("progress", msg)
            except queue.Empty:
                yield sse_event("progress", {
                    "module": "system",
                    "event": "heartbeat",
                    "data": "Still analyzing...",
                    "level": "info",
                })

        for worker in workers:
            worker.join(timeout=5)

        duration_ms = int((time.perf_counter() - started) * 1000)
        combined = {
            "repo": repo,
            "batch_id": batch_id,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "analysis_duration_ms": duration_ms,
            "metadata": results.get("metadata"),
            "cicd": results.get("cicd"),
            "dependencies": results.get("dependencies"),
            "cache_hit": False,
        }
        combined["metadata_details"] = _metadata_details_from_results(combined)
        combined["history_id"] = _save_history(repo, combined, batch_id, duration_ms, tenant_id)
        _set_cached_analysis(repo, tenant_id, combined)
        yield sse_event("done", combined)
    except Exception as exc:
        yield sse_event("error", {
            "module": "system",
            "event": "analysis_failed",
            "error": str(exc),
            "code": "analysis_stream_error",
        })


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/analyze/full", tags=["Orchestrator"])
async def analyze_full(request: Request):
    try:
        body = await request.json()
        repo = normalize_repo_input(body.get("repo", ""))
    except ValueError as exc:
        return JSONResponse({"error": str(exc), "code": "invalid_repo"}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Invalid JSON body", "code": "invalid_body"}, status_code=400)

    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        tenant_id = tenant.id
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    finally:
        db.close()

    return StreamingResponse(
        run_single_analysis_stream(repo, body.get("batch_id"), use_cache=body.get("use_cache", True), tenant_id=tenant_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/batch/analyze", tags=["Orchestrator"])
async def analyze_batch(request: Request):
    body = await request.json()
    repos = body.get("repos", [])
    requested_batch_id = body.get("batch_id")

    if not repos:
        return JSONResponse({"error": "No repositories provided"}, status_code=400)

    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        tenant_id = tenant.id
        batch_id = _unique_batch_id(db, tenant_id, requested_batch_id)
        batch_record = _create_analysis_batch(db, tenant_id, batch_id, repos)
        batch_db_id = batch_record.id
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()

    def batch_event_stream():
        batch_results = []
        try:
            yield sse_event("batch_started", {"batch_id": batch_id, "batch_db_id": batch_db_id, "total": len(repos)})
            for index, raw_repo in enumerate(repos):
                try:
                    repo = normalize_repo_input(raw_repo)
                except ValueError as exc:
                    failed = {"repo": raw_repo, "status": "failed", "error": str(exc)}
                    batch_results.append(failed)
                    yield sse_event("repo_failed", failed)
                    continue

                yield sse_event("batch_progress", {"current": index + 1, "total": len(repos), "repo": repo})
                last_done_data = None

                for message in run_single_analysis_stream(repo, batch_id, tenant_id=tenant_id):
                    yield message
                    if message.startswith("event: done\n"):
                        try:
                            last_done_data = json.loads(message.split("data: ", 1)[1].strip())
                        except Exception:
                            last_done_data = None

                if last_done_data:
                    batch_results.append(last_done_data)

            _finish_analysis_batch(tenant_id, batch_id, batch_results)
            yield sse_event("batch_done", {"batch_id": batch_id, "results": batch_results})
        except Exception as exc:
            _finish_analysis_batch(tenant_id, batch_id, batch_results, error=str(exc))
            yield sse_event("error", {"error": str(exc), "code": "batch_stream_error"})

    return StreamingResponse(
        batch_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/rate-limit", tags=["Shared"])
async def get_rate_limit():
    try:
        payload = get_github_client().get_rate_limit()
        payload["token_configured"] = bool(settings.GITHUB_TOKEN)
        return JSONResponse(payload)
    except GitHubAPIError as exc:
        return JSONResponse({
            "error": str(exc),
            "token_configured": bool(settings.GITHUB_TOKEN),
        }, status_code=502)


ARCHITECTURE_CACHE_DIR = settings.DATA_DIR / "architecture_cache"
ARCHITECTURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _architecture_cache_path(repo: str) -> Path:
    digest = hashlib.sha256(repo.encode("utf-8")).hexdigest()[:16]
    return ARCHITECTURE_CACHE_DIR / f"{digest}.json"


@app.get("/api/architecture/cache/{owner}/{repo_name}", tags=["Shared"])
async def get_architecture_cache(owner: str, repo_name: str):
    try:
        repo = normalize_repo_input(f"{owner}/{repo_name}")
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    cache_path = _architecture_cache_path(repo)
    if not cache_path.exists():
        return JSONResponse({"error": "Architecture cache not found"}, status_code=404)

    try:
        return JSONResponse(json.loads(cache_path.read_text(encoding="utf-8")))
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/architecture/cache", tags=["Shared"])
async def save_architecture_cache(request: Request):
    body = await request.json()
    try:
        repo = normalize_repo_input(body.get("repo", ""))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    data = body.get("data")
    if not isinstance(data, dict):
        return JSONResponse({"error": "Architecture analysis data is required"}, status_code=400)

    payload = {
        "repo": repo,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "source": "codeflow",
        "data": data,
    }

    try:
        _architecture_cache_path(repo).write_text(json.dumps(payload, default=str), encoding="utf-8")
        return JSONResponse({"status": "saved", "repo": repo, "analyzed_at": payload["analyzed_at"]})
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/architecture/github", tags=["Shared"])
def proxy_architecture_github(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com":
        return JSONResponse({"error": "Only https://api.github.com requests are allowed"}, status_code=400)
    if not (parsed.path == "/rate_limit" or parsed.path.startswith("/repos/")):
        return JSONResponse({"error": "GitHub API path is not allowed"}, status_code=400)

    headers = {"Accept": "application/vnd.github.v3+json"}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    try:
        resp = _github_proxy_session.get(url, headers=headers, timeout=25)
        response_headers = {
            name: resp.headers[name]
            for name in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset")
            if name in resp.headers
        }
        try:
            content = resp.json()
        except ValueError:
            content = {"error": resp.text or "GitHub returned a non-JSON response"}
        return JSONResponse(content, status_code=resp.status_code, headers=response_headers)
    except requests.RequestException as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/api/architecture/archive/{owner}/{repo_name}", tags=["Shared"])
def get_architecture_archive(owner: str, repo_name: str):
    try:
        repo = normalize_repo_input(f"{owner}/{repo_name}")
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    headers = {"Accept": "application/vnd.github.v3+json"}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    try:
        resp = _github_proxy_session.get(f"https://api.github.com/repos/{repo}/zipball", headers=headers, timeout=60)
        if not resp.ok:
            try:
                content = resp.json()
            except ValueError:
                content = {"error": resp.text or f"GitHub returned {resp.status_code}"}
            return JSONResponse(content, status_code=resp.status_code)
        return Response(
            content=resp.content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{owner}-{repo_name}.zip"'},
        )
    except requests.RequestException as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/api/health", tags=["Shared"])
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/cache/status", tags=["Shared"])
async def cache_status():
    return JSONResponse({
        "analysis_cache": analysis_cache.stats(),
        "cache_ttl": settings.CACHE_TTL,
    })


@app.get("/api/history", tags=["Shared"])
async def get_history(request: Request):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        records = (
            db.query(AnalysisHistory)
            .filter(AnalysisHistory.tenant_id == tenant.id)
            .order_by(AnalysisHistory.analyzed_at.desc())
            .all()
        )
        return JSONResponse([_history_to_dict(record) for record in records])
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@app.get("/api/history/search", tags=["Shared"])
async def search_history(
    request: Request,
    q: str = "",
    language: str = "",
    min_score: float | None = Query(default=None),
):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        query = db.query(AnalysisHistory).filter(AnalysisHistory.tenant_id == tenant.id)
        if q:
            query = query.filter(AnalysisHistory.repo.ilike(f"%{q}%"))
        if language:
            query = query.filter(AnalysisHistory.language.ilike(language))
        if min_score is not None:
            query = query.filter(AnalysisHistory.health_score >= min_score)
        records = query.order_by(AnalysisHistory.analyzed_at.desc()).all()
        return JSONResponse([_history_to_dict(record) for record in records])
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@app.get("/api/compare", tags=["Shared"])
async def compare_repositories(request: Request, repos: str = Query(..., description="Comma-separated owner/repo list")):
    requested = []
    for item in repos.split(","):
        if not item.strip():
            continue
        try:
            requested.append(normalize_repo_input(item))
        except ValueError:
            requested.append(item.strip())

    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        comparisons = []
        missing = []
        for repo in requested:
            record = (
                db.query(AnalysisHistory)
                .filter(
                    AnalysisHistory.tenant_id == tenant.id,
                    AnalysisHistory.repo == repo,
                )
                .order_by(AnalysisHistory.analyzed_at.desc())
                .first()
            )
            if not record:
                missing.append(repo)
                continue
            comparisons.append(_history_to_dict(record, include_payload=False))

        baseline = comparisons[0]["health_score"] if comparisons and comparisons[0].get("health_score") is not None else None
        for item in comparisons:
            score = item.get("health_score")
            item["score_delta_from_first"] = None if baseline is None or score is None else score - baseline

        return JSONResponse({"repos": comparisons, "missing": missing})
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


def _record_markdown(record: dict) -> str:
    metadata = record.get("metadata") or {}
    cicd = record.get("cicd") or {}
    deps = record.get("dependencies") or {}
    platforms = ", ".join(record.get("cicd_platforms") or []) or "None detected"
    return "\n".join([
        f"# Repository Intelligence Report: {record.get('repo')}",
        "",
        f"- Analyzed at: {record.get('analyzed_at')}",
        f"- Language: {record.get('language') or 'Unknown'}",
        f"- Health score: {record.get('health_score') if record.get('health_score') is not None else 'N/A'}",
        f"- Risk level: {record.get('risk_level') or 'UNKNOWN'}",
        f"- Stars: {record.get('stars') or 0}",
        f"- Forks: {record.get('forks') or 0}",
        f"- Open issues: {record.get('open_issues') or 0}",
        f"- Default branch: {record.get('default_branch') or 'N/A'}",
        f"- License: {record.get('license_name') or 'N/A'}",
        f"- CI/CD platforms: {platforms}",
        f"- Total dependencies: {record.get('total_dependencies') or 0}",
        f"- Vulnerable dependencies: {record.get('vulnerable_count') or 0}",
        f"- Outdated dependencies: {record.get('outdated_count') or 0}",
        f"- Duration: {record.get('analysis_duration_ms') or 0} ms",
        "",
        "## Raw Summary",
        "",
        "```json",
        json.dumps({"metadata": metadata, "cicd": cicd, "dependencies": deps}, indent=2, default=str),
        "```",
        "",
    ])


@app.get("/api/history/{record_id}/export", tags=["Shared"])
async def export_history_record(request: Request, record_id: int, format: str = Query("json", pattern="^(json|markdown)$")):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        record = (
            db.query(AnalysisHistory)
            .filter(
                AnalysisHistory.id == record_id,
                AnalysisHistory.tenant_id == tenant.id,
            )
            .first()
        )
        if not record:
            return JSONResponse({"error": "Record not found"}, status_code=404)

        data = _history_to_dict(record)
        if format == "markdown":
            content = _record_markdown(data)
            media_type = "text/markdown"
            filename = f"repo-intelligence-{record_id}.md"
        else:
            content = json.dumps(jsonable_encoder(data), indent=2, default=str)
            media_type = "application/json"
            filename = f"repo-intelligence-{record_id}.json"

        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@app.get("/api/history/{record_id}", tags=["Shared"])
async def get_history_record(request: Request, record_id: int):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        record = (
            db.query(AnalysisHistory)
            .filter(
                AnalysisHistory.id == record_id,
                AnalysisHistory.tenant_id == tenant.id,
            )
            .first()
        )
        if not record:
            return JSONResponse({"error": "Record not found"}, status_code=404)
        return JSONResponse(_history_to_dict(record, include_metadata_details=True))
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@app.delete("/api/history/{record_id}", tags=["Shared"])
async def delete_history_record(request: Request, record_id: int):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        record = (
            db.query(AnalysisHistory)
            .filter(
                AnalysisHistory.id == record_id,
                AnalysisHistory.tenant_id == tenant.id,
            )
            .first()
        )
        if not record:
            return JSONResponse({"error": "Record not found"}, status_code=404)
        db.delete(record)
        db.commit()
        return {"status": "deleted", "id": record_id}
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


@app.delete("/api/history", tags=["Shared"])
async def clear_history(request: Request):
    db = SessionLocal()
    try:
        tenant = resolve_request_tenant(db, request)
        db.query(AnalysisBatch).filter(AnalysisBatch.tenant_id == tenant.id).delete()
        db.query(AnalysisHistory).filter(AnalysisHistory.tenant_id == tenant.id).delete()
        db.commit()
        analysis_cache.clear()
        return {"status": "cleared"}
    except AuthRequiredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitHub Repository Intelligence Dashboard")
    parser.add_argument("--host", default=settings.HOST, help="Host to bind")
    parser.add_argument("--port", type=int, default=settings.PORT, help="Port to bind")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  GitHub Repository Intelligence Dashboard v2.0.0")
    print(f"  Open http://{args.host}:{args.port} in your browser")
    print("=" * 60 + "\n")

    uvicorn.run(app, host=args.host, port=args.port)
