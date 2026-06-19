"""
Metadata API Routes
===================
FastAPI router for Mohit's metadata extraction endpoints.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.database import get_db
from .models import Repository, Commit, Contributor, FileTree
from .extractor import extract_repo_metadata

router = APIRouter(prefix="/api/meta", tags=["Metadata Extraction"])

# Thread pool for running sync extraction in background
_executor = ThreadPoolExecutor(max_workers=4)


@router.post("/extract", summary="Extract metadata for a GitHub repository")
async def trigger_extraction(request: Request):
    """
    Takes owner/repo and extracts metadata, commits, contributors, file tree.
    Runs in a thread pool so it doesn't block the event loop.
    """
    body = await request.json()

    # Accept both formats: {"owner": "x", "repo": "y"} and {"repo": "x/y"}
    owner = body.get("owner", "")
    repo_name = body.get("repo", "")

    if not owner and "/" in repo_name:
        parts = repo_name.strip().split("/")
        if len(parts) == 2:
            owner, repo_name = parts

    if not owner or not repo_name:
        return JSONResponse(
            {"error": "Provide 'owner' and 'repo', or 'repo' as 'owner/repo'"},
            status_code=400,
        )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor, extract_repo_metadata, owner, repo_name
    )

    if result.get("error"):
        return JSONResponse({"error": result["error"]}, status_code=502)

    return JSONResponse(result)


@router.get("/repos", summary="List all extracted repositories")
def get_repositories(db: Session = Depends(get_db)):
    """Returns all repositories stored in the database."""
    repos = db.query(Repository).order_by(Repository.fetched_at.desc()).all()
    return [
        {
            "id": r.id,
            "full_name": r.full_name,
            "description": r.description,
            "url": r.url,
            "language": r.language,
            "stars": r.stars,
            "forks": r.forks,
            "topics": r.topics,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        }
        for r in repos
    ]


@router.get("/repos/{repo_id}/metrics", summary="Get full metrics for a repository")
def get_repo_metrics(repo_id: int, db: Session = Depends(get_db)):
    """Fetch deeply nested metrics for the frontend dashboard."""
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found.")

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
