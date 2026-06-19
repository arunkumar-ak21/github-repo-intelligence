"""
Dependency Analysis API Routes
===============================
FastAPI router for Arun's dependency analysis endpoints.
"""

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from core.config import settings
from core.github_client import get_github_client, RateLimitError, GitHubAPIError
from .analysis import analyze_repo

router = APIRouter(prefix="/api/deps", tags=["Dependency Analysis"])

_executor = ThreadPoolExecutor(max_workers=4)

# ---------------------------------------------------------------------------
# Data persistence (JSON file — same approach as Arun's original)
# ---------------------------------------------------------------------------
DATA_DIR = settings.DATA_DIR
DATA_FILE = DATA_DIR / "dep_analysis_results.json"


def _load_history() -> list[dict]:
    DATA_DIR.mkdir(exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text("[]", encoding="utf-8")
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save_record(record: dict):
    history = _load_history()
    history.append(record)
    DATA_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _format_result(analysis: dict) -> dict:
    """Reshape analyzer output into storage schema."""
    health = analysis.get("health", {})
    return {
        "id": str(uuid.uuid4()),
        "repo": analysis.get("repository", ""),
        "analyzed_at": analysis.get("analyzed_at", datetime.now(timezone.utc).isoformat()),
        "metadata": analysis.get("repo_info", {}),
        "ecosystems": analysis.get("ecosystems", {}),
        "dependencies": analysis.get("dependencies", []),
        "dependabot_alerts": analysis.get("dependabot_alerts", []),
        "health_score": health.get("score", 0),
        "risk_level": health.get("risk_level", "HIGH"),
        "score_breakdown": health.get("breakdown", {}),
        "summary_stats": health.get("summary_stats", {}),
        "errors": analysis.get("errors", []),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/analyze", summary="Analyze dependencies for a repository")
async def analyze_single(request: Request):
    """Analyze a single repository's dependencies."""
    body = await request.json()
    repo = body.get("repo", "").strip()

    if not repo or "/" not in repo or len(repo.split("/")) != 2:
        return JSONResponse(
            {"error": f"Invalid repo format: '{repo}'. Use owner/repo"},
            status_code=400,
        )

    loop = asyncio.get_event_loop()
    try:
        analysis = await loop.run_in_executor(_executor, analyze_repo, repo)
        record = _format_result(analysis)
        _save_record(record)
        return JSONResponse(record)
    except RateLimitError as exc:
        return JSONResponse({"error": str(exc)}, status_code=429)
    except GitHubAPIError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/analyze/batch", summary="Batch analyze with SSE progress")
async def analyze_batch(request: Request):
    """Analyze multiple repositories with Server-Sent Events for progress."""
    body = await request.json()
    repos = body.get("repos", [])

    valid_repos = [
        r.strip() for r in repos
        if r.strip() and "/" in r.strip() and len(r.strip().split("/")) == 2
    ]

    if not valid_repos:
        return JSONResponse({"error": "No valid repositories provided"}, status_code=400)

    def event_stream():
        completed = 0
        for i, repo in enumerate(valid_repos):
            progress_data = json.dumps({
                "index": i + 1,
                "total": len(valid_repos),
                "repo": repo,
                "status": "analyzing",
            })
            yield f"event: progress\ndata: {progress_data}\n\n"

            try:
                analysis = analyze_repo(repo)
                record = _format_result(analysis)
                _save_record(record)
                completed += 1
                yield f"event: result\ndata: {json.dumps(record, default=str)}\n\n"
            except RateLimitError as exc:
                error_data = json.dumps({"repo": repo, "error": str(exc), "fatal": True})
                yield f"event: error\ndata: {error_data}\n\n"
                break
            except Exception as exc:
                error_data = json.dumps({"repo": repo, "error": str(exc), "fatal": False})
                yield f"event: error\ndata: {error_data}\n\n"

        done_data = json.dumps({"completed": completed, "total": len(valid_repos)})
        yield f"event: done\ndata: {done_data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history", summary="Get dependency analysis history")
async def get_history():
    """Return all saved analysis results."""
    return JSONResponse(_load_history())


@router.get("/history/{record_id}", summary="Get a single analysis record")
async def get_history_record(record_id: str):
    """Return a single saved result by UUID."""
    history = _load_history()
    for record in history:
        if record.get("id") == record_id:
            return JSONResponse(record)
    return JSONResponse({"error": "Record not found"}, status_code=404)


@router.delete("/history", summary="Clear analysis history")
async def clear_history():
    """Clear all saved analysis history."""
    DATA_DIR.mkdir(exist_ok=True)
    DATA_FILE.write_text("[]", encoding="utf-8")
    return JSONResponse({"message": "History cleared"})
