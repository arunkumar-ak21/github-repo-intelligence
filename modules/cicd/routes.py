"""
CI/CD API Routes
================
FastAPI router for Satyam's CI/CD pipeline analysis endpoints.
Adapted from Flask routes to FastAPI.
"""

import asyncio
import json
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse

from core.config import settings
from .scanner import scan_repo_pipelines

router = APIRouter(prefix="/api/cicd", tags=["CI/CD Pipeline Analysis"])

_executor = ThreadPoolExecutor(max_workers=4)

# In-memory job registry
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _job_summary(job_id: str, data: dict) -> dict:
    """Build a compact summary dict."""
    security = data.get("security_results", [])
    avg_score = (
        round(sum(s["score"] for s in security) / len(security))
        if security else None
    )
    return {
        "job_id": job_id,
        "repo": data.get("slug", data.get("repo", "unknown")),
        "scanned_at": data.get("scanned_at", ""),
        "avg_score": avg_score,
        "pipeline_count": len(data.get("analyses", [])),
        "issues": sum(s.get("issues_found", 0) for s in security),
        "language": data.get("meta", {}).get("language", ""),
        "has_error": bool(data.get("error")),
    }


def _parse_repo_slug(repo_input: str) -> tuple[str, str]:
    """Parse 'owner/repo' or full GitHub URL → (owner, repo)."""
    repo_input = repo_input.strip().rstrip("/")
    if repo_input.endswith(".git"):
        repo_input = repo_input[:-4]
    if repo_input.startswith("http"):
        from urllib.parse import urlparse
        parts = urlparse(repo_input).path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        raise ValueError(f"Cannot parse URL: {repo_input}")
    if "/" in repo_input:
        parts = repo_input.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
    raise ValueError(f"Invalid format: '{repo_input}'. Use 'owner/repo'.")


@router.post("/scan", summary="Scan CI/CD pipelines for a repository")
async def start_scan(request: Request):
    """Kick off a background CI/CD scan. Returns {job_id}."""
    body = await request.json()

    # Handle single or multiple repo input
    repo_str = body.get("repo", "").strip()
    repos_input = body.get("repos", [])
    if not repos_input and repo_str:
        import re
        repos_input = [r.strip() for r in re.split(r"[\n,]+", repo_str) if r.strip()]

    if not repos_input:
        return JSONResponse({"error": "At least one repository is required"}, status_code=400)

    repos_to_scan = []
    for r in repos_input:
        try:
            owner, name = _parse_repo_slug(r)
            repos_to_scan.append((owner, name))
        except ValueError as e:
            return JSONResponse({"error": f"Invalid format '{r}': {e}"}, status_code=400)

    job_id = uuid.uuid4().hex[:10]
    q = queue.Queue()
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "queue": q, "result": None}

    def _run():
        try:
            combined_result = {
                "slug": ", ".join(f"{o}/{r}" for o, r in repos_to_scan),
                "meta": {"stars": 0, "forks": 0, "language": "", "description": "", "url": ""},
                "detected": {},
                "analyses": [],
                "security_results": [],
                "latest_run": {},
                "error": None,
            }

            for i, (owner, repo_name) in enumerate(repos_to_scan, 1):
                slug = f"{owner}/{repo_name}"
                q.put({"event": "connecting", "data": f"({i}/{len(repos_to_scan)}) Scanning {slug}..."})

                def _cb(event, msg):
                    q.put({"event": event, "data": f"[{slug}] {msg}"})

                result = scan_repo_pipelines(owner, repo_name, progress_callback=_cb)

                if result.get("error"):
                    q.put({"event": "warn", "data": f"Failed to scan {slug}: {result['error']}"})
                    if not result.get("analyses"):
                        continue

                # Merge metadata
                if len(repos_to_scan) == 1:
                    combined_result["meta"] = result.get("meta", {})
                    combined_result["slug"] = slug
                else:
                    combined_result["meta"]["stars"] += result.get("meta", {}).get("stars", 0)
                    combined_result["meta"]["forks"] += result.get("meta", {}).get("forks", 0)

                # Merge detected
                from .detector import get_platform_config
                for platform, file_list in result.get("detected", {}).items():
                    if platform not in combined_result["detected"]:
                        cfg = get_platform_config(platform)
                        combined_result["detected"][platform] = {
                            "files": [],
                            "docs_url": cfg.get("docs_url", ""),
                            "icon": cfg.get("icon", "📦"),
                            "color": cfg.get("color", "#334155"),
                        }
                    for f in file_list:
                        combined_result["detected"][platform]["files"].append(
                            f"{slug}:{f}" if len(repos_to_scan) > 1 else f
                        )

                # Merge analyses and security
                for a in result.get("analyses", []):
                    if len(repos_to_scan) > 1:
                        a["file"] = f"{slug}:{a.get('file', '')}"
                    combined_result["analyses"].append(a)

                for s in result.get("security_results", []):
                    if len(repos_to_scan) > 1:
                        s["file"] = f"{slug}:{s.get('file', '')}"
                    combined_result["security_results"].append(s)

                combined_result["latest_run"] = result.get("latest_run", {})

            # Save to disk
            job_dir = settings.REPORTS_DIR / job_id
            job_dir.mkdir(parents=True, exist_ok=True)

            save = {
                "job_id": job_id,
                "scanned_at": datetime.now().isoformat(),
                **combined_result,
            }
            save["analyses"] = [
                {k: v for k, v in a.items() if k != "raw_content"}
                for a in combined_result.get("analyses", [])
            ]

            (job_dir / "data.json").write_text(
                json.dumps(save, indent=2, default=str), encoding="utf-8"
            )

            with _jobs_lock:
                _jobs[job_id]["result"] = combined_result
                _jobs[job_id]["status"] = "done"

            q.put({"event": "done", "data": job_id})

        except Exception as exc:
            import traceback
            traceback.print_exc()
            with _jobs_lock:
                _jobs[job_id]["status"] = "error"
            q.put({"event": "error", "data": str(exc)})
        finally:
            q.put(None)

    threading.Thread(target=_run, daemon=True).start()
    return JSONResponse({"job_id": job_id})


@router.get("/stream/{job_id}", summary="SSE stream for scan progress")
async def stream(job_id: str):
    """Server-Sent Events endpoint — streams live scan progress."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        data_path = settings.REPORTS_DIR / job_id / "data.json"
        if data_path.exists():
            return JSONResponse({"error": "already_done", "job_id": job_id}, status_code=410)
        return JSONResponse({"error": "Job not found"}, status_code=404)

    q = job["queue"]

    def _generate():
        while True:
            msg = q.get()
            if msg is None:
                break
            yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/jobs/{job_id}", summary="Get scan results")
async def get_job(job_id: str):
    """Return saved scan data as JSON."""
    data_path = settings.REPORTS_DIR / job_id / "data.json"
    if not data_path.exists():
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return JSONResponse(json.loads(data_path.read_text(encoding="utf-8")))


@router.get("/history", summary="List past CI/CD scans")
async def get_cicd_history():
    """List all past scans ordered by most recent."""
    items = []
    reports_dir = settings.REPORTS_DIR
    if reports_dir.exists():
        dirs = sorted(
            (d for d in reports_dir.iterdir() if d.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for job_dir in dirs:
            data_path = job_dir / "data.json"
            if data_path.exists():
                try:
                    data = json.loads(data_path.read_text(encoding="utf-8"))
                    items.append(_job_summary(job_dir.name, data))
                except Exception:
                    pass
    return JSONResponse(items)

@router.get("/reports/{report_id}", summary="Open generated CI/CD HTML report")
async def get_cicd_html_report(report_id: str, download: bool = False):
    report_path = settings.REPORTS_DIR / report_id / "report.html"

    if not report_path.exists():
        return JSONResponse({"error": "Report not found"}, status_code=404)

    if download:
        return FileResponse(
            report_path,
            media_type="text/html",
            filename=f"cicd_report_{report_id}.html",
        )
    else:
        return FileResponse(
            report_path,
            media_type="text/html",
        )


@router.get(
    "/build-status/{owner}/{repo_name}",
    summary="Verify build artifacts for a repository",
)
async def get_build_status(owner: str, repo_name: str):
    """Check recent GitHub Actions workflow runs and verify whether they
    produce build artifacts. Returns a build health report with per-run
    artifact details.

    Artifact production is used as a proxy for successful compilation /
    build: if a workflow run succeeds but produces no artifacts, it may
    indicate a missing ``upload-artifact`` step or a build misconfiguration.
    """
    from .build_verifier import verify_build_artifacts

    try:
        _parse_repo_slug(f"{owner}/{repo_name}")
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    try:
        report = verify_build_artifacts(owner, repo_name)
        return JSONResponse(report)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
