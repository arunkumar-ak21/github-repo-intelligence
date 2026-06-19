"""
CI/CD Pipeline Scanner
======================
Adapted from Satyam's github_agent.py to use the shared GitHubClient.
Core logic unchanged — just replaced direct requests calls with the
shared client methods.
"""

import os
import re
import tempfile
import logging
import uuid
from pathlib import Path

from core.config import settings
from core.github_client import get_github_client, GitHubAPIError
from .analyzer import analyze_pipeline
from .build_verifier import verify_build_artifacts
from .security_checker import run_security_checks
from .detector import PIPELINE_FILE_MAP
from .report_generator import generate_html_report

logger = logging.getLogger(__name__)


def find_pipeline_files_in_tree(file_paths: list[str]) -> dict[str, list[str]]:
    """Map repo file paths to their CI/CD platform."""
    detected: dict[str, list[str]] = {}
    for path in file_paths:
        platform = None
        if path.startswith(".github/workflows/") and (
            path.endswith(".yml") or path.endswith(".yaml")
        ):
            platform = "GitHub Actions"
        elif path.startswith(".teamcity/") and (
            path.endswith(".kts") or path.endswith(".xml")
        ):
            platform = "TeamCity"
        elif path in (".drone.yml", ".drone.yaml"):
            platform = "Drone CI"
        else:
            platform = PIPELINE_FILE_MAP.get(path)

        if platform:
            detected.setdefault(platform, []).append(path)
    return detected


def scan_repo_pipelines(
    owner: str,
    repo: str,
    progress_callback=None,
) -> dict:
    """
    Full CI/CD analysis pipeline for a single repository.
    Adapted from Satyam's analyze_github_repo() function.

    Parameters
    ----------
    owner : str
        Repository owner.
    repo : str
        Repository name.
    progress_callback : callable or None
        Optional (event, message) callback for live progress streaming.

    Returns
    -------
    dict with keys: slug, meta, detected, analyses, security_results, latest_run, error
    """
    _cb = progress_callback if callable(progress_callback) else (lambda e, m: None)
    client = get_github_client()
    full_name = f"{owner}/{repo}"

    result = {
        "slug": full_name,
        "meta": {},
        "detected": {},
        "analyses": [],
        "security_results": [],
        "build_verification": {},
        "latest_run": {},
        "error": None,
    }

    # 1. Repo metadata
    _cb("cicd_connecting", f"Connecting to GitHub — {full_name}")
    try:
        meta = client.get_repo_info(full_name)
        if meta is None:
            result["error"] = f"Repository '{full_name}' not found."
            return result
    except Exception as e:
        result["error"] = str(e)
        return result

    result["meta"] = {
        "name": meta.get("full_name", full_name),
        "description": meta.get("description", ""),
        "stars": meta.get("stargazers_count", 0),
        "forks": meta.get("forks_count", 0),
        "language": meta.get("language", "Unknown"),
        "default_branch": meta.get("default_branch", "main"),
        "url": meta.get("html_url", ""),
        "private": meta.get("private", False),
        "open_issues": meta.get("open_issues_count", 0),
    }
    branch = result["meta"]["default_branch"]

    _cb("cicd_metadata", (
        f"★ {result['meta']['stars']}  ·  "
        f"🍴 {result['meta']['forks']}  ·  "
        f"Language: {result['meta']['language']}"
    ))

    # 2. Repo tree
    _cb("cicd_detecting", "Scanning file tree for pipeline files…")
    try:
        all_paths = client.get_repo_tree(full_name, branch)
    except Exception as e:
        result["error"] = f"Failed to fetch repo tree: {e}"
        return result

    # 3. Detect pipeline files
    detected = find_pipeline_files_in_tree(all_paths)
    result["detected"] = detected
    if not detected:
        _cb("cicd_detected", "No CI/CD pipeline files found in this repository")
        return result

    platforms_str = "  ·  ".join(
        f"{p}: {len(f)} file{'s' if len(f) > 1 else ''}"
        for p, f in detected.items()
    )
    _cb("cicd_detected", f"Found → {platforms_str}")

    # 4. Latest run status
    if client.token:
        result["latest_run"] = client.get_latest_workflow_run(full_name)

    # 5. Download + analyze + security check each file
    with tempfile.TemporaryDirectory() as tmpdir:
        for platform, paths in detected.items():
            for file_path in paths:
                _cb("cicd_analyzing", f"Analyzing {file_path}  [{platform}]")
                try:
                    content = client.get_raw_content(owner, repo, branch, file_path)
                except Exception as e:
                    logger.error("Could not download %s: %s", file_path, e)
                    continue

                safe_name = re.sub(r"[/\\]", "_", file_path)
                tmp_file = os.path.join(tmpdir, safe_name)
                Path(tmp_file).write_text(content, encoding="utf-8")

                analysis = analyze_pipeline(tmp_file, platform)
                analysis["file"] = file_path
                analysis["repo_slug"] = full_name
                analysis["repo_url"] = result["meta"]["url"]
                result["analyses"].append(analysis)

                if "error" not in analysis:
                    _cb("cicd_security", f"Running security checks — {os.path.basename(file_path)}")
                    sec = run_security_checks(content, platform)
                    sec["file"] = file_path
                    result["security_results"].append(sec)

    # 6. Build artifact verification
    if client.token:
        _cb("cicd_build_verify", "Verifying build artifacts from workflow runs…")
        try:
            result["build_verification"] = verify_build_artifacts(
                owner, repo, progress_callback=_cb,
            )
        except Exception as e:
            logger.warning("Build verification failed for %s: %s", full_name, e)
            result["build_verification"] = {"build_health": "error", "error": str(e)}

    # 7. Generate standalone CI/CD HTML report
    try:
        if result["analyses"] or result["security_results"]:
            report_id = uuid.uuid4().hex[:10]
            report_dir = settings.REPORTS_DIR / report_id
            report_dir.mkdir(parents=True, exist_ok=True)

            report_path = report_dir / "report.html"

            generate_html_report(
                result["analyses"],
                result["security_results"],
                output_path=str(report_path),
            )

            result["report_id"] = report_id
            result["report_url"] = f"/api/cicd/reports/{report_id}"
    except Exception as e:
        logger.warning("Could not generate CI/CD HTML report for %s: %s", full_name, e)

    _cb("cicd_complete", f"CI/CD analysis complete for {full_name}")
    return result
