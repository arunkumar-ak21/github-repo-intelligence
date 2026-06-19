"""
Metadata Extractor
==================
Adapted from Mohit's tasks.py — same logic, but runs directly
(no Celery, no Redis). Uses the shared GitHubClient instead of PyGithub.
"""

import logging
from datetime import datetime, timezone

from core.database import SessionLocal
from core.github_client import get_github_client, GitHubAPIError
from .models import Repository, Commit, Contributor, FileTree

logger = logging.getLogger(__name__)


def extract_repo_metadata(owner: str, repo_name: str, progress_callback=None) -> dict:
    """
    Full metadata extraction pipeline for a single repository.

    Replaces Mohit's Celery chain:
      create_repo_metadata_task → chord([contributors, commits, file_tree]) → finalize

    Now runs synchronously in a single function (called from a thread pool
    by the FastAPI route so it doesn't block).

    Parameters
    ----------
    owner : str
        Repository owner (e.g. "fastapi").
    repo_name : str
        Repository name (e.g. "fastapi").
    progress_callback : callable or None
        Optional (event, message) callback for live progress streaming.

    Returns
    -------
    dict with repo_id and extraction summary.
    """
    _cb = progress_callback if callable(progress_callback) else (lambda e, m: None)
    client = get_github_client()
    full_name = f"{owner}/{repo_name}"
    db = SessionLocal()

    try:
        # ── Step 1: Repo Metadata ────────────────────────────────────────
        _cb("meta_connecting", f"Fetching metadata for {full_name}...")
        repo_data = client.get_repo_info(full_name)
        if repo_data is None:
            return {"error": f"Repository '{full_name}' not found on GitHub."}

        # Upsert into database
        db_repo = db.query(Repository).filter(
            Repository.full_name == full_name
        ).first()

        if not db_repo:
            db_repo = Repository(
                owner=owner, name=repo_name, full_name=full_name
            )
            db.add(db_repo)

        db_repo.description = repo_data.get("description", "")
        db_repo.url = repo_data.get("html_url", "")
        db_repo.language = repo_data.get("language")
        db_repo.stars = repo_data.get("stargazers_count", 0)
        db_repo.forks = repo_data.get("forks_count", 0)
        db_repo.open_issues = repo_data.get("open_issues_count", 0)
        db_repo.default_branch = repo_data.get("default_branch", "main")
        db_repo.license_name = (repo_data.get("license") or {}).get("spdx_id", "N/A")
        db_repo.is_archived = repo_data.get("archived", False)
        db_repo.fetched_at = datetime.now(timezone.utc)

        # Topics
        _cb("meta_topics", "Fetching topics...")
        topics = client.get_topics(full_name)
        db_repo.topics = ", ".join(topics) if topics else ""

        # README
        _cb("meta_readme", "Fetching README...")
        readme = client.get_readme(full_name)
        db_repo.readme = readme or "No README file found."

        db.commit()
        db.refresh(db_repo)
        repo_id = db_repo.id

        _cb("meta_done", f"★ {db_repo.stars}  ·  Language: {db_repo.language or 'N/A'}")

        # ── Step 2: Contributors ─────────────────────────────────────────
        _cb("meta_contributors", "Extracting contributors...")
        contributors_raw = client.get_contributors(full_name)

        # Clear old data, insert fresh
        db.query(Contributor).filter(Contributor.repo_id == repo_id).delete()
        for c in contributors_raw:
            db.add(Contributor(
                repo_id=repo_id,
                username=c.get("login", "unknown"),
                profile_url=c.get("html_url", ""),
                avatar_url=c.get("avatar_url", ""),
                total_commits=c.get("contributions", 0),
            ))

        # ── Step 3: Commits ──────────────────────────────────────────────
        _cb("meta_commits", "Extracting commit history...")
        commits_raw = client.get_commits(full_name)

        db.query(Commit).filter(Commit.repo_id == repo_id).delete()
        for c in commits_raw:
            commit_data = c.get("commit", {})
            author_data = commit_data.get("author", {})
            time_str = author_data.get("date")
            try:
                parsed_time = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ") if time_str else datetime.now(timezone.utc)
            except (ValueError, TypeError):
                parsed_time = datetime.now(timezone.utc)

            db.add(Commit(
                repo_id=repo_id,
                commit_hash=c.get("sha", ""),
                author_name=author_data.get("name", "Unknown"),
                message=commit_data.get("message", ""),
                timestamp=parsed_time,
            ))

        # ── Step 4: File Tree ────────────────────────────────────────────
        _cb("meta_filetree", "Extracting file tree...")
        branch = db_repo.default_branch or "main"
        tree_paths = client.get_repo_tree(full_name, branch)

        db.query(FileTree).filter(FileTree.repo_id == repo_id).delete()

        # We only have file paths from the tree API; get the full tree
        # with types and sizes from the git tree endpoint
        tree_url = f"https://api.github.com/repos/{full_name}/git/trees/{branch}?recursive=1"
        try:
            tree_resp = client._request("GET", tree_url)
            tree_items = tree_resp.json().get("tree", [])
            for item in tree_items:
                db.add(FileTree(
                    repo_id=repo_id,
                    file_path=item.get("path", ""),
                    file_type=item.get("type", "blob"),
                    size=item.get("size"),
                ))
        except Exception as e:
            logger.warning("Could not fetch file tree for %s: %s", full_name, e)

        db.commit()

        _cb("meta_counting", "Fetching total counts...")
        total_commits = client.get_paginated_total_count(f"/repos/{full_name}/commits")
        total_contributors = client.get_paginated_total_count(f"/repos/{full_name}/contributors")

        _cb("meta_complete", f"Metadata extraction complete for {full_name}")

        return {
            "status": "SUCCESS",
            "repo_id": repo_id,
            "full_name": full_name,
            "stars": db_repo.stars,
            "language": db_repo.language,
            "total_commits": total_commits,
            "commits_analyzed": len(commits_raw),
            "total_contributors": total_contributors,
            "contributors_loaded": len(contributors_raw),
        }

    except GitHubAPIError as exc:
        db.rollback()
        return {"error": str(exc)}
    except Exception as exc:
        db.rollback()
        logger.exception("Extraction failed for %s", full_name)
        return {"error": str(exc)}
    finally:
        db.close()
